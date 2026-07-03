from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

from dotenv import load_dotenv



_PROVIDERS = {
    "deepseek": {
        "base_url": "https://api.deepseek.com",
        "api_key_env": "DEEPSEEK_API_KEY",
        "default_model": "deepseek-chat",
        "context_window": 64_000,
    },
    "openai": {
        "base_url": "https://api.openai.com/v1",
        "api_key_env": "OPENAI_API_KEY",
        "default_model": "gpt-4o-mini",
        "context_window": 128_000,
    },
    "anthropic": {
        "base_url": "https://api.anthropic.com/v1",
        "api_key_env": "ANTHROPIC_API_KEY",
        "default_model": "claude-haiku-3-5",
        "context_window": 200_000,
    },
}


def _detect_provider() -> str:
    if os.environ.get("DEEPSEEK_API_KEY"):
        return "deepseek"
    if os.environ.get("OPENAI_API_KEY"):
        return "openai"
    if os.environ.get("ANTHROPIC_API_KEY"):
        return "anthropic"
    return "deepseek"


@dataclass
class Config:
    provider: str
    base_url: str
    api_key: str
    model: str
    context_window: int
    cors_origins: list[str]
    max_loop_iterations: int
    data_dir: Path


def load_config() -> Config:
    # provider = os.environ.get("LLM_PROVIDER") or _detect_provider()
    provider = _detect_provider()
    cfg = _PROVIDERS.get(provider)
    if not cfg:
        raise ValueError(f"未知 provider: {provider}，可选: {list(_PROVIDERS)}")

    api_key = os.environ.get(cfg["api_key_env"], "")
    model = os.environ.get("LLM_MODEL", cfg["default_model"])

    cors_raw = os.environ.get("CORS_ORIGINS", "http://localhost:5173")
    cors_origins = [o.strip() for o in cors_raw.split(",") if o.strip()]

    max_loop = int(os.environ.get("MAX_LOOP_ITERATIONS", "10"))
    data_dir = Path(os.environ.get("DATA_DIR", "./data"))

    return Config(
        provider=provider,
        base_url=cfg["base_url"],
        api_key=api_key,
        model=model,
        context_window=cfg["context_window"],
        cors_origins=cors_origins,
        max_loop_iterations=max_loop,
        data_dir=data_dir,
    )
