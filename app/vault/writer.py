"""Vault 写入：Raw 原文存档 + Wiki 编译产物。

frontmatter 对齐 SCHEMA.md：
- Raw：source_type / source_ref / ingested
- Wiki：type / title / aliases / created / updated / sources / tags / confidence
"""
from __future__ import annotations

import re
from datetime import date, datetime
from pathlib import Path

from loguru import logger

from app.config import settings

from .frontmatter import dump_frontmatter

# type → Wiki 子目录（SCHEMA.md 契约）
_TYPE_TO_SUBDIR = {
    "entity": "entities",
    "concept": "concepts",
    "comparison": "comparisons",
    "query": "queries",
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
    sub = {
        "url": "articles",
        "text": "notes",
        "file": "files",
        "transcript": "transcripts",
        "paper": "papers",
    }.get(source_type, "notes")
    filename = f"{stamp}-{_slugify(title)}.md"
    path = root / "Raw" / sub / filename

    meta = {
        "source_type": source_type,
        "source_ref": source_ref,
        "title": title,
        "ingested": datetime.now().isoformat(timespec="seconds"),
    }
    body = text if text.endswith("\n") else text + "\n"
    content = dump_frontmatter(meta) + "\n" + body

    _ensure_dir(path)
    path.write_text(content, encoding="utf-8")
    logger.info("vault.write_raw -> {}", path)
    return path.relative_to(root)


def write_wiki(
    *,
    type: str,
    title: str,
    tags: list[str],
    summary: str,
    source_ref: str,
    body_markdown: str,
    aliases: list[str] | None = None,
    confidence: str = "medium",
) -> Path:
    """写入 Wiki 编译产物；返回相对于 vault 根的路径。

    - type: entity | concept | comparison | query。
    - 分路径按 SCHEMA.md；summary 不写入 frontmatter（已在正文「摘要」块）。
    """
    root = _vault_root()
    sub = _TYPE_TO_SUBDIR.get(type, "entities")
    filename = f"{_slugify(title)}.md"
    path = root / "Wiki" / sub / filename

    today = date.today().isoformat()
    meta: dict = {
        "type": type,
        "title": title,
        "aliases": aliases or [],
        "tags": tags,
        "created": today,
        "updated": today,
        "sources": [source_ref] if source_ref else [],
        "confidence": confidence,
    }
    body = body_markdown if body_markdown.endswith("\n") else body_markdown + "\n"
    content = dump_frontmatter(meta) + "\n" + body

    _ensure_dir(path)
    path.write_text(content, encoding="utf-8")
    logger.info("vault.write_wiki -> {} (type={})", path, type)
    return path.relative_to(root)


def write_query(question: str, answer_md: str, candidates: list[str] | None = None) -> Path:
    """/查 结果回填 Wiki/queries/；返回相对路径。

    文件名加 时间戳 前缀便于按日期检索，不覆盖旧档。
    """
    root = _vault_root()
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    filename = f"{stamp}-{_slugify(question, max_len=40)}.md"
    path = root / "Wiki" / "queries" / filename

    today = date.today().isoformat()
    meta = {
        "type": "query",
        "title": question[:40],
        "question": question,
        "tags": ["meta/query"],
        "created": today,
        "updated": today,
        "sources": candidates or [],
    }
    body_lines = [f"# {question}", "", "## 答复", answer_md.rstrip()]
    if candidates:
        body_lines += ["", "## 候选证据"]
        body_lines += [f"- {c}" for c in candidates]
    body = "\n".join(body_lines) + "\n"
    content = dump_frontmatter(meta) + "\n" + body

    _ensure_dir(path)
    path.write_text(content, encoding="utf-8")
    logger.info("vault.write_query -> {}", path)
    return path.relative_to(root)
