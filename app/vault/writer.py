"""Vault 写入：Raw 原文存档 + Wiki 编译产物。"""
from __future__ import annotations

import re
from datetime import datetime
from pathlib import Path

from loguru import logger

from app.config import settings

from .frontmatter import dump_frontmatter

# area → Wiki 子目录映射（与 SCHEMA.md 保持一致）
_AREA_TO_SUBDIR = {
    "Concepts": "concepts",
    "Areas-AI": "entities",
    "Areas-Product": "entities",
    "Areas-Mgmt": "entities",
    "Archives": "entities",
}

_SLUG_STRIP = re.compile(r'[\\/:*?"<>|\r\n\t]+')
_SLUG_SPACE = re.compile(r"\s+")


def _slugify(title: str, max_len: int = 60) -> str:
    """生成文件名安全的 slug，保留中文。"""
    s = _SLUG_STRIP.sub("", title).strip()
    s = _SLUG_SPACE.sub("-", s)
    return s[:max_len] or "untitled"


def _vault_root() -> Path:
    root = Path(settings.vault_path)
    if not root.exists():
        raise RuntimeError(
            f"VAULT_PATH 不存在：{root}；请先按 docs/feishu-setup.md §2b 初始化 vault。"
        )
    return root


def _ensure_dir(p: Path) -> None:
    p.parent.mkdir(parents=True, exist_ok=True)


def write_raw(title: str, source_type: str, source_ref: str, text: str) -> Path:
    """写入 Raw 原文存档；返回相对于 vault 根的路径。"""
    root = _vault_root()
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    sub = {"url": "articles", "text": "notes", "file": "files"}.get(source_type, "notes")
    filename = f"{stamp}-{_slugify(title)}.md"
    path = root / "Raw" / sub / filename

    meta = {
        "title": title,
        "source_type": source_type,
        "source_ref": source_ref,
        "captured_at": datetime.now().isoformat(timespec="seconds"),
    }
    body = text if text.endswith("\n") else text + "\n"
    content = dump_frontmatter(meta) + "\n" + body

    _ensure_dir(path)
    path.write_text(content, encoding="utf-8")
    logger.info("vault.write_raw -> {}", path)
    return path.relative_to(root)


def write_wiki(
    *,
    title: str,
    area: str,
    tags: list[str],
    summary: str,
    source_ref: str,
    body_markdown: str,
) -> Path:
    """写入 Wiki 编译产物；返回相对于 vault 根的路径。"""
    root = _vault_root()
    sub = _AREA_TO_SUBDIR.get(area, "entities")
    filename = f"{_slugify(title)}.md"
    path = root / "Wiki" / sub / filename

    meta = {
        "title": title,
        "area": area,
        "tags": tags,
        "summary": summary,
        "source_ref": source_ref,
        "created_at": datetime.now().isoformat(timespec="seconds"),
    }
    body = body_markdown if body_markdown.endswith("\n") else body_markdown + "\n"
    content = dump_frontmatter(meta) + "\n" + body

    _ensure_dir(path)
    path.write_text(content, encoding="utf-8")
    logger.info("vault.write_wiki -> {}", path)
    return path.relative_to(root)
