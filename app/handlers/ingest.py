"""Collect first, compile second. No Drive mirror, index or operation-log writes."""
from __future__ import annotations
import asyncio
from datetime import datetime
from pathlib import Path
from app.jobs import state_root
from app.feishu import get_feishu_client
from app.parsers import parse_any
from app.llm import compile_knowledge
from app.vault.collection import save_received,save_extracted,save_page,digest,find_content,rename_source
from app.vault.git_sync import sync_vault
from app.vault.gate import vault_write_gate
from app.vault.images import download_images, save_images


async def collect(job, inbox):
    jid=job['id'];payload=job['payload'];result=dict(job['result'])
    # After a push failure/restart, use durable artifacts instead of paying for regeneration.
    if result.get('wiki_path'):
        return result
    text=payload.get('text','');file=payload.get('file')
    received=text if not file else '附件：'+file['name']
    if not result.get('wiki_path'):
        async with vault_write_gate.acquire():
            from app.parsers.dispatcher import URL_PATTERN
            match=URL_PATTERN.search(text)
            source=file["name"] if file else match.group(0) if match else "inline"
            raw=await asyncio.to_thread(save_received,jid,received,source)
            result['raw_path']=raw
            inbox.update(jid,result=result)
            await asyncio.to_thread(sync_vault,'collect: '+jid,[raw]+result.get('asset_paths',[]))
    cache=state_root()/'parsed'/ (jid+'.json')
    import json
    if cache.exists():
        data=json.loads(cache.read_text())
    else:
        if file:
            binary=state_root()/'uploads'/jid
            if not binary.exists():
                raw_bytes=await get_feishu_client().download_message_file(job['message_id'],file['key'],file['type'])
                binary.parent.mkdir(parents=True,exist_ok=True)
                binary.write_bytes(raw_bytes);binary.chmod(0o600)
            parsed=await parse_any(file=(binary.read_bytes(),file['name']))
        else:
            parsed=await parse_any(text=text)
        if not parsed.text.strip():raise RuntimeError('empty_source')
        data={'text':parsed.text,'source':parsed.source_ref,'remark':getattr(parsed,'remark','')}
        cache.parent.mkdir(parents=True,exist_ok=True)
        tmp=cache.with_suffix('.tmp');tmp.write_text(json.dumps(data,ensure_ascii=False));tmp.chmod(0o600);tmp.replace(cache)
    try:
        downloads = await download_images(data['text'], data['source'])
    except Exception:
        # Signed URLs may have expired in the parsed cache. Retry the original page.
        if data['source'].startswith(('http://', 'https://')):
            cache.unlink(missing_ok=True)
        raise
    async with vault_write_gate.acquire():
        archived_text, assets = await asyncio.to_thread(save_images, data['text'], result['raw_path'], downloads)
        result['asset_paths'] = assets
        inbox.update(jid,result=result)
        raw_content,content_id=await asyncio.to_thread(save_extracted,jid,archived_text,data['source'],datetime.now().isoformat(timespec='seconds'))
        # A different user comment is meaningful and must not be discarded by deduplication.
        content_id=digest(content_id+'\n'+data['remark'])
        result.update(content_path=raw_content,content_id=content_id)
        inbox.update(jid,result=result)
        refresh = await asyncio.to_thread(sync_vault,'source: '+jid,[result['raw_path'],raw_content]+assets)
        duplicate=await asyncio.to_thread(find_content,content_id)
    if duplicate:
        from app.vault.collection import root
        from app.vault.frontmatter import split_frontmatter
        meta,body=split_frontmatter((root()/duplicate).read_text())
        async with vault_write_gate.acquire():
            new_raw, retired = await asyncio.to_thread(rename_source,jid,str(meta.get('title') or Path(duplicate).stem))
            result.update(raw_path=new_raw,content_path=new_raw)
            if retired:result['retired_paths']=list(dict.fromkeys(result.get('retired_paths',[])+[retired]))
        result.update(wiki_path=duplicate,title=str(meta.get('title') or Path(duplicate).stem),summary='相同内容已收藏，已有正文和手动修改均保留。',preview='',duplicate=True)
    else:
        from app.vault.categories import load_rules, Rules
        rules = await asyncio.to_thread(load_rules) if refresh.ok else Rules({}, 'Git 刷新失败，无法确认最新分类规则，已放入待整理。')
        card=await compile_knowledge(data['text'], rules=rules)
        card.category=rules.select(card.category)
        async with vault_write_gate.acquire():
            new_raw, retired = await asyncio.to_thread(rename_source,jid,card.title)
            result.update(raw_path=new_raw,content_path=new_raw)
            if retired:result['retired_paths']=list(dict.fromkeys(result.get('retired_paths',[])+[retired]))
            inbox.update(jid,result=result)
            raw_content=new_raw
            path,duplicate=await asyncio.to_thread(save_page,card,content_id,list(dict.fromkeys([result['raw_path'],raw_content])),data['source'],data['remark'])
        result.update(wiki_path=path,title=card.title,summary=card.summary,preview=card.to_markdown(),duplicate=duplicate)
        if rules.warning:
            result['summary']+='\n'+rules.warning
            result['preview']+='\n\n'+rules.warning
    inbox.update(jid,result=result)
    return result
