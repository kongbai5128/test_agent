from __future__ import annotations

import json
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Optional


@dataclass
class Session:
    """
    一个完整会话的数据模型。

    raw_messages: OpenAI 格式的原始消息列表，用于给 LLM 提供上下文。
    display_messages: 格式化的展示消息，供前端渲染。
    todos: 该会话的独立待办事项列表。
    tool_traces: 本会话所有工具调用的执行日志。
    """

    id: str
    title: str
    raw_messages: list[dict]
    display_messages: list[dict]
    todos: list[dict]
    created_at: str
    updated_at: str
    tool_traces: list[dict] = field(default_factory=list)
    total_input_tokens: int = 0
    total_output_tokens: int = 0


class SessionStore:
    """JSON 文件持久化的 Session 存储。"""

    def __init__(self, sessions_dir: Path) -> None:
        self.sessions_dir = sessions_dir
        self.sessions_dir.mkdir(parents=True, exist_ok=True)
        self._cache: dict[str, Session] = {}
        self._load_all()

    def _load_all(self) -> None:
        for path in self.sessions_dir.glob("*.json"):
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
                # 兼容旧格式（缺少 todos 字段）
                data.setdefault("todos", [])
                data.setdefault("display_messages", [])
                data.setdefault("tool_traces", [])
                data.setdefault("total_input_tokens", 0)
                data.setdefault("total_output_tokens", 0)
                session = Session(**data)
                self._cache[session.id] = session
            except Exception:
                pass

    def create(self, title: str = "") -> Session:
        now = datetime.now().isoformat()
        session = Session(
            id=uuid.uuid4().hex[:12],
            title=title or f"新对话 {datetime.now().strftime('%m-%d %H:%M')}",
            raw_messages=[],
            display_messages=[],
            todos=[],
            created_at=now,
            updated_at=now,
        )
        self._cache[session.id] = session
        self._persist(session)
        return session

    def get(self, session_id: str) -> Optional[Session]:
        return self._cache.get(session_id)

    def list_all(self) -> list[Session]:
        return sorted(self._cache.values(), key=lambda s: s.updated_at, reverse=True)

    def save(self, session: Session) -> None:
        session.updated_at = datetime.now().isoformat()
        self._cache[session.id] = session
        self._persist(session)

    def delete(self, session_id: str) -> bool:
        if session_id not in self._cache:
            return False
        del self._cache[session_id]
        path = self.sessions_dir / f"{session_id}.json"
        if path.exists():
            path.unlink()
        return True

    def _persist(self, session: Session) -> None:
        path = self.sessions_dir / f"{session.id}.json"
        path.write_text(
            json.dumps(asdict(session), indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
