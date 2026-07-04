from __future__ import annotations

import logging

logger = logging.getLogger(__name__)

# ── Context 管理配置 ──────────────────────────────────────────
# 触发压缩的估算 token 阈值（字符数 / 4 为 token 估算）
COMPRESS_THRESHOLD_CHARS = 30_000  # ~7500 tokens

# 压缩时保留最近用户对话轮次数
KEEP_RECENT_USER_TURNS = 8

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


def compress(
    messages: list[dict],
    system_prompt: str = "",
    *,
    force: bool = False,
) -> list[dict]:
    """
    两阶段 Context 压缩：
    Step 1 — microcompact：截断靠前的旧工具结果，减少字符但保留消息结构。
    Step 2 — 若仍超阈值，或 force=True：只保留最近 KEEP_RECENT_USER_TURNS 轮用户对话 + 注入压缩说明。
    """
    if not messages:
        return messages

    messages = list(messages)  # 浅复制，不修改原列表
    recent_start = recent_user_turn_start_index(messages, KEEP_RECENT_USER_TURNS)

    # Step 1: microcompact 截断旧 tool result
    for i in range(recent_start):
        m = messages[i]
        if m.get("role") == "tool":
            content = m.get("content", "")
            if isinstance(content, str) and len(content) > OLD_TOOL_RESULT_MAX_CHARS:
                messages[i] = {
                    **m,
                    "content": content[:OLD_TOOL_RESULT_MAX_CHARS] + "\n…[旧结果已截断]",
                }

    # Step 2: 完整截断 + 摘要注入
    if (force or estimate_chars(messages, system_prompt) > COMPRESS_THRESHOLD_CHARS) and (
        recent_start > 0
    ):
        dropped = recent_start
        recent = messages[recent_start:]
        kept_turns = count_user_turns(recent)
        summary_note = {
            "role": "system",
            "content": (
                f"[Context 自动压缩：已省略较早的 {dropped} 条消息，"
                f"保留最近 {kept_turns} 轮用户对话以节省 token。"
                "请继续根据当前上下文作答。]"
            ),
        }
        messages = [summary_note] + recent
        logger.info(
            "Context compressed: kept last %d user turns (dropped %d messages)",
            kept_turns,
            dropped,
        )

    return sanitize_chat_messages(messages)


def recent_user_turn_start_index(messages: list[dict], keep_user_turns: int) -> int:
    """返回最近 keep_user_turns 个 user 轮次的起始下标。"""
    if keep_user_turns <= 0:
        return len(messages)

    seen = 0
    for index in range(len(messages) - 1, -1, -1):
        if messages[index].get("role") == "user":
            seen += 1
            if seen == keep_user_turns:
                return index
    return 0


def sanitize_chat_messages(messages: list[dict]) -> list[dict]:
    """
    移除不符合 Chat Completions tool 消息顺序的历史片段。

    API 要求 role=tool 必须紧跟在带 tool_calls 的 assistant 后面；
    context 截断可能切断这个结构，所以发送给模型前需要修复。
    """
    clean: list[dict] = []
    i = 0
    dropped = 0

    while i < len(messages):
        message = messages[i]
        role = message.get("role")

        if role == "tool":
            dropped += 1
            i += 1
            continue

        tool_calls = message.get("tool_calls") if role == "assistant" else None
        if not tool_calls:
            clean.append(message)
            i += 1
            continue

        expected_ids = _tool_call_ids(tool_calls)
        tool_results: list[dict] = []
        found_ids: set[str] = set()
        j = i + 1

        while j < len(messages) and messages[j].get("role") == "tool":
            tool_message = messages[j]
            tool_call_id = str(tool_message.get("tool_call_id", ""))
            if tool_call_id in expected_ids and tool_call_id not in found_ids:
                tool_results.append(tool_message)
                found_ids.add(tool_call_id)
            else:
                dropped += 1
            j += 1

        if expected_ids and expected_ids.issubset(found_ids):
            clean.append(message)
            clean.extend(tool_results)
        else:
            stripped = {k: v for k, v in message.items() if k != "tool_calls"}
            if stripped.get("content"):
                clean.append(stripped)
            dropped += len(expected_ids - found_ids)

        i = j

    if dropped:
        logger.info("Sanitized chat history: dropped %d invalid tool message(s)", dropped)
    return clean


def _tool_call_ids(tool_calls: object) -> set[str]:
    if not isinstance(tool_calls, list):
        return set()

    ids: set[str] = set()
    for item in tool_calls:
        if isinstance(item, dict) and item.get("id"):
            ids.add(str(item["id"]))
    return ids
