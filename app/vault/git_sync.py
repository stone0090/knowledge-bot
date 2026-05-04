"""Vault Git 同步：commit + push 到 ECS 自建 bare 仓库。

best-effort：push 失败不阻断主流程，仅 logger.warning。
"""
from __future__ import annotations

import subprocess
from pathlib import Path

from loguru import logger

from app.config import settings


def _run(args: list[str], cwd: Path) -> tuple[int, str, str]:
    proc = subprocess.run(
        args,
        cwd=str(cwd),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    return proc.returncode, proc.stdout, proc.stderr


def _ensure_git_identity(cwd: Path) -> None:
    name = settings.vault_git_author_name or "Knowledge Bot"
    email = settings.vault_git_author_email or "bot@knowledge-bot.local"
    _run(["git", "config", "user.name", name], cwd)
    _run(["git", "config", "user.email", email], cwd)


def commit_and_push(message: str) -> bool:
    """在 VAULT_PATH 下 git add . → commit → push；返回是否成功推送。"""
    root = Path(settings.vault_path)
    if not (root / ".git").exists():
        logger.warning("vault.git_sync: {} 不是 git 仓库，跳过", root)
        return False

    _ensure_git_identity(root)

    rc, _, _ = _run(["git", "add", "."], root)
    if rc != 0:
        logger.warning("vault.git_sync: git add 失败")
        return False

    # 没有变更时 commit 会返回非零，这里先探测
    rc_status, out_status, _ = _run(
        ["git", "status", "--porcelain"], root
    )
    if rc_status == 0 and not out_status.strip():
        logger.info("vault.git_sync: 无变更，跳过 commit")
        return False

    rc, out, err = _run(["git", "commit", "-m", message], root)
    if rc != 0:
        logger.warning("vault.git_sync: commit 失败 stdout={} stderr={}", out, err)
        return False

    rc, out, err = _run(["git", "push"], root)
    if rc == 0:
        logger.info("vault.git_sync: push 成功 - {}", message)
        return True

    # push 被 reject：bare 已有其他端（PC/手机）先 push 的 commit，
    # 尝试 pull --rebase 一次再重试 push。冲突走 -X theirs 自动让本次 ingest 胜出。
    logger.warning(
        "vault.git_sync: 首次 push 失败，尝试 pull --rebase 再推 stderr={}", err
    )
    rc_r, out_r, err_r = _run(
        ["git", "pull", "--rebase", "-X", "theirs"], root
    )
    if rc_r != 0:
        logger.warning(
            "vault.git_sync: pull --rebase 失败，放弃 push（commit 已落盘）stderr={}",
            err_r,
        )
        _run(["git", "rebase", "--abort"], root)
        return False

    rc, out, err = _run(["git", "push"], root)
    if rc != 0:
        logger.warning(
            "vault.git_sync: rebase 后 push 仍失败（commit 已落盘，稍后手动 push）stderr={}",
            err,
        )
        return False

    logger.info("vault.git_sync: rebase 后 push 成功 - {}", message)
    return True
