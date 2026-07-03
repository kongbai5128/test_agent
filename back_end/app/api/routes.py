from __future__ import annotations

import json
import logging
import uuid
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import StreamingResponse
from openai import AsyncOpenAI
from pydantic import BaseModel, Field
from starlette.datastructures import UploadFile

from ..agent.loop import run_agent_loop
from ..agent.system_prompt import SYSTEM_PROMPT
from ..context import manager as ctx_manager
from ..documents import Document, DocumentStore
from ..memory import MEMORY_TYPES, Memory, MemoryStore, build_memory_block
from ..sessions.store import Session, SessionStore

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api")


# ── 依赖注入 ───────────────────────────────────────────────────

def get_store(request: Request) -> SessionStore:
    return request.app.state.session_store


def get_memory_store(request: Request) -> MemoryStore:
    return request.app.state.memory_store


def get_document_store(request: Request) -> DocumentStore:
    return request.app.state.document_store


def get_client(request: Request) -> AsyncOpenAI:
    return request.app.state.llm_client


def get_model(request: Request) -> str:
    return request.app.state.model


def get_max_iter(request: Request) -> int:
    return request.app.state.max_loop_iterations


# ── Pydantic 请求/响应模型 ─────────────────────────────────────

class CreateSessionRequest(BaseModel):
    title: str = Field(default="", max_length=100)


class UpdateSessionRequest(BaseModel):
    title: str = Field(max_length=100)


class ChatRequest(BaseModel):
    message: str = Field(default="", max_length=8000)
    document_ids: list[str] = Field(default_factory=list, max_length=8)


class CreateMemoryRequest(BaseModel):
    content: str = Field(min_length=1, max_length=4000)
    type: str = Field(default="project")
    tags: list[str] = Field(default_factory=list)
    importance: int = Field(default=3, ge=1, le=5)


# ── Session 路由 ───────────────────────────────────────────────

@router.post("/sessions", status_code=201)
async def create_session(
    body: CreateSessionRequest,
    store: SessionStore = Depends(get_store),
):
    session = store.create(body.title)
    return _session_summary(session)


@router.get("/sessions")
async def list_sessions(store: SessionStore = Depends(get_store)):
    return [_session_summary(s) for s in store.list_all()]


@router.get("/sessions/{session_id}")
async def get_session(
    session_id: str,
    store: SessionStore = Depends(get_store),
):
    session = _get_or_404(store, session_id)
    return {
        **_session_summary(session),
        "display_messages": session.display_messages,
        "todos": session.todos,
        "documents": session.documents,
    }


@router.patch("/sessions/{session_id}")
async def update_session(
    session_id: str,
    body: UpdateSessionRequest,
    store: SessionStore = Depends(get_store),
):
    session = _get_or_404(store, session_id)
    session.title = body.title
    store.save(session)
    return _session_summary(session)


@router.delete("/sessions/{session_id}", status_code=204)
async def delete_session(
    session_id: str,
    store: SessionStore = Depends(get_store),
    document_store: DocumentStore = Depends(get_document_store),
):
    if not store.delete(session_id):
        raise HTTPException(status_code=404, detail="Session not found")
    document_store.delete_session(session_id)


# ── Chat 路由（SSE 流式）──────────────────────────────────────

@router.post("/sessions/{session_id}/chat/stream")
async def chat_stream(
    session_id: str,
    body: ChatRequest,
    store: SessionStore = Depends(get_store),
    client: AsyncOpenAI = Depends(get_client),
    model: str = Depends(get_model),
    max_iter: int = Depends(get_max_iter),
    memory_store: MemoryStore = Depends(get_memory_store),
    document_store: DocumentStore = Depends(get_document_store),
):
    """
    发送消息并以 SSE 格式实时流式返回 Agent 执行过程。

    每条 SSE data 都是一个 JSON 对象：
      {"type": "thinking",    "content": "..."}
      {"type": "tool_start",  "tool": "...", "params": {...}}
      {"type": "tool_result", "tool": "...", "result": "..."}
      {"type": "message",     "content": "..."}
      {"type": "error",       "message": "..."}
      {"type": "done"}
    """
    session = _get_or_404(store, session_id)
    user_input = body.message.strip()
    attached_docs = _get_attached_documents(
        document_store,
        session_id,
        body.document_ids,
    )
    if not user_input and attached_docs:
        user_input = "请阅读并总结上传的文档。"
    if not user_input:
        raise HTTPException(status_code=422, detail="message 或 document_ids 不能为空")

    # 超轮次触发 context 压缩
    if ctx_manager.count_user_turns(session.raw_messages) >= ctx_manager.MAX_ROUNDS:
        session.raw_messages = ctx_manager.compress(
            session.raw_messages, SYSTEM_PROMPT
        )
    elif ctx_manager.should_compress(session.raw_messages, SYSTEM_PROMPT):
        session.raw_messages = ctx_manager.compress(
            session.raw_messages, SYSTEM_PROMPT
        )

    # 会话首条消息时自动设置标题
    if not session.raw_messages and session.title.startswith("新对话"):
        session.title = user_input[:30] + ("…" if len(user_input) > 30 else "")

    # 构建本轮 display 消息（user 部分先添加）
    user_display_msg = {
        "id": uuid.uuid4().hex[:8],
        "role": "user",
        "content": user_input,
        "thinking": None,
        "tool_calls": [],
        "attachments": [_document_response(doc) for doc in attached_docs],
    }
    session.display_messages.append(user_display_msg)

    # 构建待填充的 assistant display 消息
    assistant_display_msg: dict = {
        "id": uuid.uuid4().hex[:8],
        "role": "assistant",
        "content": "",
        "thinking": None,
        "tool_calls": [],
    }

    # raw_messages 由 run_agent_loop 就地修改
    raw_messages = session.raw_messages
    new_traces: list[dict] = []
    system_prompt = _with_relevant_memories(SYSTEM_PROMPT, memory_store, user_input)
    system_prompt = _with_attached_documents(system_prompt, attached_docs)

    async def event_generator():
        try:
            async for event in run_agent_loop(
                session_id=session_id,
                user_input=user_input,
                raw_messages=raw_messages,
                system_prompt=system_prompt,
                client=client,
                model=model,
                max_iterations=max_iter,
                session_store=store,
                memory_store=memory_store,
                document_store=document_store,
                tool_traces=new_traces,
            ):
                # 同步更新 assistant_display_msg
                _apply_event_to_display(event, assistant_display_msg)

                yield f"data: {json.dumps(event, ensure_ascii=False)}\n\n"

        except Exception as exc:
            logger.error("SSE generator error: %s", exc, exc_info=True)
            err_event = {"type": "error", "message": f"服务器内部错误：{exc}"}
            yield f"data: {json.dumps(err_event, ensure_ascii=False)}\n\n"
            done_event = {"type": "done"}
            yield f"data: {json.dumps(done_event, ensure_ascii=False)}\n\n"
        finally:
            # 保存更新后的 session（无论正常结束或出错）
            session.display_messages.append(assistant_display_msg)
            session.tool_traces.extend(new_traces)
            store.save(session)

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",  # 关闭 Nginx 缓冲
        },
    )


# ── 文档上传 ───────────────────────────────────────────────────

@router.post("/sessions/{session_id}/documents", status_code=201)
async def upload_document(
    session_id: str,
    request: Request,
    store: SessionStore = Depends(get_store),
    document_store: DocumentStore = Depends(get_document_store),
):
    session = _get_or_404(store, session_id)
    try:
        form = await request.form()
    except AssertionError as exc:
        raise HTTPException(
            status_code=500,
            detail="文件上传需要安装 python-multipart",
        ) from exc

    upload = form.get("file")
    if not isinstance(upload, UploadFile):
        raise HTTPException(status_code=400, detail="缺少文件字段 file")

    try:
        document = document_store.save_upload(
            session_id=session_id,
            filename=upload.filename or "document",
            content_type=upload.content_type or "application/octet-stream",
            fileobj=upload.file,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    finally:
        await upload.close()

    session.documents = _merge_documents(session.documents, [document])
    store.save(session)
    return _document_response(document)


@router.get("/sessions/{session_id}/documents")
async def list_documents(
    session_id: str,
    store: SessionStore = Depends(get_store),
    document_store: DocumentStore = Depends(get_document_store),
):
    _get_or_404(store, session_id)
    return [_document_response(doc) for doc in document_store.list_for_session(session_id)]


@router.delete("/sessions/{session_id}/documents/{document_id}", status_code=204)
async def delete_document(
    session_id: str,
    document_id: str,
    store: SessionStore = Depends(get_store),
    document_store: DocumentStore = Depends(get_document_store),
):
    session = _get_or_404(store, session_id)
    if not document_store.delete(session_id, document_id):
        raise HTTPException(status_code=404, detail="Document not found")
    session.documents = [
        doc for doc in session.documents if doc.get("id") != document_id
    ]
    store.save(session)


@router.get("/sessions/{session_id}/messages")
async def get_messages(
    session_id: str,
    store: SessionStore = Depends(get_store),
):
    """返回格式化的展示消息列表，供前端初始化或刷新。"""
    session = _get_or_404(store, session_id)
    return session.display_messages


@router.get("/sessions/{session_id}/trace")
async def get_trace(
    session_id: str,
    store: SessionStore = Depends(get_store),
):
    """返回本会话的工具调用执行日志。"""
    session = _get_or_404(store, session_id)
    return session.tool_traces


@router.get("/sessions/{session_id}/todos")
async def get_todos(
    session_id: str,
    store: SessionStore = Depends(get_store),
):
    session = _get_or_404(store, session_id)
    return session.todos


# ── 长期记忆 ───────────────────────────────────────────────────

@router.get("/memories")
async def list_memories(
    query: Optional[str] = None,
    limit: int = 20,
    memory_store: MemoryStore = Depends(get_memory_store),
):
    limit = max(1, min(limit, 100))
    if query and query.strip():
        memories = memory_store.find_relevant(query.strip(), top_k=limit)
    else:
        memories = memory_store.load_all()[:limit]
    return [_memory_response(memory) for memory in memories]


@router.post("/memories", status_code=201)
async def create_memory(
    body: CreateMemoryRequest,
    memory_store: MemoryStore = Depends(get_memory_store),
):
    mem_type = body.type.strip() or "project"
    if mem_type not in MEMORY_TYPES:
        raise HTTPException(
            status_code=400,
            detail=f"type must be one of {list(MEMORY_TYPES)}",
        )

    memory = Memory(
        id=f"mem-{uuid.uuid4().hex[:8]}",
        content=body.content.strip(),
        tags=[tag.strip() for tag in body.tags if tag.strip()],
        created_at=datetime.now(timezone.utc).isoformat(),
        source_session="manual",
        importance=body.importance,
        type=mem_type,
    )
    memory_store.save(memory)
    return _memory_response(memory)


@router.delete("/memories/{memory_id}", status_code=204)
async def delete_memory(
    memory_id: str,
    memory_store: MemoryStore = Depends(get_memory_store),
):
    if not memory_store.delete(memory_id):
        raise HTTPException(status_code=404, detail="Memory not found")


# ── 健康检查 ───────────────────────────────────────────────────

@router.get("/health")
async def health():
    return {"status": "ok"}


# ── 工具列表（供前端展示） ────────────────────────────────────

@router.get("/tools")
async def list_tools():
    from ..tools import all_tools

    return [
        {"name": t.name, "description": t.description, "parameters": t.parameters}
        for t in all_tools()
    ]


# ── 辅助函数 ───────────────────────────────────────────────────

def _get_or_404(store: SessionStore, session_id: str) -> Session:
    session = store.get(session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="Session not found")
    return session


def _session_summary(session: Session) -> dict:
    return {
        "id": session.id,
        "title": session.title,
        "created_at": session.created_at,
        "updated_at": session.updated_at,
        "message_count": len(session.display_messages),
    }


def _memory_response(memory: Memory) -> dict:
    return memory.to_dict()


def _document_response(document: Document) -> dict:
    return {
        "id": document.id,
        "session_id": document.session_id,
        "filename": document.filename,
        "content_type": document.content_type,
        "size": document.size,
        "created_at": document.created_at,
        "status": document.status,
    }


def _merge_documents(existing: list[dict], documents: list[Document]) -> list[dict]:
    by_id = {doc.get("id"): doc for doc in existing if doc.get("id")}
    for document in documents:
        by_id[document.id] = _document_response(document)
    return sorted(
        by_id.values(),
        key=lambda item: item.get("created_at", ""),
        reverse=True,
    )


def _get_attached_documents(
    document_store: DocumentStore,
    session_id: str,
    document_ids: list[str],
) -> list[Document]:
    if not document_ids:
        return []
    documents = document_store.get_many(session_id, document_ids)
    found_ids = {doc.id for doc in documents}
    missing = [doc_id for doc_id in document_ids if doc_id not in found_ids]
    if missing:
        raise HTTPException(
            status_code=404,
            detail=f"Document not found: {', '.join(missing)}",
        )
    return documents


def _with_relevant_memories(
    base_prompt: str,
    memory_store: MemoryStore,
    user_input: str,
) -> str:
    memory_block = build_memory_block(user_input, memory_store, top_k=3)
    if not memory_block:
        return base_prompt
    return f"{base_prompt}\n\n{memory_block}"


def _with_attached_documents(base_prompt: str, documents: list[Document]) -> str:
    if not documents:
        return base_prompt

    lines = [
        "[本轮上传文档]",
        "用户本轮消息附带了以下文档。需要读取正文时，请调用 read_docs，并优先使用 document_id 参数。",
    ]
    for doc in documents:
        lines.append(
            f"- document_id={doc.id} filename={doc.filename} "
            f"size={doc.size} content_type={doc.content_type}"
        )
    return base_prompt + "\n\n" + "\n".join(lines)


def _apply_event_to_display(event: dict, assistant_msg: dict) -> None:
    """将 SSE 事件反映到 assistant display 消息，供最终存储。"""
    t = event.get("type")
    if t == "thinking":
        prev = assistant_msg.get("thinking") or ""
        assistant_msg["thinking"] = prev + event.get("content", "")
    elif t == "tool_start":
        assistant_msg["tool_calls"].append(
            {
                "tool": event["tool"],
                "params": event.get("params", {}),
                "result": None,
            }
        )
    elif t == "tool_result":
        # 找最后一个匹配该工具名且 result 为 None 的记录
        for tc in reversed(assistant_msg["tool_calls"]):
            if tc["tool"] == event["tool"] and tc["result"] is None:
                tc["result"] = event.get("result", "")
                break
    elif t == "message":
        assistant_msg["content"] = event.get("content", "")
