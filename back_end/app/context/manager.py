from __future__ import annotations

import logging

logger = logging.getLogger(__name__)

# ── Context 管理配置 ──────────────────────────────────────────
# 触发压缩的估算 token 阈值（字符数 / 4 为 token 估算）
COMPRESS_THRESHOLD_CHARS = 30_000  # ~7500 tokens

# 压缩时保留最近消息数
KEEP_RECENT_MESSAGES = 8

# 旧工具结果的截断长度（字符）
OLD_TOOL_RESULT_MAX_CHARS = 400

# 单次对话最大轮次（超过时触发 context 压缩重置）
MAX_ROUNDS = 20


def estimate_chars(messages: list[dict], system_prompt: str = "") -> int:
    """粗估 token 数（以字符数近似，1 token ≈ 4 chars）。"""
    total = len(system_prompt)
    for m in messages:
        total += len(m.get("role", ""))
        content = m.get("content")
        if isinstance(content, str):
            total += len(content)
        for tc in m.get("tool_calls", []):
            fn = tc.get("function", {})
            total += len(fn.get("name", "")) + len(fn.get("arguments", ""))
    return total


def count_user_turns(messages: list[dict]) -> int:
    """统计用户消息轮次。"""
    return sum(1 for m in messages if m.get("role") == "user")


def should_compress(messages: list[dict], system_prompt: str = "") -> bool:
    return estimate_chars(messages, system_prompt) > COMPRESS_THRESHOLD_CHARS


def compress(messages: list[dict], system_prompt: str = "") -> list[dict]:
    """
    两阶段 Context 压缩：
    Step 1 — microcompact：截断靠前的旧工具结果，减少字符但保留消息结构。
    Step 2 — 若仍超阈值：只保留最近 KEEP_RECENT_MESSAGES 条 + 注入压缩说明。
    """
    if not messages:
        return messages

    messages = list(messages)  # 浅复制，不修改原列表

    # Step 1: microcompact 截断旧 tool result
    cutoff = max(0, len(messages) - KEEP_RECENT_MESSAGES)
    for i in range(cutoff):
        m = messages[i]
        if m.get("role") == "tool":
            content = m.get("content", "")
            if isinstance(content, str) and len(content) > OLD_TOOL_RESULT_MAX_CHARS:
                messages[i] = {
                    **m,
                    "content": content[:OLD_TOOL_RESULT_MAX_CHARS] + "\n…[旧结果已截断]",
                }

    # Step 2: 完整截断 + 摘要注入
    if estimate_chars(messages, system_prompt) > COMPRESS_THRESHOLD_CHARS:
        dropped = len(messages) - KEEP_RECENT_MESSAGES
        recent = messages[-KEEP_RECENT_MESSAGES:]
        summary_note = {
            "role": "system",
            "content": (
                f"[Context 自动压缩：已省略较早的 {dropped} 条消息，"
                "保留最近对话以节省 token。请继续根据当前上下文作答。]"
            ),
        }
        messages = [summary_note] + recent
        logger.info(
            "Context compressed: kept last %d messages (dropped %d)",
            KEEP_RECENT_MESSAGES,
            dropped,
        )

    return messages
