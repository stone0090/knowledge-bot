"""Wiki Lint：扫描 Wiki 页面，报告 frontmatter 缺失 / 孤儿页 / 旧版 area 残留。

只读操作；返回人类可读的 Markdown 报告，用于飞书 /lint 命令回复。
"""
from __future__ import annotations

from pathlib import Path

from loguru import logger

from app.config import settings

from .frontmatter import split_frontmatter

# SCHEMA.md 规定的必填字段
_REQUIRED = ["type", "title", "created", "updated", "sources", "tags"]
# 允许的 type 值
_ALLOWED_TYPES = {"entity", "concept", "comparison", "query", "skill"}


def _vault_root() -> Path:
    return Path(settings.vault_path)


def lint_vault() -> dict:
    """返回 {'pages': N, 'issues': [...]} ；issues 是 (path, kind, detail) 三元组。"""
    root = _vault_root()
    wiki = root / "Wiki"
    if not wiki.exists():
        return {"pages": 0, "issues": []}

    issues: list[tuple[str, str, str]] = []
    pages = 0

    # index.md 里出现过的 [[title]]
    index_text = ""
    idx_path = root / "index.md"
    if idx_path.exists():
        index_text = idx_path.read_text(encoding="utf-8")

    for md in wiki.rglob("*.md"):
        if md.name == ".gitkeep":
            continue
        pages += 1
        rel = md.relative_to(root).as_posix()
        try:
            content = md.read_text(encoding="utf-8")
        except Exception as exc:  # noqa: BLE001
            issues.append((rel, "read_error", str(exc)))
            continue

        meta, _body = split_frontmatter(content)
        if not meta:
            issues.append((rel, "no_frontmatter", "frontmatter 缺失或解析失败"))
            continue

        # 必填字段
        missing = [k for k in _REQUIRED if k not in meta or meta.get(k) in (None, "", [])]
        if missing:
            issues.append((rel, "missing_fields", ", ".join(missing)))

        # type 值校验
        t = meta.get("type")
        if t and t not in _ALLOWED_TYPES:
            issues.append((rel, "bad_type", f"type={t} 不在 {sorted(_ALLOWED_TYPES)}"))

        # 旧版字段残留
        for legacy in ("area", "summary", "source_ref", "created_at"):
            if legacy in meta:
                issues.append((rel, "legacy_field", f"存在旧版字段 {legacy}"))

        # 孤儿页（不在 index.md 中）
        title = meta.get("title")
        if title and index_text and f"[[{title}]]" not in index_text:
            issues.append((rel, "orphan", f"未在 index.md 登记: [[{title}]]"))

    return {"pages": pages, "issues": issues}


def format_lint_report(result: dict) -> str:
    """把 lint_vault 结果渲染成 Markdown 报告。"""
    pages = result.get("pages", 0)
    issues = result.get("issues", [])

    if not issues:
        return f"✅ Lint 通过：扫描 {pages} 个 Wiki 页，无问题。"

    # 按 kind 归组
    by_kind: dict[str, list[tuple[str, str]]] = {}
    for path, kind, detail in issues:
        by_kind.setdefault(kind, []).append((path, detail))

    lines = [f"⚠️ Lint 报告：扫描 {pages} 页，发现 {len(issues)} 个问题。", ""]
    kind_titles = {
        "no_frontmatter": "缺 frontmatter",
        "missing_fields": "必填字段缺失",
        "bad_type": "type 值非法",
        "legacy_field": "遗留旧版字段",
        "orphan": "孤儿页（未入 index）",
        "read_error": "读取失败",
    }
    for kind, items in by_kind.items():
        lines.append(f"**{kind_titles.get(kind, kind)}** · {len(items)} 条")
        for path, detail in items[:10]:
            lines.append(f"- `{path}` — {detail}")
        if len(items) > 10:
            lines.append(f"- …… 省略 {len(items) - 10} 条")
        lines.append("")
    logger.info("lint_vault: {} pages / {} issues", pages, len(issues))
    return "\n".join(lines)
