from __future__ import annotations

import inspect
import logging
from dataclasses import dataclass
from typing import Any, Callable

logger = logging.getLogger(__name__)

# ── 工具 Spec ──────────────────────────────────────────────────


@dataclass
class ToolSpec:
    """描述一个工具的完整规格，LLM 基于此自主决策是否调用。"""

    name: str
    description: str
    parameters: dict  # JSON Schema（OpenAI function calling 格式）
    handler: Callable[[dict, Any], str]


# ── 全局注册表 ────────────────────────────────────────────────

_REGISTRY: dict[str, ToolSpec] = {}


def register(spec: ToolSpec) -> None:
    _REGISTRY[spec.name] = spec
    logger.debug("Tool registered: %s", spec.name)


def get_tool(name: str) -> ToolSpec | None:
    return _REGISTRY.get(name)


def all_tools() -> list[ToolSpec]:
    return list(_REGISTRY.values())


def to_openai_tools() -> list[dict]:
    """转为 OpenAI function calling 的 tools 数组格式。"""
    return [
        {
            "type": "function",
            "function": {
                "name": spec.name,
                "description": spec.description,
                "parameters": spec.parameters,
            },
        }
        for spec in _REGISTRY.values()
    ]


def execute(name: str, params: dict, context: Any = None) -> str:
    """
    执行指定工具，捕获所有异常并以字符串形式返回。
    context 携带 session_id 等运行时信息，供需要会话隔离的工具使用。
    """
    spec = get_tool(name)
    if spec is None:
        return f"错误：未知工具 '{name}'"

    try:
        sig = inspect.signature(spec.handler)
        if len(sig.parameters) >= 2:
            return spec.handler(params, context)
        return spec.handler(params)
    except Exception as exc:
        logger.error("Tool '%s' raised an error: %s", name, exc, exc_info=True)
        return f"工具 '{name}' 执行出错: {exc}"
