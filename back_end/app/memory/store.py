"""
长期记忆存储。

参考 ref/shell-agent 的 memory/store.py，但保留后端当前需要的核心能力：
- 结构化 JSON 持久化
- 本地相关性检索
- system prompt 记忆块格式化
"""
from __future__ import annotations

import json
import os
import re
import uuid
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal

MEMORY_TYPES = ("user", "feedback", "project", "reference")
MemoryType = Literal["user", "feedback", "project", "reference"]

DREAM_MIN_HOURS_SINCE_LAST = 24
SESSION_DIGEST_MAX_CHARS = 24_000

_CONSOLIDATE_SYSTEM_PROMPT = """\
你是一个长期记忆整合助手。只输出 JSON，不输出 Markdown 或解释。

请从会话记录中提取未来仍有价值的信息，并整理为长期记忆。

记忆类型：
- feedback：用户纠正过助手的做法，或明确确认某种做法有效。最重要。
- user：用户身份、背景、长期偏好。
- project：项目背景、关键决策、当前状态。不要保存能直接从代码读取的信息。
- reference：外部资源、路径、工具位置等指针。

不要保存：
- 临时任务状态、一次性对话流水。
- 可以直接从代码或文件系统读取的普通路径清单。
- 重复或低价值内容。

输出格式：
{"memories":[{"type":"project","content":"记忆内容","tags":["标签"],"importance":3}]}
""".strip()


@dataclass
class Memory:
    id: str
    content: str
    tags: list[str]
    created_at: str
    source_session: str
    importance: int = 3
    type: str = "project"

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "Memory":
        clean = {
            "id": data["id"],
            "content": data["content"],
            "tags": data.get("tags", []),
            "created_at": data.get("created_at", ""),
            "source_session": data.get("source_session", ""),
            "importance": int(data.get("importance", 3)),
            "type": data.get("type", "project"),
        }
        if clean["type"] not in MEMORY_TYPES:
            clean["type"] = "project"
        if not isinstance(clean["tags"], list):
            clean["tags"] = []
        clean["importance"] = max(1, min(5, clean["importance"]))
        return cls(**clean)


@dataclass
class MemoryIndex:
    last_consolidated_at: str = ""
    total_memories: int = 0
    session_count_at_last_consolidation: int = 0

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "MemoryIndex":
        return cls(
            last_consolidated_at=data.get("last_consolidated_at", ""),
            total_memories=int(data.get("total_memories", 0)),
            session_count_at_last_consolidation=int(
                data.get("session_count_at_last_consolidation", 0)
            ),
        )


def _default_memory_dir() -> Path:
    return Path(os.environ.get("DATA_DIR", "./data")) / "memory"


def _parse_datetime(value: str) -> datetime:
    try:
        dt = datetime.fromisoformat(value)
        if dt.tzinfo is None:
            return dt.replace(tzinfo=timezone.utc)
        return dt
    except Exception:
        return datetime.now(timezone.utc)


def memory_age_text(created_at: str) -> str:
    try:
        days = (datetime.now(timezone.utc) - _parse_datetime(created_at)).days
        if days == 0:
            return ""
        if days == 1:
            return "（昨天）"
        return f"（{days} 天前）"
    except Exception:
        return ""


def _normalize_text(text: str) -> str:
    return re.sub(r"\s+", " ", text.lower()).strip()


def _tokenize_text(text: str) -> set[str]:
    normalized = _normalize_text(text)
    tokens = set(re.findall(r"[a-z0-9_+\-]{2,}", normalized))

    for chunk in re.findall(r"[\u4e00-\u9fff]+", normalized):
        tokens.add(chunk)
        if len(chunk) >= 2:
            tokens.update(chunk[i : i + 2] for i in range(len(chunk) - 1))
    return tokens


def _freshness_factor(created_at: str) -> float:
    days_old = (datetime.now(timezone.utc) - _parse_datetime(created_at)).days
    if days_old <= 7:
        return 1.0
    return max(0.6, 1.0 - days_old * 0.01)


def _score_memory_relevance(memory: Memory, query: str) -> float:
    query_text = _normalize_text(query)
    if not query_text:
        return 0.0

    query_tokens = _tokenize_text(query_text)
    if not query_tokens:
        return 0.0

    content_text = _normalize_text(memory.content)
    tags_text = _normalize_text(" ".join(memory.tags))
    combined_text = f"{content_text} {tags_text}".strip()
    combined_tokens = _tokenize_text(combined_text)

    token_overlap = query_tokens & combined_tokens
    exact_phrase_hit = len(query_text) >= 4 and query_text in combined_text
    tag_overlap = query_tokens & _tokenize_text(tags_text)

    if not token_overlap and not exact_phrase_hit:
        return 0.0

    coverage = len(token_overlap) / max(len(query_tokens), 1)
    if not exact_phrase_hit and coverage < 0.2:
        return 0.0

    score = 0.0
    if exact_phrase_hit:
        score += 6.0
    score += len(token_overlap) * 2.0
    score += coverage * 4.0
    score += len(tag_overlap) * 1.5
    score += min(memory.importance, 5) * 0.35
    return score * _freshness_factor(memory.created_at)


class MemoryStore:
    """每条长期记忆存为一个 JSON 文件。"""

    def __init__(self, memory_dir: Path | None = None) -> None:
        self.memory_dir = memory_dir or _default_memory_dir()
        self.memory_dir.mkdir(parents=True, exist_ok=True)
        self.index_file = self.memory_dir / "_index.json"

    def save(self, memory: Memory) -> Path:
        path = self.memory_dir / f"{memory.id}.json"
        path.write_text(
            json.dumps(memory.to_dict(), indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
        self._write_index(total_memories=len(self.load_all()))
        return path

    def load_all(self) -> list[Memory]:
        memories: list[Memory] = []
        for path in sorted(self.memory_dir.glob("*.json")):
            if path.name.startswith("_"):
                continue
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
                memories.append(Memory.from_dict(data))
            except Exception:
                continue
        return sorted(
            memories,
            key=lambda m: (_parse_datetime(m.created_at), m.importance),
            reverse=True,
        )

    def find_relevant(self, query: str, top_k: int = 5) -> list[Memory]:
        scored: list[tuple[float, Memory]] = []
        for memory in self.load_all():
            score = _score_memory_relevance(memory, query)
            if score > 0:
                scored.append((score, memory))
        scored.sort(key=lambda item: item[0], reverse=True)
        return [memory for _, memory in scored[:top_k]]

    def delete(self, memory_id: str) -> bool:
        path = self.memory_dir / f"{memory_id}.json"
        if not path.exists():
            return False
        path.unlink()
        self._write_index(total_memories=len(self.load_all()))
        return True

    def get_index(self) -> MemoryIndex:
        if self.index_file.exists():
            try:
                data = json.loads(self.index_file.read_text(encoding="utf-8"))
                return MemoryIndex.from_dict(data)
            except Exception:
                pass
        return MemoryIndex(total_memories=len(self.load_all()))

    def _write_index(self, total_memories: int) -> None:
        old = self.get_index()
        index = MemoryIndex(
            last_consolidated_at=old.last_consolidated_at,
            total_memories=total_memories,
            session_count_at_last_consolidation=(
                old.session_count_at_last_consolidation
            ),
        )
        self.index_file.write_text(
            json.dumps(index.to_dict(), indent=2, ensure_ascii=False),
            encoding="utf-8",
        )

    def update_consolidation_timestamp(self, session_count: int) -> None:
        index = MemoryIndex(
            last_consolidated_at=datetime.now(timezone.utc).isoformat(),
            total_memories=len(self.load_all()),
            session_count_at_last_consolidation=session_count,
        )
        self.index_file.write_text(
            json.dumps(index.to_dict(), indent=2, ensure_ascii=False),
            encoding="utf-8",
        )


def build_memory_block(query: str, store: MemoryStore, top_k: int = 3) -> str:
    if query:
        memories = store.find_relevant(query, top_k=top_k)
    else:
        memories = sorted(
            store.load_all(),
            key=lambda m: (m.importance, _parse_datetime(m.created_at)),
            reverse=True,
        )[:top_k]

    if not memories:
        return ""

    lines = [
        "[相关长期记忆]",
        "以下内容来自长期记忆，可能过时；若与用户最新消息冲突，以最新消息为准。",
    ]
    for memory in memories:
        age = memory_age_text(memory.created_at)
        tags = f" tags={','.join(memory.tags)}" if memory.tags else ""
        lines.append(f"- [{memory.type}{tags}] {memory.content}{age}")
    return "\n".join(lines)


def count_non_empty_sessions(session_store: Any) -> int:
    return sum(1 for session in session_store.list_all() if session.raw_messages)


def should_consolidate_sessions(
    session_store: Any,
    memory_store: MemoryStore,
    *,
    min_hours_since_last: int = DREAM_MIN_HOURS_SINCE_LAST,
) -> bool:
    sessions = [session for session in session_store.list_all() if session.raw_messages]
    current_count = len(sessions)
    if current_count <= 0:
        return False

    index = memory_store.get_index()
    if not index.last_consolidated_at:
        return True

    try:
        last = _parse_datetime(index.last_consolidated_at)
        hours = (datetime.now(timezone.utc) - last).total_seconds() / 3600
        if hours < min_hours_since_last:
            return False
    except Exception:
        return True

    has_new_session = current_count > index.session_count_at_last_consolidation
    has_updated_session = any(
        _parse_datetime(session.updated_at) > last for session in sessions
    )
    return has_new_session or has_updated_session


def format_session_digest(session: Any) -> str:
    lines: list[str] = [f"=== 会话 {session.id}：{session.title} ==="]
    messages = session.raw_messages or []

    for msg in messages:
        role = msg.get("role", "")
        content = msg.get("content", "")

        if role == "user" and isinstance(content, str) and content.strip():
            lines.append(f"[用户] {_trim_text(content, 800)}")
        elif role == "assistant":
            if isinstance(content, str) and content.strip():
                lines.append(f"[助手] {_trim_text(content, 400)}")
            tool_calls = msg.get("tool_calls", [])
            if tool_calls:
                names = [
                    call.get("function", {}).get("name", "?")
                    for call in tool_calls
                    if isinstance(call, dict)
                ]
                if names:
                    lines.append(f"[工具调用] {', '.join(names)}")
        elif role == "tool" and isinstance(content, str):
            lowered = content.lower()
            if any(word in lowered for word in ("错误", "error", "失败", "failed")):
                lines.append(f"[工具错误] {_trim_text(content, 300)}")

    if len(lines) == 1:
        for msg in session.display_messages:
            role = msg.get("role", "")
            content = msg.get("content", "")
            if (
                role in {"user", "assistant"}
                and isinstance(content, str)
                and content.strip()
            ):
                label = "用户" if role == "user" else "助手"
                lines.append(f"[{label}] {_trim_text(content, 500)}")

    return "\n".join(lines) if len(lines) > 1 else ""


def build_sessions_digest(
    session_store: Any,
    *,
    max_chars: int = SESSION_DIGEST_MAX_CHARS,
) -> str:
    chunks: list[str] = []
    total = 0
    for session in session_store.list_all():
        digest = format_session_digest(session)
        if not digest:
            continue
        if total + len(digest) > max_chars:
            remaining = max_chars - total
            if remaining > 500:
                chunks.append(digest[:remaining] + "\n...[已截断]")
            break
        chunks.append(digest)
        total += len(digest)
    return "\n\n".join(chunks)


async def consolidate_sessions_to_memory(
    *,
    client: Any,
    model: str,
    session_store: Any,
    memory_store: MemoryStore,
    force: bool = False,
) -> dict:
    if not force and not should_consolidate_sessions(session_store, memory_store):
        return {
            "status": "skipped",
            "reason": "未达到自动整合条件",
            "created": 0,
            "memory_ids": [],
        }

    session_digest = build_sessions_digest(session_store)
    if not session_digest:
        memory_store.update_consolidation_timestamp(count_non_empty_sessions(session_store))
        return {
            "status": "skipped",
            "reason": "没有可整合的会话内容",
            "created": 0,
            "memory_ids": [],
        }

    existing = [
        {"id": m.id, "type": m.type, "content": m.content, "tags": m.tags}
        for m in memory_store.load_all()
    ]
    prompt = (
        "现有长期记忆：\n"
        f"{json.dumps(existing, ensure_ascii=False)}\n\n"
        "待整合会话：\n"
        f"{session_digest}"
    )

    response = await client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": _CONSOLIDATE_SYSTEM_PROMPT},
            {"role": "user", "content": prompt},
        ],
        max_tokens=2048,
        temperature=0.2,
    )
    raw = response.choices[0].message.content or ""
    data = _parse_json_object(raw)
    items = data.get("memories", [])
    if not isinstance(items, list):
        items = []

    saved_ids: list[str] = []
    existing_contents = {_normalize_text(m.content) for m in memory_store.load_all()}
    for item in items:
        memory = _memory_from_model_item(item)
        if memory is None:
            continue
        normalized = _normalize_text(memory.content)
        if normalized in existing_contents:
            continue
        memory_store.save(memory)
        existing_contents.add(normalized)
        saved_ids.append(memory.id)

    session_count = count_non_empty_sessions(session_store)
    memory_store.update_consolidation_timestamp(session_count)
    return {
        "status": "ok",
        "created": len(saved_ids),
        "memory_ids": saved_ids,
        "session_count": session_count,
    }


def _trim_text(text: str, limit: int) -> str:
    clean = text.strip()
    if len(clean) <= limit:
        return clean
    return clean[:limit] + "..."


def _parse_json_object(text: str) -> dict:
    match = re.search(r"\{.*\}", text, re.DOTALL)
    if not match:
        return {}
    try:
        data = json.loads(match.group())
    except Exception:
        return {}
    return data if isinstance(data, dict) else {}


def _memory_from_model_item(item: Any) -> Memory | None:
    if not isinstance(item, dict):
        return None

    content = str(item.get("content", "")).strip()
    if not content:
        return None

    mem_type = str(item.get("type", "project")).strip() or "project"
    if mem_type not in MEMORY_TYPES:
        mem_type = "project"

    raw_tags = item.get("tags", [])
    tags = (
        [str(tag).strip() for tag in raw_tags if str(tag).strip()]
        if isinstance(raw_tags, list)
        else []
    )
    try:
        importance = int(item.get("importance", 3))
    except (TypeError, ValueError):
        importance = 3
    importance = max(1, min(5, importance))

    return Memory(
        id=f"mem-{uuid.uuid4().hex[:8]}",
        content=content,
        tags=tags,
        created_at=datetime.now(timezone.utc).isoformat(),
        source_session="auto_consolidate",
        importance=importance,
        type=mem_type,
    )
