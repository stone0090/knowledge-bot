"""Normalize Feishu messages and durably enqueue before acknowledging delivery."""
from __future__ import annotations
import asyncio
import json
from app.config import settings
from app.jobs import Inbox

QUERY_PREFIXES=('/查','/q','/search')
LINT_PREFIXES=('/lint',)
DELETE_PREFIXES=('/delete','/del')
ARCHIVE_PREFIXES=('/archive',)
SKILL_PREFIXES=('/skill','/sk')


def _extract_text(message):
    raw=message.get('content') or '{}'
    try:data=json.loads(raw) if isinstance(raw,str) else raw
    except (ValueError,TypeError):return ''
    if 'text' in data:return str(data['text']).strip()
    # Feishu posts may be a locale map, and hyperlinks use href rather than text.
    if 'content' not in data:
        data=next((x for x in data.values() if isinstance(x,dict) and 'content' in x),{})
    parts=[str(data.get('title') or '')]
    for row in data.get('content',[]) or []:
        for seg in row or []:
            if isinstance(seg,dict):
                if seg.get('tag')=='a':parts.append(str(seg.get('href') or seg.get('text') or ''))
                elif seg.get('tag')=='text':parts.append(str(seg.get('text') or ''))
    return '\n'.join(x for x in parts if x).strip()


def _extract_file(message):
    try:
        raw=message.get('content') or '{}';data=json.loads(raw) if isinstance(raw,str) else raw
    except (ValueError,TypeError):return None
    kind=message.get('message_type')
    if kind=='file' and data.get('file_key'):return data['file_key'],data.get('file_name','attachment'),'file'
    if kind=='image' and data.get('image_key'):return data['image_key'],'image.jpg','image'
    return None


def command(text):
    head,_,tail=text.partition(' ')
    if head in QUERY_PREFIXES:return 'query',tail.strip()
    if head in ('/重试','/retry'):return 'retry',tail.strip()
    if head in ('/保存','/save'):return 'save',tail.strip()
    if head in ('/状态','/status'):return 'status',tail.strip()
    if text.startswith('/'):return 'help',''
    return 'ingest',text


async def dispatch_event(payload):
    header=payload.get('header') or {}
    if header.get('event_type')!='im.message.receive_v1':return
    event=payload.get('event') or {};message=event.get('message') or {}
    message_id=message.get('message_id')
    if not message_id:return
    sender=(event.get('sender') or {}).get('sender_id') or {}
    sender_id=sender.get('open_id') or sender.get('user_id') or ''
    allow={x.strip() for x in settings.feishu_allowed_open_ids.split(',') if x.strip()}
    if allow and sender_id not in allow:return
    if (event.get('sender') or {}).get('sender_type')=='app':return
    scope=str(message.get('chat_id') or '')+':'+sender_id
    text=_extract_text(message);file=_extract_file(message)
    if not text and not file:return
    kind,arg=command(text)
    data={'kind':kind,'text':arg}
    if file:data={'kind':'ingest','file':dict(zip(('key','name','type'),file))}
    await asyncio.to_thread(Inbox().enqueue,str(message_id),scope,data)
