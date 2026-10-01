"""Repair one XHS source in Raw without regenerating Wiki or replacing prose.

Stop the worker before --apply. Preview: python -m scripts.repair_xhs_images URL
Apply and Git sync: python -m scripts.repair_xhs_images URL --apply
"""
from __future__ import annotations
import argparse
import asyncio
import re
from datetime import datetime
from urllib.parse import urlsplit

from app.jobs import state_root
from app.parsers.url_reader import fetch_url_as_markdown
from app.vault.collection import root
from app.vault.frontmatter import split_frontmatter
from app.vault.git_sync import sync_vault
from app.vault.images import download_images, image_urls, save_images


def image_key(url):
    return urlsplit(url).path.rsplit('/', 1)[-1].split('!', 1)[0]


def repair_text(original, fresh, local):
    mapping = dict(zip(image_urls(fresh), re.findall(r'!\[[^\]]*\]\(<([^>]+)>\)', local)))
    by_key = {image_key(url): path for url, path in mapping.items()}
    if image_urls(original):
        for old in image_urls(original):
            target = by_key.get(image_key(old))
            if not target:
                raise ValueError('Old image not found in current note; leaving document unchanged')
            original = original.replace(old, target)
        return original
    if '_assets/' in original:
        return original
    section = local.split('## 笔记图片', 1)
    if len(section) != 2: raise ValueError('No fresh image section')
    return original.rstrip() + '\n\n## 笔记图片' + section[1] + '\n'


async def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('url')
    parser.add_argument('--apply', action='store_true')
    args = parser.parse_args()
    matches = []
    for path in (root()/'Raw').rglob('*.md'):
        original = path.read_text()
        meta, _ = split_frontmatter(original)
        if meta.get('source_ref') == args.url:
            matches.append((path, original))
    print('Matching Raw notes:', len(matches))
    if not matches: raise RuntimeError('No matching source records')
    if not args.apply:
        for path, _ in matches: print(path.relative_to(root()))
        return
    sync = sync_vault()
    if not sync.ok: raise RuntimeError('Vault must sync before repair: '+sync.state)
    # Re-read after pulling user edits.
    fresh = await fetch_url_as_markdown(args.url)
    downloads = await download_images(fresh, args.url)
    if not downloads: raise RuntimeError('No images downloaded')
    fresh_keys = {image_key(url) for url in image_urls(fresh)}
    for path, _ in matches:
        if any(image_key(url) not in fresh_keys for url in image_urls(path.read_text())):
            raise ValueError('Historical image missing from current page; no files changed')
    backup = state_root()/'image-repair-backups'/datetime.now().strftime('%Y%m%d-%H%M%S')
    paths = []
    for path, _ in matches:
        original = path.read_text()
        rel = path.relative_to(root())
        local, assets = save_images(fresh, str(rel), downloads)
        repaired = repair_text(original, fresh, local)
        if repaired != original:
            saved = backup/rel; saved.parent.mkdir(parents=True, exist_ok=True)
            saved.write_text(original)
            path.write_text(repaired)
            paths.append(str(rel))
        paths.extend(assets)
        print('Repaired:', rel, 'images:', len(downloads))
    sync = sync_vault('repair: archive Xiaohongshu images', list(dict.fromkeys(paths)))
    print('Git:', sync.state, 'Backup:', backup)
    if not sync.ok: raise RuntimeError('Image repair sync incomplete: '+sync.state)


if __name__ == '__main__':
    asyncio.run(main())
