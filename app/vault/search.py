"""Rank original sources and Wiki using lexical terms, including Chinese bigrams."""
from __future__ import annotations
import math
import re
from collections import Counter
from pathlib import Path
from app.config import settings
from .frontmatter import split_frontmatter

_STOP={'什么','哪些','怎么','如何','以前','之前','收藏','关于','资料','内容','有没有','是否','帮我','一下','相关','的','了','我','是','在','the','and','what','how'}

def terms(text):
    text=text.lower()
    for word in sorted(_STOP,key=len,reverse=True):
        if len(word)>1 and re.search('[\u4e00-\u9fff]',word):text=text.replace(word,' ')
    out=[]
    for part in re.findall(r'[a-z0-9][a-z0-9_+.-]*|[\u4e00-\u9fff]+',text):
        if part in _STOP:continue
        if re.search('[\u4e00-\u9fff]',part):
            out.extend([part] if len(part)<3 else [part[i:i+2] for i in range(len(part)-1)])
        else:out.append(part)
    return set(out)


def search_wiki(keyword: str, limit: int=5):
    root=Path(settings.vault_path)
    tokens=terms(keyword)
    if not tokens:return []
    docs=[];df=Counter()
    for folder in ['Wiki','Raw']:
        for p in sorted((root/folder).rglob('*.md')):
            if any(x in ('queries','_archive','.obsidian') for x in p.relative_to(root).parts):continue
            try:meta,body=split_frontmatter(p.read_text(encoding='utf-8'))
            except (OSError,UnicodeError):continue
            if meta.get('type')=='query':continue
            title=str(meta.get('title') or p.stem)
            tags=' '.join(map(str,meta.get('tags') or []))
            aliases=' '.join(map(str,meta.get('aliases') or []))
            full=(title+' '+tags+' '+aliases+' '+body).lower()
            matched={t for t in tokens if t in full}
            if matched:
                docs.append((p,meta,body,title,tags,aliases,matched));df.update(matched)
    ranked=[]
    for p,meta,body,title,tags,aliases,matched in docs:
        score=sum((1+math.log(1+len(docs)/(1+df[t])))*(5*(t in title.lower())+3*(t in (tags+' '+aliases).lower())+min(body.lower().count(t),4)) for t in matched)
        score*=len(matched)/len(tokens)
        paragraphs=[x.strip() for x in re.split(r'\n\s*\n',body) if x.strip()]
        snippets=sorted(enumerate(paragraphs),key=lambda x:sum(t in x[1].lower() for t in tokens),reverse=True)[:3]
        excerpt='\n\n'.join(x[1][:900] for x in sorted(snippets))[:2400]
        rel=str(p.relative_to(root))
        ranked.append((score,{'title':title,'path':rel,'url':rel,'excerpt':excerpt,'summary':excerpt[:200],
                             'tags':meta.get('tags') or [],'sources':meta.get('sources') or [],'kind':'原文' if rel.startswith('Raw/') else 'Wiki'}))
    ranked.sort(key=lambda x:(-x[0],x[1]['path']))
    return [x[1] for x in ranked[:limit]]
