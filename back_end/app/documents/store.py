from __future__ import annotations

import json
import re
import shutil
import uuid
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from typing import BinaryIO

ALLOWED_SUFFIXES = {".pdf", ".doc", ".docx", ".txt", ".md", ".markdown"}
MAX_UPLOAD_SIZE = 25 * 1024 * 1024


@dataclass
class Document:
    id: str
    session_id: str
    filename: str
    stored_name: str
    content_type: str
    size: int
    path: str
    created_at: str
    status: str = "ready"

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "Document":
        return cls(
            id=data["id"],
            session_id=data["session_id"],
            filename=data["filename"],
            stored_name=data["stored_name"],
            content_type=data.get("content_type", "application/octet-stream"),
            size=int(data.get("size", 0)),
            path=data["path"],
            created_at=data.get("created_at", ""),
            status=data.get("status", "ready"),
        )


def _safe_filename(filename: str) -> str:
    raw = Path(filename or "document").name.strip() or "document"
    safe = re.sub(r"[^A-Za-z0-9._\-\u4e00-\u9fff]+", "_", raw)
    return safe[:120] or "document"


class DocumentStore:
    def __init__(self, docs_dir: Path) -> None:
        self.docs_dir = docs_dir
        self.docs_dir.mkdir(parents=True, exist_ok=True)

    def session_dir(self, session_id: str) -> Path:
        path = self.docs_dir / session_id
        path.mkdir(parents=True, exist_ok=True)
        return path

    def save_upload(
        self,
        *,
        session_id: str,
        filename: str,
        content_type: str,
        fileobj: BinaryIO,
    ) -> Document:
        safe_name = _safe_filename(filename)
        suffix = Path(safe_name).suffix.lower()
        if suffix not in ALLOWED_SUFFIXES:
            allowed = ", ".join(sorted(ALLOWED_SUFFIXES))
            raise ValueError(f"仅支持这些文件类型：{allowed}")

        doc_id = f"doc-{uuid.uuid4().hex[:10]}"
        doc_dir = self.session_dir(session_id) / doc_id
        doc_dir.mkdir(parents=True, exist_ok=True)
        stored_name = f"original{suffix}"
        target = doc_dir / stored_name

        size = 0
        with target.open("wb") as out:
            while True:
                chunk = fileobj.read(1024 * 1024)
                if not chunk:
                    break
                size += len(chunk)
                if size > MAX_UPLOAD_SIZE:
                    shutil.rmtree(doc_dir, ignore_errors=True)
                    raise ValueError("文件超过 25MB 限制")
                out.write(chunk)

        document = Document(
            id=doc_id,
            session_id=session_id,
            filename=safe_name,
            stored_name=stored_name,
            content_type=content_type or "application/octet-stream",
            size=size,
            path=str(target),
            created_at=datetime.now().isoformat(),
        )
        self._write_meta(document)
        return document

    def get(self, session_id: str, document_id: str) -> Document | None:
        meta_path = self.docs_dir / session_id / document_id / "meta.json"
        if not meta_path.exists():
            return None
        try:
            return Document.from_dict(json.loads(meta_path.read_text(encoding="utf-8")))
        except Exception:
            return None

    def get_many(self, session_id: str, document_ids: list[str]) -> list[Document]:
        docs: list[Document] = []
        seen: set[str] = set()
        for document_id in document_ids:
            if document_id in seen:
                continue
            seen.add(document_id)
            document = self.get(session_id, document_id)
            if document is not None:
                docs.append(document)
        return docs

    def list_for_session(self, session_id: str) -> list[Document]:
        root = self.docs_dir / session_id
        if not root.exists():
            return []
        docs: list[Document] = []
        for meta_path in sorted(root.glob("*/meta.json")):
            try:
                docs.append(
                    Document.from_dict(json.loads(meta_path.read_text(encoding="utf-8")))
                )
            except Exception:
                continue
        return sorted(docs, key=lambda item: item.created_at, reverse=True)

    def delete(self, session_id: str, document_id: str) -> bool:
        doc_dir = self.docs_dir / session_id / document_id
        if not doc_dir.exists():
            return False
        shutil.rmtree(doc_dir)
        return True

    def delete_session(self, session_id: str) -> None:
        shutil.rmtree(self.docs_dir / session_id, ignore_errors=True)

    def resolve_path(self, session_id: str, document_id: str) -> Path:
        document = self.get(session_id, document_id)
        if document is None:
            raise ValueError(f"未找到文档：{document_id}")
        path = Path(document.path).resolve()
        try:
            path.relative_to(self.docs_dir.resolve())
        except ValueError as exc:
            raise ValueError("文档路径越界，拒绝读取") from exc
        if not path.exists():
            raise ValueError(f"文档文件不存在：{document.filename}")
        return path

    def _write_meta(self, document: Document) -> None:
        meta_path = self.docs_dir / document.session_id / document.id / "meta.json"
        meta_path.write_text(
            json.dumps(document.to_dict(), indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
