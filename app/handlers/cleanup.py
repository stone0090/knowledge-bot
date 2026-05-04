"""`/del` 与 `/archive` 命令：按 Wiki 页标题清理 Vault。

匹配策略：扫 Wiki/**/*.md 的 frontmatter.title，精确匹配（去空格）。
找不到时列出候选（前缀匹配）。找到时：
- /archive：mv Wiki 页 + sources 里的 Raw 文件 → `_archive/<原相对路径>`
- /del    ：rm Wiki 页 + sources 里的 Raw 文件
两者都：从 index.md 移除条目、log.md 追加事件、commit && push。
"""
from __future__ import annotations

import asyncio
import shutil
from pathlib import Path

from loguru import logger

from app.config import settings
from app.feishu import get_feishu_client
from app.vault import (
    append_log,
    commit_and_push,
    remove_from_index,
    split_frontmatter,
)


def _vault_root() -> Path:
    return Path(settings.vault_path)


def _iter_wiki_pages() -> list[Path]:
    wiki = _vault_root() / "Wiki"
    if not wiki.is_dir():
        return []
    return sorted(wiki.rglob("*.md"))


def _find_page(title: str) -> tuple[Path | None, dict, list[str]]:
    """按 title 精确匹配；返回 (匹配路径, frontmatter, 候选标题)。"""
    target = title.strip()
    exact: Path | None = None
    exact_meta: dict = {}
    candidates: list[str] = []
    for page in _iter_wiki_pages():
        try:
            meta, _ = split_frontmatter(page.read_text(encoding="utf-8"))
        except Exception:
            continue
        page_title = str(meta.get("title") or "").strip()
        if not page_title:
            continue
        if page_title == target:
            exact = page
            exact_meta = meta
            break
        if target and target.lower() in page_title.lower():
            candidates.append(page_title)
    return exact, exact_meta, candidates


def _resolve_sources(meta: dict) -> list[Path]:
    """读 frontmatter.sources，返回存在的 Raw 绝对路径列表。"""
    sources = meta.get("sources") or []
    if isinstance(sources, str):
        sources = [sources]
    root = _vault_root()
    paths: list[Path] = []
    for ref in sources:
        rel = str(ref).strip()
        if not rel or not rel.startswith("Raw/"):
            continue
        p = root / rel
        if p.exists():
            paths.append(p)
    return paths


def _archive_move(src: Path) -> Path:
    """把 vault 内的文件 mv 到 `_archive/<原相对路径>`，保留目录结构。"""
    root = _vault_root()
    rel = src.relative_to(root)
    dst = root / "_archive" / rel
    dst.parent.mkdir(parents=True, exist_ok=True)
    if dst.exists():
        dst.unlink()
    shutil.move(str(src), str(dst))
    return dst


def _do_cleanup(title: str, mode: str) -> dict:
    """执行一次 /del 或 /archive；返回结果摘要供飞书回复。

    mode in {"delete", "archive"}
    """
    page, meta, candidates = _find_page(title)
    if page is None:
        return {
            "ok": False,
            "title": title,
            "reason": "not_found",
            "candidates": candidates[:5],
        }

    root = _vault_root()
    wiki_rel = str(page.relative_to(root)).replace("\\", "/")
    raw_paths = _resolve_sources(meta)

    moved: list[str] = []  # for archive
    removed: list[str] = []  # for delete

    targets = [page] + raw_paths
    for t in targets:
        rel = str(t.relative_to(root)).replace("\\", "/")
        if mode == "archive":
            _archive_move(t)
            moved.append(rel)
        else:
            t.unlink()
            removed.append(rel)

    # 索引与日志
    remove_from_index(title)
    log_type = "archived" if mode == "archive" else "deleted"
    append_log(log_type, title, wiki_rel)

    # 提交推送
    msg_action = "archive" if mode == "archive" else "delete"
    pushed = commit_and_push(f"{msg_action}: {title}")

    return {
        "ok": True,
        "title": title,
        "wiki": wiki_rel,
        "moved": moved,
        "removed": removed,
        "pushed": pushed,
    }


def _format_reply(mode: str, result: dict) -> str:
    action = "归档" if mode == "archive" else "删除"
    if not result.get("ok"):
        reason = result.get("reason")
        if reason == "not_found":
            cand = result.get("candidates") or []
            if cand:
                cand_md = "\n".join(f"- {c}" for c in cand)
                return (
                    f"未找到标题为「{result['title']}」的 Wiki 页。\n"
                    f"候选（包含关键词）：\n{cand_md}"
                )
            return f"未找到标题为「{result['title']}」的 Wiki 页。"
        return f"{action}失败：{reason}"

    if mode == "archive":
        items = result.get("moved") or []
        header = f"✅ 已归档「{result['title']}」 → `_archive/`"
    else:
        items = result.get("removed") or []
        header = f"✅ 已删除「{result['title']}」"

    body = "\n".join(f"- `{p}`" for p in items)
    push_note = "" if result.get("pushed") else "\n\n⚠️ commit 已落盘但 push 未成功，稍后会自动重试。"
    return f"{header}\n{body}{push_note}"


async def handle_delete(text: str, reply_message_id: str) -> None:
    """飞书 `/del <标题>` / `/delete <标题>` 入口。"""
    title = _strip_prefix(text, ("/delete", "/del"))
    await _cleanup_and_reply(title, mode="delete", reply_message_id=reply_message_id)


async def handle_archive(text: str, reply_message_id: str) -> None:
    """飞书 `/archive <标题>` 入口。"""
    title = _strip_prefix(text, ("/archive",))
    await _cleanup_and_reply(title, mode="archive", reply_message_id=reply_message_id)


def _strip_prefix(text: str, prefixes: tuple[str, ...]) -> str:
    s = text.strip()
    for p in prefixes:
        if s.startswith(p):
            return s[len(p):].strip()
    return s


async def _cleanup_and_reply(title: str, *, mode: str, reply_message_id: str) -> None:
    client = get_feishu_client()
    if not title:
        await client.reply_text(
            reply_message_id,
            f"用法：`/{mode[:3] if mode == 'delete' else mode} <Wiki 页标题>`",
        )
        return
    try:
        result = await asyncio.to_thread(_do_cleanup, title, mode)
    except Exception as exc:
        logger.exception("cleanup failed: {}", exc)
        await client.reply_text(reply_message_id, f"{mode} 失败: {exc}")
        return
    await client.reply_text(reply_message_id, _format_reply(mode, result))
