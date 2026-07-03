from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from openai import AsyncOpenAI

from .api.routes import router
from .config import load_config
from .documents import DocumentStore
from .memory import MemoryStore
from .sessions.store import SessionStore

# 加载所有工具（触发注册），需在 app 初始化前完成
import app.tools  # noqa: F401  触发工具注册

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(application: FastAPI):
    """应用生命周期：启动时初始化 SessionStore 和 LLM Client。"""
    cfg = load_config()

    if not cfg.api_key:
        logger.warning(
            "API Key 未设置！请在 .env 文件中配置 %s_API_KEY。"
            "Agent 将无法调用 LLM，但其余接口正常。",
            cfg.provider.upper(),
        )

    application.state.session_store = SessionStore(cfg.data_dir / "sessions")
    application.state.memory_store = MemoryStore(cfg.data_dir / "memory")
    application.state.document_store = DocumentStore(cfg.data_dir / "doc")
    application.state.llm_client = AsyncOpenAI(
        api_key=cfg.api_key or "dummy-key",
        base_url=cfg.base_url,
    )
    application.state.model = cfg.model
    application.state.max_loop_iterations = cfg.max_loop_iterations

    logger.info(
        "Agent started — provider=%s model=%s max_iterations=%d",
        cfg.provider,
        cfg.model,
        cfg.max_loop_iterations,
    )
    yield
    logger.info("Agent shutting down.")

def create_app() -> FastAPI:
    cfg = load_config()

    application = FastAPI(
        title="Minimal Agent API",
        description="最小可用 Agent 系统后端（FastAPI + LLM Tool Use）",
        version="1.0.0",
        lifespan=lifespan,
    )

    application.add_middleware(
        CORSMiddleware,
        allow_origins=cfg.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    application.include_router(router)
    return application


app = create_app()
