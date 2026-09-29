"""Safe Git synchronization: ordinary merges, no automatic conflict-side selection."""
from __future__ import annotations
import subprocess
from pathlib import Path
from dataclasses import dataclass
from app.config import settings

@dataclass
class SyncResult:
    ok: bool
    state: str


def _run(args, cwd):
    try:
        p = subprocess.run(['git', *args], cwd=cwd, capture_output=True, text=True, timeout=60,
                           env={**__import__('os').environ, 'GIT_TERMINAL_PROMPT':'0'})
        return p.returncode, p.stdout.strip()
    except (OSError, subprocess.TimeoutExpired):
        return 1, ''


def sync_vault(message='knowledge-bot sync', paths=None) -> SyncResult:
    root = Path(settings.vault_path)
    if not (root / '.git').exists():
        return SyncResult(False, 'not_git')
    rc, conflicts = _run(['ls-files','-u'], root)
    if rc or conflicts:
        return SyncResult(False, 'conflict')
    for key,val in [('user.name',settings.vault_git_author_name),('user.email',settings.vault_git_author_email)]:
        _run(['config',key,val],root)
    if paths:
        # A source rename may already have been committed before a push retry.
        paths = [p for p in paths if (root/p).exists() or _run(['ls-files','--error-unmatch','--',p],root)[0] == 0]
    if paths:
        # Commit only artifacts belonging to this operation. Leave other edits alone.
        rc,_ = _run(['add','--',*paths],root)
        if rc:
            return SyncResult(False,'stage_failed')
        rc, changed = _run(['diff','--cached','--name-only','--',*paths],root)
        if rc:
            return SyncResult(False,'stage_failed')
        if changed:
            rc,_ = _run(['commit','--only','-m',message,'--',*paths],root)
            if rc:
                return SyncResult(False,'commit_failed')
    rc, dirty = _run(['status','--porcelain'],root)
    if rc or dirty:
        return SyncResult(False,'working_tree_changed')
    rc,_ = _run(['fetch','origin'],root)
    if rc:
        return SyncResult(False,'fetch_failed')
    rc, upstream = _run(['rev-parse','--abbrev-ref','--symbolic-full-name','@{u}'],root)
    if rc:
        return SyncResult(False,'no_upstream')
    rc,_ = _run(['merge','--no-edit',upstream],root)
    if rc:
        _run(['merge','--abort'],root)
        return SyncResult(False,'conflict')
    rc,_ = _run(['push'],root)
    return SyncResult(rc==0,'synced' if rc==0 else 'push_failed')


def commit_and_push(message: str) -> bool:
    """Legacy helper, retained for offline maintenance scripts."""
    root=Path(settings.vault_path)
    rc,paths=_run(['ls-files','--modified','--others','--exclude-standard'],root)
    return sync_vault(message, paths.splitlines() if not rc else None).ok
