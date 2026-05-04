"""`/del` 与 `/archive` 命令：按 Wiki 页标题 / 文件名 / Vault 相对路径清理 Vault。

匹配策略（依次尝试）：
1. Wiki 页 frontmatter.title 全等 / normalize 后相等
2. Wiki 页文件名 stem normalize 后相等
3. Wiki 相对路径（`Wiki/entities/xxx.md` 或 `entities/xxx.md` 或裸 `xxx.md`）
4. Raw 相对路径（`Raw/notes/xxx.md` 或 `notes/xxx`）→ 反查 sources 引用该 Raw 的 Wiki 页
5. Raw 孤儿（没有任何 Wiki 引用）→ 走“只处理 Raw”分支

normalize: lower + 连字符/下划线计作空格 + 历缩空白。
找不到时列出模糊候选协助介用户手动替换。
"""
from __future__ import annotations

import asyncio
import re
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


def _norm(s: str) -> str:
    """规范化字符串：小写 + 连字符/下划线 → 空格 + 历缩空白。用于 title/stem 对比。"""
    if not s:
        return ""
    s = str(s).lower().replace("-", " ").replace("_", " ")
    return re.sub(r"\s+", " ", s).strip()


def _path_candidates(query: str) -> list[str]:
    """将用户输入展开为候选 vault 相对路径列表（未过滤是否存在）。"""
    q = query.strip().lstrip("/").replace("\\", "/")
    if not q:
        return []
    with_md = q if q.endswith(".md") else q + ".md"
    cands = [with_md]
    if not with_md.startswith(("Wiki/", "Raw/", "_archive/")):
        cands.extend([f"Wiki/{with_md}", f"Raw/{with_md}"])
    # 再托底一层：将纯文件名（不含子目录）放到各 Wiki/Raw 子表里
    stem = Path(with_md).name
    if stem != with_md:
        for sub in ("Wiki/entities", "Wiki/concepts", "Wiki/comparisons", "Wiki/queries",
                    "Raw/articles", "Raw/notes", "Raw/files", "Raw/transcripts", "Raw/papers"):
            cands.append(f"{sub}/{stem}")
    return cands


def _find_wiki_by_raw(raw_rel: str) -> tuple[Path | None, dict]:
    """反查：哪个 Wiki 页的 sources 包含这个 Raw 相对路径。"""
    target = raw_rel.replace("\\", "/")
    for page in _iter_wiki_pages():
        try:
            meta, _ = split_frontmatter(page.read_text(encoding="utf-8"))
        except Exception:
            continue
        sources = meta.get("sources") or []
        if isinstance(sources, str):
            sources = [sources]
        for s in sources:
            s_norm = str(s).strip().replace("\\", "/")
            if s_norm == target or s_norm.endswith("/" + target):
                return page, meta
    return None, {}


def _find_page(query: str) -> tuple[Path | None, dict, list[str]]:
    """按 title/stem/路径匹配 Wiki 页。返回 (匹配页, frontmatter, 模糊候选标题)。

    若输入是 Raw 相对路径且有 Wiki 引用，则返回该 Wiki 页（级联删除）。
    Raw 孤儿场景由上层调 `_find_raw_only` 处理。
    """
    target = query.strip()
    if not target:
        return None, {}, []

    root = _vault_root()

    # 直接路径命中
    for rel in _path_candidates(target):
        p = root / rel
        if not (p.exists() and p.is_file() and p.suffix == ".md"):
            continue
        try:
            rel_to_root = str(p.relative_to(root)).replace("\\", "/")
        except ValueError:
            continue
        if rel_to_root.startswith("Wiki/"):
            try:
                meta, _ = split_frontmatter(p.read_text(encoding="utf-8"))
            except Exception:
                meta = {}
            return p, meta, []
        if rel_to_root.startswith("Raw/"):
            page, meta = _find_wiki_by_raw(rel_to_root)
            if page is not None:
                return page, meta, []
            # Raw 孤儿——留给上层 _find_raw_only 处理
            return None, {}, []

    # title / stem 匹配
    target_n = _norm(target)
    exact: list[tuple[Path, dict]] = []
    fuzzy: list[str] = []
    for page in _iter_wiki_pages():
        try:
            meta, _ = split_frontmatter(page.read_text(encoding="utf-8"))
        except Exception:
            continue
        title = str(meta.get("title") or "").strip()
        if not title:
            continue
        title_n = _norm(title)
        stem_n = _norm(page.stem)
        if title == target or title_n == target_n or stem_n == target_n:
            exact.append((page, meta))
        elif target_n and (target_n in title_n or target_n in stem_n):
            fuzzy.append(title)

    if len(exact) == 1:
        return exact[0][0], exact[0][1], []
    if len(exact) > 1:
        # 多个正则命中：全部列出 Wiki 相对路径，让用户用路径明确指定
        return None, {}, [str(p.relative_to(root)).replace("\\", "/") for p, _ in exact]

    return None, {}, fuzzy[:5]


def _find_raw_only(query: str) -> Path | None:
    """路径型输入且定位到 Raw 但没 Wiki 引用时返回该 Raw 路径。其他情况返 None。"""
    target = query.strip()
    if not target or "/" not in target.lstrip("/") and not target.endswith(".md"):
        # 非路径型输入不走“只删 Raw”分支（避免误杀）
        return None
    root = _vault_root()
    for rel in _path_candidates(target):
        p = root / rel
        if not (p.exists() and p.is_file() and p.suffix == ".md"):
            continue
        try:
            rel_to_root = str(p.relative_to(root)).replace("\\", "/")
        except ValueError:
            continue
        if rel_to_root.startswith("Raw/"):
            page, _ = _find_wiki_by_raw(rel_to_root)
            if page is None:
                return p
    return None


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

    # 故事 A：找到 Wiki 页 → 级联处理 Wiki + sources
    if page is not None:
        root = _vault_root()
        wiki_rel = str(page.relative_to(root)).replace("\\", "/")
        raw_paths = _resolve_sources(meta)

        moved: list[str] = []
        removed: list[str] = []
        for t in [page] + raw_paths:
            rel = str(t.relative_to(root)).replace("\\", "/")
            if mode == "archive":
                _archive_move(t)
                moved.append(rel)
            else:
                t.unlink()
                removed.append(rel)

        page_title = str(meta.get("title") or page.stem)
        remove_from_index(page_title)
        append_log("archived" if mode == "archive" else "deleted", page_title, wiki_rel)
        pushed = commit_and_push(f"{mode}: {page_title}")
        return {
            "ok": True,
            "title": page_title,
            "wiki": wiki_rel,
            "moved": moved,
            "removed": removed,
            "pushed": pushed,
        }

    # 故事 B：输入是 Raw 路径但无 Wiki 引用 → 只处理 Raw
    raw_orphan = _find_raw_only(title)
    if raw_orphan is not None:
        root = _vault_root()
        rel = str(raw_orphan.relative_to(root)).replace("\\", "/")
        moved: list[str] = []
        removed: list[str] = []
        if mode == "archive":
            _archive_move(raw_orphan)
            moved.append(rel)
        else:
            raw_orphan.unlink()
            removed.append(rel)
        # 无 Wiki 页，无需动 index.md；log.md 仍记一条
        pseudo_title = f"(raw) {raw_orphan.name}"
        append_log("archived" if mode == "archive" else "deleted", pseudo_title, rel)
        pushed = commit_and_push(f"{mode} raw-orphan: {rel}")
        return {
            "ok": True,
            "title": pseudo_title,
            "wiki": None,
            "moved": moved,
            "removed": removed,
            "pushed": pushed,
        }

    # 故事 C：未命中
    return {
        "ok": False,
        "title": title,
        "reason": "not_found",
        "candidates": candidates[:5],
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
                    f"未找到「{result['title']}」对应的 Wiki 页或 Raw 原文。\n\n"
                    f"可能的候选：\n{cand_md}"
                )
            return (
                f"未找到「{result['title']}」对应的 Wiki 页或 Raw 原文。\n\n"
                f"支持用法：\n"
                f"- `/{mode[:3] if mode == 'delete' else mode} <Wiki 标题>` 比如 `Hermes 技能实战体验`\n"
                f"- `/{mode[:3] if mode == 'delete' else mode} <文件名>` 比如 `Hermes-技能实战体验`\n"
                f"- `/{mode[:3] if mode == 'delete' else mode} <Vault 相对路径>` 比如 `Raw/notes/20260504-001224-xxx.md`"
            )
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
        verb = "del" if mode == "delete" else mode
        await client.reply_text(
            reply_message_id,
            f"用法：`/{verb} <Wiki 标题 | 文件名 | Vault 相对路径>`",
        )
        return
    try:
        result = await asyncio.to_thread(_do_cleanup, title, mode)
    except Exception as exc:
        logger.exception("cleanup failed: {}", exc)
        await client.reply_text(reply_message_id, f"{mode} 失败: {exc}")
        return
    await client.reply_text(reply_message_id, _format_reply(mode, result))
