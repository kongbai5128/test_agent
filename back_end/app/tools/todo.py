"""
todo 工具 — 会话隔离的待办事项管理。
每个 session 有独立的 todos 列表，通过 ToolContext 从 SessionStore 中读写。
"""
from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from .registry import ToolSpec, register


def _todo_handler(params: dict, context: Any = None) -> str:
    action: str = params.get("action", "list")

    # ── 从 context 取 session todos ─────────────────────────────
    session = None
    todos: list[dict] = []

    if context is not None:
        session = context.session_store.get(context.session_id)
        if session is not None:
            todos = list(session.todos)

    # ── 执行操作 ─────────────────────────────────────────────────
    if action == "list":
        if not todos:
            return "📋 待办事项列表为空。\n提示：使用 add 操作添加新待办。"
        lines = ["📋 待办事项列表：\n"]
        for t in todos:
            status_icon = "✅" if t.get("done") else "⬜"
            short_id = t["id"][:6]
            lines.append(f"{status_icon} [{short_id}] {t['content']}")
        return "\n".join(lines)

    elif action == "add":
        content: str = params.get("content", "").strip()
        if not content:
            return "错误：请提供待办事项内容（content 字段）"
        item = {
            "id": uuid.uuid4().hex[:8],
            "content": content,
            "done": False,
            "created_at": datetime.now().isoformat(),
        }
        todos.append(item)
        _save(context, session, todos)
        return f"✅ 已添加待办：「{content}」（ID: {item['id'][:6]}）"

    elif action == "done":
        item_id: str = params.get("id", "").strip()
        if not item_id:
            return "错误：请提供待办事项 ID（id 字段，可以只写前几位）"
        for t in todos:
            if t["id"].startswith(item_id):
                if t.get("done"):
                    return f"「{t['content']}」已经是完成状态"
                t["done"] = True
                _save(context, session, todos)
                return f"✅ 已标记完成：「{t['content']}」"
        return f"未找到 ID 以「{item_id}」开头的待办事项"

    elif action == "delete":
        item_id = params.get("id", "").strip()
        if not item_id:
            return "错误：请提供要删除的待办 ID"
        original_len = len(todos)
        target = next((t for t in todos if t["id"].startswith(item_id)), None)
        if target is None:
            return f"未找到 ID 以「{item_id}」开头的待办事项"
        todos = [t for t in todos if not t["id"].startswith(item_id)]
        _save(context, session, todos)
        return f"🗑️ 已删除：「{target['content']}」"

    else:
        return f"未知操作：{action}。支持的操作：list / add / done / delete"


def _save(context: Any, session: Any, todos: list[dict]) -> None:
    """将更新后的 todos 写回 session 并持久化。"""
    if context is not None and session is not None:
        session.todos = todos
        context.session_store.save(session)


register(
    ToolSpec(
        name="todo",
        description=(
            "管理当前会话的待办事项列表。支持查看(list)、添加(add)、"
            "标记完成(done)、删除(delete)四种操作。每个对话窗口有独立的待办列表。"
        ),
        parameters={
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": ["list", "add", "done", "delete"],
                    "description": (
                        "操作类型：\n"
                        "- list：查看所有待办\n"
                        "- add：添加新待办（需要 content）\n"
                        "- done：标记为完成（需要 id）\n"
                        "- delete：删除待办（需要 id）"
                    ),
                },
                "content": {
                    "type": "string",
                    "description": "待办事项内容，action=add 时必须提供",
                },
                "id": {
                    "type": "string",
                    "description": "待办事项 ID（前缀匹配），action=done 或 delete 时必须提供",
                },
            },
            "required": ["action"],
        },
        handler=_todo_handler,
    )
)
