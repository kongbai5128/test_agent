"""
read_docs 工具 — 读取工作区内文档/代码文件内容。

特性：
- 支持按行读取（start_line / end_line）
- 限制在项目根目录内，防止路径穿越
- 支持相对路径与绝对路径
- 限制最大读取行数，避免上下文爆炸
"""
from __future__ import annotations

from pathlib import Path

from .registry import ToolSpec, register

# 项目根目录：.../back_end
PROJECT_ROOT = Path(__file__).resolve().parents[2]
MAX_READ_LINES = 400


def _normalize_target(path_str: str) -> Path:
    if not path_str:
        raise ValueError("path 不能为空")

    p = Path(path_str)
    if not p.is_absolute():
        p = PROJECT_ROOT / p

    p = p.resolve()

    # 防止读取项目外文件
    try:
        p.relative_to(PROJECT_ROOT)
    except ValueError as exc:
        raise ValueError("不允许读取项目根目录之外的文件") from exc

    return p


def _read_docs(params: dict) -> str:
    path_str = str(params.get("path", "")).strip()
    start_line = int(params.get("start_line", 1))
    end_line_raw = params.get("end_line", None)

    if start_line < 1:
        return "错误：start_line 必须 >= 1"

    target = _normalize_target(path_str)

    if not target.exists():
        return f"错误：文件不存在 -> {target}"
    if not target.is_file():
        return f"错误：目标不是文件 -> {target}"

    try:
        text = target.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        return "错误：仅支持 UTF-8 文本文件"
    except Exception as exc:
        return f"错误：读取文件失败 -> {exc}"

    lines = text.splitlines()
    total = len(lines)

    if total == 0:
        return f"文件为空：{target.relative_to(PROJECT_ROOT)}"

    if end_line_raw is None:
        end_line = min(start_line + MAX_READ_LINES - 1, total)
    else:
        end_line = int(end_line_raw)

    if end_line < start_line:
        return "错误：end_line 必须 >= start_line"

    # 限制单次最大读取行数
    if end_line - start_line + 1 > MAX_READ_LINES:
        end_line = start_line + MAX_READ_LINES - 1

    if start_line > total:
        return f"错误：start_line 超出文件行数（总行数 {total}）"

    end_line = min(end_line, total)

    selected = lines[start_line - 1 : end_line]

    header = (
        f"文件: {target.relative_to(PROJECT_ROOT)}\n"
        f"行范围: {start_line}-{end_line}（总行数 {total}）\n"
        "---"
    )
    body = "\n".join(selected)
    return f"{header}\n{body}"


recals hgister(
    ToolSpec(
        name="read_docs",
        description=(
            "读取项目内的文档或代码文件内容。可指定路径与行范围，"
            "适合读取 README、接口文档、配置文件和源码片段。"
        ),
        parameters={
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": (
                        "要读取的文件路径。支持相对路径（相对 back_end 根目录）"
                        "或绝对路径。"
                    ),
                },
                "start_line": {
                    "type": "integer",
                    "description": "起始行（从 1 开始），默认 1",
                    "default": 1,
                },
                "end_line": {
                    "type": "integer",
                    "description": "结束行（包含），默认读取到 start_line 后最多 400 行",
                },
            },
            "required": ["path"],
        },
        handler=_read_docs,
    )
)
