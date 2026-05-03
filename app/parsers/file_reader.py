"""文件解析：PDF / PPT / Excel / Word / 图片 OCR → 纯文本。

依赖 `markitdown`（微软开源，底层集成多种格式）。
"""
from __future__ import annotations

import tempfile
from pathlib import Path

from loguru import logger


def parse_file_bytes(data: bytes, suffix: str) -> str:
    """把二进制文件落盘到临时文件，用 markitdown 转成纯文本。

    suffix 需包含点号，例如 ".pdf"。
    """
    try:
        from markitdown import MarkItDown
    except ImportError as exc:  # pragma: no cover
        raise RuntimeError("markitdown 未安装，请执行 pip install markitdown") from exc

    with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
        tmp.write(data)
        path = Path(tmp.name)

    try:
        md = MarkItDown()
        result = md.convert(str(path))
        text = getattr(result, "text_content", "") or ""
        if not text:
            logger.warning("markitdown returned empty content for {}", suffix)
        return text
    finally:
        try:
            path.unlink()
        except OSError:
            pass
