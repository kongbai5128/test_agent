from __future__ import annotations

import json
import logging
import uuid
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import StreamingResponse
from openai import AsyncOpenAI
from pydantic import BaseModel, Field

from ..agent.loop import run_agent_loop
from ..agent.system_prompt import SYSTEM_PROMPT
from ..context import manager as ctx_manager
from ..sessions.store import Session, SessionStore

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api")


# ── 依赖注入 ───────────────────────────────────────────────────

def get_store(request: Request) -> SessionStore:
    return request.app.state.session_store


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
    message: str = Field(min_length=1, max_length=8000)


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
):
    if not store.delete(session_id):
        raise HTTPException(status_code=404, detail="Session not found")


# ── Chat 路由（SSE 流式）──────────────────────────────────────

@router.post("/sessions/{session_id}/chat/stream")
async def chat_stream(
    session_id: str,
    body: ChatRequest,
    store: SessionStore = Depends(get_store),
    client: AsyncOpenAI = Depends(get_client),
    model: str = Depends(get_model),
    max_iter: int = Depends(get_max_iter),
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

    async def event_generator():
        try:
            async for event in run_agent_loop(
                session_id=session_id,
                user_input=user_input,
                raw_messages=raw_messages,
                system_prompt=SYSTEM_PROMPT,
                client=client,
                model=model,
                max_iterations=max_iter,
                session_store=store,
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
