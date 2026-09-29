"""Read the user's Markdown category contract on each collection; never cache it."""
from dataclasses import dataclass
from pathlib import Path
import re
from app.config import settings

FALLBACK = 'Wiki/待整理'

@dataclass(frozen=True)
class Rules:
    categories: dict[str, str]
    warning: str = ''
    guidance: str = ''

    def select(self, candidate):
        return candidate if candidate in self.categories else FALLBACK

    def prompt(self):
        return self.guidance + '\n\n' + '\n\n'.join(f'目录：{path}\n{description}' for path, description in self.categories.items())


def load_rules():
    root = Path(settings.vault_path).resolve()
    try:
        source = (root / '分类规则.md').read_text(encoding='utf-8')
        if len(source) > 20000:
            raise ValueError('too long')
        categories = {}
        guidance = ''
        for section in re.split(r'^##\s+', source, flags=re.M)[1:]:
            lines = section.splitlines()
            paths = re.findall(r'^\s*-\s*目录[：:]\s*`?([^`\n]+?)`?\s*$', section, re.M)
            if not paths:
                if lines[0].strip() == '默认规则':
                    guidance = section.strip()
                    continue
                raise ValueError('missing directory')
            if len(paths) != 1:
                raise ValueError('multiple directories')
            path = paths[0].strip()
            parts = path.split('/')
            if len(parts) < 2 or parts[0] != 'Wiki' or any(not p or p in ('.', '..') or p.startswith('.') or any(c in p for c in '\\:*?"<>|') for p in parts):
                raise ValueError('unsafe directory')
            resolved = (root / path).resolve()
            if not resolved.is_relative_to(root / 'Wiki') or (resolved.exists() and not resolved.is_dir()):
                raise ValueError('invalid directory')
            if path in categories:
                raise ValueError('duplicate directory')
            categories[path] = section.strip()
        if not categories:
            raise ValueError('empty categories')
        return Rules(categories, guidance=guidance)
    except (OSError, UnicodeError, ValueError):
        return Rules({}, '分类规则缺失或格式有误，已放入待整理。')
