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
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal

MEMORY_TYPES = ("user", "feedback", "project", "reference")
MemoryType = Literal["user", "feedback", "project", "reference"]


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
