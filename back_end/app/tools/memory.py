"""
memory 工具 — 让 LLM 主动保存长期记忆。

长期记忆会写入 data/memory，并在后续对话中按相关性注入 system prompt。
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any

from ..memory import MEMORY_TYPES, Memory, MemoryStore
from .registry import ToolSpec, register


def _get_store(context: Any = None) -> MemoryStore:
    store = getattr(context, "memory_store", None) if context is not None else None
    if store is not None:
        return store
    return MemoryStore()


def _memory_save(params: dict, context: Any = None) -> str:
    content = str(params.get("content", "")).strip()
    if not content:
        return "错误：content 不能为空"

    mem_type = str(params.get("type", "project")).strip() or "project"
    if mem_type not in MEMORY_TYPES:
        return f"错误：type 必须是 {list(MEMORY_TYPES)} 之一，收到 {mem_type!r}"

    raw_tags = params.get("tags", [])
    if isinstance(raw_tags, list):
        tags = [str(tag).strip() for tag in raw_tags if str(tag).strip()]
    else:
        tags = []

    try:
        importance = int(params.get("importance", 3))
    except (TypeError, ValueError):
        importance = 3
    importance = max(1, min(5, importance))

    source_session = getattr(context, "session_id", "inline") if context else "inline"
    memory = Memory(
        id=f"mem-{uuid.uuid4().hex[:8]}",
        content=content,
        tags=tags,
        created_at=datetime.now(timezone.utc).isoformat(),
        source_session=source_session,
        importance=importance,
        type=mem_type,
    )
    _get_store(context).save(memory)
    return f"已保存 [{mem_type}] 长期记忆（id={memory.id}，importance={importance}）"


register(
    ToolSpec(
        name="memory_save",
        description=(
            "将重要信息保存到长期记忆，未来会话会按相关性自动读取。"
            "适合保存用户长期偏好、用户纠正/确认、项目重要背景和外部资源。"
            "不要保存临时状态、当前对话流水、可从代码直接读取的信息。"
        ),
        parameters={
            "type": "object",
            "properties": {
                "content": {
                    "type": "string",
                    "description": (
                        "要保存的记忆内容。feedback 类型建议写成："
                        "规则：[规则]。\\n**Why:** [原因]。\\n**How to apply:** [场景]。"
                    ),
                },
                "type": {
                    "type": "string",
                    "enum": list(MEMORY_TYPES),
                    "description": "记忆类型：user / feedback / project / reference",
                    "default": "project",
                },
                "tags": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "标签列表，用于后续相关性检索",
                    "default": [],
                },
                "importance": {
                    "type": "integer",
                    "minimum": 1,
                    "maximum": 5,
                    "description": "重要性 1-5，越高越优先注入上下文",
                    "default": 3,
                },
            },
            "required": ["content", "type"],
        },
        handler=_memory_save,
    )
)
