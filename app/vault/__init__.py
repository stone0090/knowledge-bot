"""ECS 本地 Vault：纯 md + git 作为知识资产的真相源。"""
from .frontmatter import dump_frontmatter, parse_frontmatter, split_frontmatter
from .gate import vault_write_gate
from .git_sync import commit_and_push
from .indexer import append_index, append_log, remove_from_index
from .lint import lint_vault
from .search import search_wiki
from .writer import write_query, write_raw, write_skill, write_wiki

__all__ = [
    "dump_frontmatter",
    "parse_frontmatter",
    "split_frontmatter",
    "vault_write_gate",
    "commit_and_push",
    "append_index",
    "append_log",
    "remove_from_index",
    "lint_vault",
    "search_wiki",
    "write_query",
    "write_raw",
    "write_skill",
    "write_wiki",
]
