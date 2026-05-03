"""ECS 本地 Vault：纯 md + git 作为知识资产的真相源。"""
from .frontmatter import dump_frontmatter, parse_frontmatter, split_frontmatter
from .git_sync import commit_and_push
from .search import search_wiki
from .writer import write_raw, write_wiki

__all__ = [
    "dump_frontmatter",
    "parse_frontmatter",
    "split_frontmatter",
    "commit_and_push",
    "search_wiki",
    "write_raw",
    "write_wiki",
]
