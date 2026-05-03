"""解析派发：根据传入类型选择对应解析器。"""
from __future__ import annotations

import re
from dataclasses import dataclass

from .file_reader import parse_file_bytes
from .url_reader import fetch_url_as_markdown

URL_PATTERN = re.compile(r"https?://[^\s<>\"']+")


@dataclass
class ParsedContent:
    source_type: str       # "url" | "text" | "file"
    source_ref: str        # 原始 URL / 文件名 / "inline"
    text: str              # 转换后的纯文本 / Markdown


async def parse_text(text: str) -> ParsedContent:
    stripped = text.strip()
    match = URL_PATTERN.search(stripped)
    # 如果整段基本就是一个 URL，就走 URL 抓取；否则当纯文本
    if match and len(stripped) - len(match.group(0)) < 10:
        url = match.group(0)
        md = await fetch_url_as_markdown(url)
        return ParsedContent(source_type="url", source_ref=url, text=md)
    return ParsedContent(source_type="text", source_ref="inline", text=stripped)


def parse_file(data: bytes, filename: str) -> ParsedContent:
    suffix = "." + filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    text = parse_file_bytes(data, suffix)
    return ParsedContent(source_type="file", source_ref=filename, text=text)


async def parse_any(*, text: str | None = None, file: tuple[bytes, str] | None = None) -> ParsedContent:
    if file is not None:
        return parse_file(file[0], file[1])
    if text is not None:
        return await parse_text(text)
    raise ValueError("parse_any: 需要提供 text 或 file")
