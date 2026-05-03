"""Vault 本地检索：扫描 Wiki/**/*.md。

优先使用 ripgrep（若可执行），否则 fallback 到纯 Python 扫描。
返回候选笔记列表，供检索 LLM 使用。
"""
from __future__ import annotations

import shutil
import subprocess
from pathlib import Path
from typing import Any

from loguru import logger

from app.config import settings

from .frontmatter import split_frontmatter


def _vault_wiki_root() -> Path:
    return Path(settings.vault_path) / "Wiki"


def _extract_points(body: str, max_points: int = 5) -> list[str]:
    """从正文 `## 核心观点` 段提取 bullet。"""
    lines = body.splitlines()
    points: list[str] = []
    in_points = False
    for line in lines:
        stripped = line.strip()
        if stripped.startswith("## "):
            in_points = stripped.lstrip("# ").strip().startswith("核心观点")
            continue
        if in_points and stripped.startswith("- "):
            points.append(stripped[2:].strip())
            if len(points) >= max_points:
                break
    return points


def _load_candidate(path: Path, vault_root: Path) -> dict[str, Any]:
    try:
        content = path.read_text(encoding="utf-8")
    except OSError as exc:
        logger.warning("读取 {} 失败: {}", path, exc)
        return {}
    meta, body = split_frontmatter(content)
    if not meta:
        # 无 frontmatter 的旧文件也支持：退化为 title=文件名、summary=首段
        meta = {"title": path.stem, "summary": body.strip().split("\n\n", 1)[0][:120]}
        body = content
    rel = path.relative_to(vault_root)
    return {
        "title": str(meta.get("title") or path.stem),
        "summary": str(meta.get("summary") or ""),
        "points": _extract_points(body),
        "url": str(rel).replace("\\", "/"),
        "tags": meta.get("tags") or [],
    }


def _search_with_rg(keyword: str, wiki_root: Path) -> list[Path]:
    """用 ripgrep 找出包含关键字的 md 文件路径。"""
    rg = shutil.which("rg")
    if not rg:
        return []
    try:
        proc = subprocess.run(
            [rg, "--files-with-matches", "--no-heading", "-i", "-g", "*.md", keyword, str(wiki_root)],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=10,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        logger.warning("ripgrep 调用失败: {}", exc)
        return []
    if proc.returncode not in (0, 1):  # 1 = 无匹配
        logger.warning("ripgrep 返回异常 rc={} stderr={}", proc.returncode, proc.stderr)
        return []
    return [Path(line) for line in proc.stdout.splitlines() if line.strip()]


def _search_with_python(keyword: str, wiki_root: Path) -> list[Path]:
    """纯 Python fallback：不区分大小写扫描 md 内容。"""
    kw = keyword.lower()
    matched: list[Path] = []
    for p in wiki_root.rglob("*.md"):
        try:
            if kw in p.read_text(encoding="utf-8").lower():
                matched.append(p)
        except OSError:
            continue
    return matched


def search_wiki(keyword: str, limit: int = 5) -> list[dict[str, Any]]:
    """按关键字检索 Wiki；关键字为空时返回最近修改的 N 篇。"""
    wiki_root = _vault_wiki_root()
    if not wiki_root.exists():
        logger.warning("Wiki 目录不存在: {}", wiki_root)
        return []

    keyword = (keyword or "").strip()
    if keyword:
        paths = _search_with_rg(keyword, wiki_root) or _search_with_python(keyword, wiki_root)
    else:
        paths = sorted(wiki_root.rglob("*.md"), key=lambda p: p.stat().st_mtime, reverse=True)

    vault_root = Path(settings.vault_path)
    results: list[dict[str, Any]] = []
    for p in paths[:limit]:
        c = _load_candidate(p, vault_root)
        if c:
            results.append(c)
    return results
