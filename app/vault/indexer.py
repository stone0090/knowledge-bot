"""Wiki index.md / log.md 自动维护。

设计约定（见 SCHEMA.md §Session Orientation）：
- index.md：按 type 分组的全量导航；不去重，允许多行指向同一页（后续由 lint 报告）。
- log.md：倒序时间线，每次 ingest/query 追加一行。
"""
from __future__ import annotations

from datetime import date, datetime
from pathlib import Path

from loguru import logger

from app.config import settings

_TYPE_HEADING = {
    "entity": "## Entities",
    "concept": "## Concepts",
    "comparison": "## Comparisons",
    "query": "## Queries",
    "skill": "## Skills",
}

_INDEX_TEMPLATE = """# Wiki 索引

> 本文件由 knowledge-bot 自动维护。方法论见仓库 `docs/llm-wiki-method.md`，运行契约见同级 `SCHEMA.md`。

## Entities

## Concepts

## Comparisons

## Queries

## Skills
"""

_LOG_TEMPLATE = """# 变更日志

> 由 `app/vault/indexer.py` 自动追加。倒序排列（新在上）。
"""


def _vault_root() -> Path:
    return Path(settings.vault_path)


def _ensure_index(path: Path) -> None:
    if not path.exists():
        path.write_text(_INDEX_TEMPLATE, encoding="utf-8")


def _ensure_log(path: Path) -> None:
    if not path.exists():
        path.write_text(_LOG_TEMPLATE, encoding="utf-8")


def append_index(type: str, title: str, summary: str = "") -> None:
    """把一条 `- [[title]] — summary` 追加到 index.md 对应 type 分组段末尾。

    去重策略：若已存在完全相同的 `[[title]]` 行则跳过。
    """
    path = _vault_root() / "index.md"
    _ensure_index(path)
    heading = _TYPE_HEADING.get(type, "## Entities")
    entry = f"- [[{title}]]" + (f" — {summary}" if summary else "")

    text = path.read_text(encoding="utf-8")
    if f"[[{title}]]" in text:
        logger.debug("index.md already has [[{}]], skip", title)
        return

    lines = text.splitlines()
    out: list[str] = []
    inserted = False
    i = 0
    while i < len(lines):
        out.append(lines[i])
        if not inserted and lines[i].strip() == heading:
            # 把新条目插到下一个 "## " 之前
            j = i + 1
            # 跳过紧随的空行
            while j < len(lines) and not lines[j].strip():
                out.append(lines[j])
                j += 1
            # 找到该分组结束位置（下一个 ## 或文末）
            section_end = j
            while section_end < len(lines) and not lines[section_end].startswith("## "):
                out.append(lines[section_end])
                section_end += 1
            out.append(entry)
            i = section_end
            inserted = True
            continue
        i += 1

    if not inserted:
        # 没找到对应 heading，直接在文末新增一段
        out.append("")
        out.append(heading)
        out.append("")
        out.append(entry)

    path.write_text("\n".join(out) + "\n", encoding="utf-8")
    logger.info("indexer.append_index -> {} ({})", title, type)


def append_log(type: str, title: str, wiki_path: str) -> None:
    """把一条时间线条目前置到 log.md（新在上）。"""
    path = _vault_root() / "log.md"
    _ensure_log(path)

    stamp = datetime.now().strftime("%Y-%m-%d %H:%M")
    today_heading = f"## {date.today().isoformat()}"
    entry = f"- [{stamp}] `{type}` [[{title}]] — `{wiki_path}`"

    text = path.read_text(encoding="utf-8")
    lines = text.splitlines()

    # 找到第一个 "## " 行位置
    first_section = next((i for i, l in enumerate(lines) if l.startswith("## ")), None)

    if first_section is not None and lines[first_section] == today_heading:
        # 今天已有段落，插到段落标题之后
        insert_at = first_section + 1
        lines.insert(insert_at, entry)
    else:
        # 新建今日段落，放在 frontmatter/说明文字之后、历史段落之前
        insert_at = first_section if first_section is not None else len(lines)
        new_block = [today_heading, "", entry, ""]
        for idx, row in enumerate(new_block):
            lines.insert(insert_at + idx, row)

    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    logger.info("indexer.append_log -> {} ({})", title, type)


def remove_from_index(title: str) -> bool:
    """从 index.md 中删除含 `[[title]]` 的条目行。

    任意包含 `[[title]]` 的整行都会被移除（包括重复条目）。
    返回是否实际删除了至少一行。
    """
    path = _vault_root() / "index.md"
    if not path.exists():
        return False
    text = path.read_text(encoding="utf-8")
    needle = f"[[{title}]]"
    if needle not in text:
        return False
    lines = text.splitlines()
    kept = [ln for ln in lines if needle not in ln]
    if len(kept) == len(lines):
        return False
    path.write_text("\n".join(kept) + "\n", encoding="utf-8")
    logger.info("indexer.remove_from_index -> {}", title)
    return True
