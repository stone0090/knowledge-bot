"""Flat Wiki pages and immutable source records. Human edits are never overwritten."""
from __future__ import annotations
import hashlib
import os
import json
import re
from pathlib import Path
from datetime import datetime
from urllib.parse import quote, unquote
from app.config import settings
from .frontmatter import dump_frontmatter, split_frontmatter
from .writer import _slugify


def digest(text):
    return hashlib.sha256(text.encode('utf-8')).hexdigest()


def root():
    p = Path(settings.vault_path).resolve()
    if not p.is_dir():
        raise RuntimeError('vault_missing')
    return p


def readable_name(title):
    name = re.sub(r'[\\/:*?"<>|\[\]#^\r\n]', ' ', str(title))
    return re.sub(r'\s+', ' ', name).strip(' .')[:80] or '未命名笔记'


def unique_path(directory, title):
    name = readable_name(title)
    candidate = directory / (name + '.md')
    number = 2
    while (root() / candidate).exists():
        candidate = directory / (name + '（' + str(number) + '）.md')
        number += 1
    return candidate


def source_path(job_id):
    for p in (root() / 'Raw').rglob('*.md'):
        meta, _ = split_frontmatter(p.read_text(encoding='utf-8'))
        if str(meta.get('collection_id', '')) == job_id:
            return p.relative_to(root())
    return None


def rename_source(job_id, title):
    old = source_path(job_id)
    if old is None:
        raise RuntimeError('source_missing')
    meta, body = split_frontmatter((root()/old).read_text(encoding='utf-8'))
    if meta.get('title') == title:
        return str(old), None
    new = unique_path(old.parent, title)
    meta['title'] = title
    (root()/old).write_text(dump_frontmatter(meta)+'\n'+body, encoding='utf-8')
    (root()/old).rename(root()/new)
    return str(new), str(old)


def save_received(job_id, text, source='inline'):
    rel = source_path(job_id)
    if rel is None:
        title = '网页收藏' if source.startswith(('http://', 'https://')) else text.splitlines()[0][:60] if text.strip() else '待整理收藏'
        rel = unique_path(Path('Raw') / datetime.now().strftime('%Y/%m'), title)
    p = root()/rel
    if not p.exists():
        meta={'title': rel.stem, 'source_ref':source, 'received':datetime.now().isoformat(timespec='seconds'), 'collection_id':job_id}
        body=dump_frontmatter(meta)+'\n# 原始消息\n\n'+text+'\n'
        p.parent.mkdir(parents=True,exist_ok=True)
        with p.open('x',encoding='utf-8') as f:
            f.write(body)
    return str(rel)


def save_extracted(job_id, text, source, received):
    # Enrich the received record by appending; never replace the user's original message.
    content_id=digest(source+'\n'+text)
    rel=source_path(job_id);p=root()/rel
    marker='<!-- extracted-source:'+content_id+' -->'
    if source!='inline' and marker not in p.read_text(encoding='utf-8'):
        with p.open('a',encoding='utf-8') as f:
            f.write('\n\n## 抓取正文\n\n'+marker+'\n\n'+text.rstrip()+'\n')
    return str(rel),content_id


def find_content(content_id):
    for p in sorted((root()/'Wiki').rglob('*.md')):
        meta,_=split_frontmatter(p.read_text(encoding='utf-8'))
        if meta.get('content_id')==content_id:
            return str(p.relative_to(root()))
    return None


def existing_titles():
    titles={}
    for p in (root()/'Wiki').rglob('*.md'):
        meta,_=split_frontmatter(p.read_text(encoding='utf-8'))
        title=str(meta.get('title') or p.stem)
        target=str(p.relative_to(root()).with_suffix(''))
        titles[title]=None if title in titles else target
    return titles


def save_page(card, content_id, sources, source_ref='', remark=''):
    found=find_content(content_id)
    if found:
        # A manually edited existing page is returned as-is, never regenerated over it.
        return found,True
    from .categories import load_rules
    category = load_rules().select(card.category)
    rel = unique_path(Path(category), card.title)
    p = root()/rel
    meta={'title':card.title,'type':'note','created':datetime.now().isoformat(timespec='seconds'),
          'tags':card.tags,'aliases':card.aliases,'sources':sources,'content_id':content_id,'source_ref':source_ref}
    allowed=existing_titles()
    card.related=[allowed[t] for t in card.related if allowed.get(t) and t!=card.title]
    body=card.to_markdown()
    if remark:body+='\n\n## 我的备注\n\n'+remark
    body+='\n\n## 来源\n\n'+'\n'.join('- [原始记录 '+str(i+1)+']('+quote(os.path.relpath(root()/s, p.parent),safe='/.-_')+')' for i,s in enumerate(sources))+'\n'
    meta['generated_body_sha256']=digest(body)
    p.parent.mkdir(parents=True,exist_ok=True)
    with p.open('x',encoding='utf-8') as f:f.write(dump_frontmatter(meta)+'\n'+body)
    return str(rel),False


def save_answer(job_id, question, answer, sources):
    for existing in (root()/'Wiki').rglob('*.md'):
        meta, _ = split_frontmatter(existing.read_text(encoding='utf-8'))
        if str(meta.get('query_job_id', '')) == job_id:
            return str(existing.relative_to(root()))
    rel=unique_path(Path('Wiki/待整理'), '问答：'+question)
    p=root()/rel
    if not p.exists():
        meta={'title':question,'type':'saved_answer','query_job_id':job_id,'sources':sources,'created':datetime.now().isoformat(timespec='seconds')}
        # Query citations are vault-relative; saved answers live inside Wiki.
        def citation(match):
            target=unquote(match.group(1))
            return '('+quote(os.path.relpath(root()/target,p.parent),safe='/.-_')+')' if target in sources else match.group()
        answer=re.sub(r'\(([^)]+)\)',citation,answer)
        answer+='\n\n## 来源\n\n'+'\n'.join('- [来源 '+str(i+1)+']('+quote(os.path.relpath(root()/source,p.parent),safe='/.-_')+')' for i,source in enumerate(sources))
        p.parent.mkdir(parents=True,exist_ok=True)
        with p.open('x',encoding='utf-8') as f:f.write(dump_frontmatter(meta)+'\n# '+question+'\n\n'+answer+'\n')
    return str(rel)
