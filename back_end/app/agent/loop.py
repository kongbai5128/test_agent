"""
Agent 核心循环。

Loop 步骤：
  Step 1 — 接收用户输入（已追加至 raw_messages）
  Step 2 — 调用 LLM，判断：直接回复 还是 调用工具
  Step 3 — 若调用工具：执行工具，将结果追加至 raw_messages，继续循环
  Step 4 — 若直接回复（stop_reason == "stop"）：yield message 事件，结束循环

通过 AsyncGenerator yield 事件，供 SSE 接口实时推送到前端：
  {"type": "thinking",    "content": str}           # LLM 思考文本（伴随工具调用时）
  {"type": "tool_start",  "tool": str, "params": {}} # 工具调用开始
  {"type": "tool_result", "tool": str, "result": str}# 工具执行结果
  {"type": "message",     "content": str}            # 最终答案（对话结束）
  {"type": "error",       "message": str}            # 异常
  {"type": "done"}                                   # 循环结束
"""
from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass
from typing import Any, AsyncGenerator

from openai import AsyncOpenAI

from ..tools import execute as tool_execute, to_openai_tools

logger = logging.getLogger(__name__)


@dataclass
class ToolContext:
    """传递给工具 handler 的运行时上下文（携带会话信息）。"""

    session_id: str
    session_store: Any  # SessionStore，避免循环导入


async def run_agent_loop(
    *,
    session_id: str,
    user_input: str,
    raw_messages: list[dict],
    system_prompt: str,
    client: AsyncOpenAI,
    model: str,
    max_iterations: int,
    session_store: Any,
    tool_traces: list[dict],
) -> AsyncGenerator[dict, None]:
    """
    核心 Agent 循环（异步生成器）。

    raw_messages 在此函数内会被 **就地修改**（追加 assistant / tool 消息），
    调用方在循环结束后应将更新后的 raw_messages 持久化到 session。
    """
    # 将用户输入追加至 raw_messages（Step 1）
    raw_messages.append({"role": "user", "content": user_input})

    tool_definitions = to_openai_tools()
    tool_ctx = ToolContext(session_id=session_id, session_store=session_store)

    for iteration in range(max_iterations):
        # ── Step 2：调用 LLM ─────────────────────────────────────
        try:
            response = await client.chat.completions.create(
                model=model,
                messages=[{"role": "system", "content": system_prompt}] + raw_messages,
                tools=tool_definitions if tool_definitions else None,
                tool_choice="auto" if tool_definitions else None,
                max_tokens=4096,
                temperature=0.7,
            )
        except Exception as exc:
            logger.error("LLM API error (iteration %d): %s", iteration, exc, exc_info=True)
            yield {"type": "error", "message": f"LLM 调用失败：{exc}"}
            yield {"type": "done"}
            return

        choice = response.choices[0]
        msg = choice.message
        stop_reason = choice.finish_reason  # "stop" | "tool_calls" | "length"

        # 序列化 assistant 消息以便追加至历史
        msg_dict: dict = {"role": "assistant", "content": msg.content or ""}
        if msg.tool_calls:
            msg_dict["tool_calls"] = [
                {
                    "id": tc.id,
                    "type": "function",
                    "function": {
                        "name": tc.function.name,
                        "arguments": tc.function.arguments,
                    },
                }
                for tc in msg.tool_calls
            ]
        raw_messages.append(msg_dict)

        # ── Step 2b：LLM 直接回复（无工具调用）→ 结束 ─────────────
        if not msg.tool_calls:
            yield {"type": "message", "content": msg.content or ""}
            yield {"type": "done"}
            return

        # ── Step 2c：LLM 附带思考文本 ─────────────────────────────
        if msg.content:
            yield {"type": "thinking", "content": msg.content}

        # ── Step 3：执行所有工具调用 ──────────────────────────────
        for tc in msg.tool_calls:
            tool_name = tc.function.name
            try:
                tool_params = json.loads(tc.function.arguments)
            except json.JSONDecodeError:
                tool_params = {}

            yield {"type": "tool_start", "tool": tool_name, "params": tool_params}

            t0 = time.monotonic()
            result = tool_execute(tool_name, tool_params, tool_ctx)
            elapsed_ms = int((time.monotonic() - t0) * 1000)

            # 记录执行 trace
            tool_traces.append(
                {
                    "iteration": iteration,
                    "tool": tool_name,
                    "params": tool_params,
                    "result": result,
                    "elapsed_ms": elapsed_ms,
                }
            )

            yield {"type": "tool_result", "tool": tool_name, "result": result}

            # 将工具结果追加至 raw_messages（Step 4 判断依据）
            raw_messages.append(
                {
                    "role": "tool",
                    "tool_call_id": tc.id,
                    "content": result,
                }
            )

        # Step 4：有工具结果 → 继续循环，让 LLM 综合结果再次决策

    # 超过最大迭代次数
    yield {
        "type": "error",
        "message": f"已达到最大迭代次数（{max_iterations} 轮），自动停止。",
    }
    yield {"type": "done"}
