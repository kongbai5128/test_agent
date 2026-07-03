"""
read_docs 工具 — 读取工作区内的 PDF、Word 和文本类文档。

支持格式：
- PDF: .pdf（依赖 pypdf）
- Word: .docx（使用标准库解析 OOXML），.doc 可在系统安装 antiword 时读取
- 文本: .txt/.md/.csv/.json/.py/.ts/.vue 等 UTF-8/GB18030 文本文件
"""
from __future__ import annotations

import shutil
import subprocess
import zipfile
from pathlib import Path
from typing import Any
from xml.etree import ElementTree

from .registry import ToolSpec, register

# 项目根目录：.../厦门光辰智能科技-agent简单搭建
PROJECT_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_MAX_CHARS = 12_000
MAX_CHARS_LIMIT = 50_000
DEFAULT_MAX_PDF_PAGES = 20

TEXT_SUFFIXES = {
    "",
    ".txt",
    ".md",
    ".markdown",
    ".csv",
    ".tsv",
    ".json",
    ".jsonl",
    ".yaml",
    ".yml",
    ".toml",
    ".ini",
    ".cfg",
    ".conf",
    ".log",
    ".py",
    ".js",
    ".ts",
    ".tsx",
    ".jsx",
    ".vue",
    ".html",
    ".htm",
    ".css",
    ".scss",
    ".sql",
    ".sh",
    ".bat",
    ".ps1",
    ".xml",
}


def _normalize_target(path_str: str) -> Path:
    if not path_str:
        raise ValueError("path 不能为空")

    path = Path(path_str)
    if not path.is_absolute():
        path = PROJECT_ROOT / path

    path = path.resolve()

    try:
        path.relative_to(PROJECT_ROOT)
    except ValueError as exc:
        raise ValueError("不允许读取项目根目录之外的文件") from exc

    return path


def _resolve_target(params: dict, context: Any = None) -> Path:
    document_id = str(params.get("document_id", "")).strip()
    if document_id:
        if context is None or getattr(context, "document_store", None) is None:
            raise ValueError("document_id 只能在会话工具调用中使用")
        return context.document_store.resolve_path(context.session_id, document_id)

    path_str = str(params.get("path", "")).strip()
    if not path_str:
        raise ValueError("请提供 path 或 document_id")
    return _normalize_target(path_str)


def _int_param(
    params: dict,
    name: str,
    default: int,
    *,
    minimum: int = 1,
    maximum: int | None = None,
) -> int:
    raw = params.get(name, default)
    if raw is None:
        raw = default
    try:
        value = int(raw)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{name} 必须是整数") from exc

    if value < minimum:
        raise ValueError(f"{name} 必须 >= {minimum}")
    if maximum is not None and value > maximum:
        value = maximum
    return value


def _optional_int(params: dict, name: str, *, minimum: int = 1) -> int | None:
    raw = params.get(name)
    if raw in (None, ""):
        return None
    try:
        value = int(raw)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{name} 必须是整数") from exc
    if value < minimum:
        raise ValueError(f"{name} 必须 >= {minimum}")
    return value


def _relative(path: Path) -> str:
    try:
        return str(path.relative_to(PROJECT_ROOT))
    except ValueError:
        return str(path)


def _read_text_file(path: Path) -> str:
    data = path.read_bytes()
    if b"\x00" in data[:4096]:
        raise ValueError("文件看起来是二进制内容，不适合作为文本读取")

    for encoding in ("utf-8-sig", "utf-8", "gb18030"):
        try:
            return data.decode(encoding)
        except UnicodeDecodeError:
            continue
    raise ValueError("无法按 UTF-8 或 GB18030 解码该文本文件")


def _read_pdf(path: Path, params: dict) -> tuple[str, list[str]]:
    try:
        from pypdf import PdfReader
    except ImportError as exc:
        raise ValueError("读取 PDF 需要安装依赖 pypdf：pip install pypdf") from exc

    reader = PdfReader(str(path))
    if reader.is_encrypted:
        try:
            reader.decrypt("")
        except Exception as exc:
            raise ValueError("PDF 已加密，无法读取文本") from exc

    total_pages = len(reader.pages)
    if total_pages == 0:
        return "", [f"页范围: 0-0（总页数 0）"]

    start_page = _int_param(params, "start_page", 1, minimum=1)
    if start_page > total_pages:
        raise ValueError(f"start_page 超出 PDF 页数（总页数 {total_pages}）")

    end_page = _optional_int(params, "end_page", minimum=start_page)
    if end_page is None:
        end_page = min(start_page + DEFAULT_MAX_PDF_PAGES - 1, total_pages)
    else:
        end_page = min(end_page, total_pages)

    parts: list[str] = []
    for page_no in range(start_page, end_page + 1):
        page = reader.pages[page_no - 1]
        try:
            page_text = page.extract_text() or ""
        except Exception as exc:
            page_text = f"[第 {page_no} 页文本提取失败：{exc}]"
        if page_text.strip():
            parts.append(f"--- 第 {page_no} 页 ---\n{page_text.strip()}")

    meta = [f"页范围: {start_page}-{end_page}（总页数 {total_pages}）"]
    if end_page < total_pages and params.get("end_page") is None:
        meta.append(f"提示: 默认最多读取 {DEFAULT_MAX_PDF_PAGES} 页，可用 end_page 指定更多页")
    return "\n\n".join(parts), meta


def _read_docx(path: Path) -> str:
    try:
        with zipfile.ZipFile(path) as archive:
            xml = archive.read("word/document.xml")
    except KeyError as exc:
        raise ValueError("DOCX 缺少 word/document.xml，文件可能损坏") from exc
    except zipfile.BadZipFile as exc:
        raise ValueError("DOCX 文件损坏或不是有效的 Word 文档") from exc

    root = ElementTree.fromstring(xml)
    ns = {"w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main"}
    paragraphs: list[str] = []

    for paragraph in root.findall(".//w:p", ns):
        chunks: list[str] = []
        for node in paragraph.iter():
            if node.tag == f"{{{ns['w']}}}t" and node.text:
                chunks.append(node.text)
            elif node.tag == f"{{{ns['w']}}}tab":
                chunks.append("\t")
            elif node.tag in {f"{{{ns['w']}}}br", f"{{{ns['w']}}}cr"}:
                chunks.append("\n")
        text = "".join(chunks).strip()
        if text:
            paragraphs.append(text)

    return "\n".join(paragraphs)


def _read_doc(path: Path) -> str:
    antiword = shutil.which("antiword")
    if antiword is None:
        raise ValueError("旧版 .doc 需要系统安装 antiword，或先转换为 .docx 后读取")

    result = subprocess.run(
        [antiword, str(path)],
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    if result.returncode != 0:
        detail = result.stderr.strip() or result.stdout.strip() or "antiword 读取失败"
        raise ValueError(detail)
    return result.stdout


def _select_lines(text: str, params: dict) -> tuple[str, list[str]]:
    start_line = _int_param(params, "start_line", 1, minimum=1)
    end_line = _optional_int(params, "end_line", minimum=start_line)

    lines = text.splitlines()
    total = len(lines)
    if total == 0:
        return "", [f"行范围: 0-0（总行数 0）"]
    if start_line > total:
        raise ValueError(f"start_line 超出文本行数（总行数 {total}）")

    if end_line is None:
        end_line = total
    else:
        end_line = min(end_line, total)

    selected = lines[start_line - 1 : end_line]
    return "\n".join(selected), [f"行范围: {start_line}-{end_line}（总行数 {total}）"]


def _limit_chars(text: str, max_chars: int) -> tuple[str, bool]:
    if len(text) <= max_chars:
        return text, False
    return text[:max_chars].rstrip(), True


def _extract_text(path: Path, params: dict) -> tuple[str, str, list[str]]:
    suffix = path.suffix.lower()

    if suffix == ".pdf":
        text, meta = _read_pdf(path, params)
        return text, "PDF", meta
    if suffix == ".docx":
        return _read_docx(path), "Word DOCX", []
    if suffix == ".doc":
        return _read_doc(path), "Word DOC", []
    if suffix in TEXT_SUFFIXES:
        return _read_text_file(path), "文本", []

    raise ValueError(
        f"不支持的文件类型：{suffix or '(无扩展名)'}。"
        "当前支持 pdf、docx、doc（需 antiword）和常见文本文件。"
    )


def _read_docs(params: dict, context: Any = None) -> str:
    try:
        path = _resolve_target(params, context)
        max_chars = _int_param(
            params,
            "max_chars",
            DEFAULT_MAX_CHARS,
            minimum=500,
            maximum=MAX_CHARS_LIMIT,
        )
    except ValueError as exc:
        return f"错误：{exc}"

    if not path.exists():
        return f"错误：文件不存在 -> {path}"
    if not path.is_file():
        return f"错误：目标不是文件 -> {path}"

    try:
        text, doc_type, meta = _extract_text(path, params)
        text, line_meta = _select_lines(text, params)
        meta.extend(line_meta)
        text, truncated = _limit_chars(text, max_chars)
    except ValueError as exc:
        return f"错误：{exc}"
    except Exception as exc:
        return f"错误：读取文档失败 -> {exc}"

    if not text.strip():
        return f"文件未提取到可读文本：{_relative(path)}"

    header = [
        f"文件: {_relative(path)}",
        f"类型: {doc_type}",
        *meta,
        f"字符限制: {max_chars}" + ("（已截断）" if truncated else ""),
        "---",
    ]
    return "\n".join(header + [text])


register(
    ToolSpec(
        name="read_docs",
        description=(
            "读取工作区内的 PDF、Word 或文本文件内容。支持 pdf、docx、"
            "旧 doc（系统需安装 antiword）以及 txt/md/json/代码等文本文件。"
        ),
        parameters={
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": (
                        "要读取的文件路径。支持相对路径（相对项目根目录）"
                        "或项目内绝对路径。若有 document_id，优先使用 document_id。"
                    ),
                },
                "document_id": {
                    "type": "string",
                    "description": "已上传文档 ID，例如 doc-xxxxxxxxxx。用于读取用户本轮或本会话上传的文件。",
                },
                "start_line": {
                    "type": "integer",
                    "description": "起始行（从 1 开始），默认 1。PDF/Word 会先提取文本再按行截取。",
                    "default": 1,
                },
                "end_line": {
                    "type": "integer",
                    "description": "结束行（包含）。默认读取到文档末尾，但仍受 max_chars 限制。",
                },
                "start_page": {
                    "type": "integer",
                    "description": "PDF 起始页（从 1 开始），仅对 PDF 生效，默认 1。",
                    "default": 1,
                },
                "end_page": {
                    "type": "integer",
                    "description": (
                        "PDF 结束页（包含），仅对 PDF 生效。默认最多读取起始页后的 20 页。"
                    ),
                },
                "max_chars": {
                    "type": "integer",
                    "description": "最多返回字符数，默认 12000，最大 50000。",
                    "default": DEFAULT_MAX_CHARS,
                },
            },
        },
        handler=_read_docs,
    )
)
