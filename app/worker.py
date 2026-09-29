"""One durable worker; restart recovery, bounded retries, separate reply delivery."""
from __future__ import annotations
import asyncio
import time
from contextlib import suppress
from loguru import logger
from app.config import settings
from app.jobs import Inbox,state_root
from app.feishu import get_feishu_client
from app.handlers.ingest import collect
from app.handlers.query import query
from app.handlers.cards import build_ingest_card,build_answer_card
from app.vault.git_sync import sync_vault
from app.vault.collection import save_answer
from app.vault.gate import vault_write_gate

HELP='直接发送链接、文字或文件即可收藏。\n/查 问题：搜索原文和 Wiki\n/保存：保存最近一次有来源的回答\n/重试 [任务编号]：重试失败任务\n/状态 [任务编号]：查看状态\n文件的删除、归档请在 Obsidian 中操作；旧 /skill、/lint 命令暂不提供。'


def safe_error(exc):
    from app.parsers.url_reader import FetchError
    if isinstance(exc,FetchError):return exc.user_hint
    value=str(exc).lower()
    if '401' in value or '403' in value:return '接口认证失败；原始消息已保留，请修复配置后重试。'
    if '429' in value:return '接口限流；原始消息已保留。'
    if isinstance(exc,(asyncio.TimeoutError,TimeoutError)):return '处理超时；原始消息已保留。'
    if 'invalid_model_output' in value:return '模型返回格式不正确；原始消息已保留。'
    return '本次处理失败；原始消息已保留，可使用 /重试。'


async def process(job,db):
    jid=job['id'];kind=job['payload']['kind'];text=job['payload'].get('text','')
    try:
        if kind=='ingest':result=await collect(job,db)
        elif kind=='query':
            if not text:result={'text':'用法：/查 你想找的问题'}
            else:
                # Include edits pushed from Obsidian even when no collection arrived.
                async with vault_write_gate.acquire():
                    refresh=await asyncio.to_thread(sync_vault)
                result=await query(text)
                result['refresh_state']=refresh.state
                if not refresh.ok:
                    result['answer']+='\n\n提示：本次未能刷新 Git，回答基于服务器当前已有笔记。'

        elif kind=='save':
            result=dict(job['result'])
            if not result.get('wiki_path'):
                source=db.get(text) if text else db.latest(job['scope'],'query')
                if not source or source['scope']!=job['scope'] or source['payload']['kind']!='query' or source['status']!='done' or not source['result'].get('candidates'):
                    result={'text':'没有可保存的、有来源的查询回答。先发送 /查 问题。'}
                else:
                    answer=source['result']
                    async with vault_write_gate.acquire():
                        path=await asyncio.to_thread(save_answer,source['id'],answer['question'],answer['answer'],[x['path'] for x in answer['candidates']])
                    result={'wiki_path':path,'title':answer['question'],'summary':'已按你的要求保存回答。'}
        elif kind=='retry':
            target=db.retry(job['scope'],text)
            result={'text':('已安排重试：'+target) if target else '没有找到本会话可重试的失败任务。'}
        elif kind=='status':
            target=db.get(text) if text else next((x for x in _recent(db,job['scope']) if x['id']!=jid),None)
            if target and target['scope']==job['scope']:
                labels={'pending':'等待处理','running':'处理中','retry':'等待重试','sync_pending':'等待 Git 同步','failed':'处理失败','done':'处理完成'}
                result={'text':f"任务 {target['id']}：{labels.get(target['status'],target['status'])}\n{target['error']}"}
            else:result={'text':'未找到本会话的任务。'}
        else:result={'text':HELP}
        db.update(jid,result=result)
        if result.get('wiki_path'):
            paths=list(dict.fromkeys(x for x in [result.get('raw_path'),result.get('content_path'),result['wiki_path']]+result.get('retired_paths',[]) if x))
            async with vault_write_gate.acquire():sync=await asyncio.to_thread(sync_vault,'collect: '+jid,paths)
            result.update(synced=sync.ok,sync_state=sync.state)
            if not sync.ok:
                delay=min(settings.retry_delay_seconds*2**min(job['attempts']-1,6),3600)
                db.update(jid,status='sync_pending',due=time.time()+delay,result=result,error='Git 同步未完成：'+sync.state)
                return
        db.update(jid,status='done',result=result,error='',notified=0)
    except Exception as exc:
        retry=job['attempts']<settings.max_job_attempts
        db.update(jid,status='retry' if retry else 'failed',due=time.time()+settings.retry_delay_seconds*2**(job['attempts']-1),error=safe_error(exc),notified=0)
        logger.warning('job {} failed ({})',jid,type(exc).__name__)


def _recent(db,scope):
    with db.connect() as conn:
        return [db.decode(x) for x in conn.execute('SELECT * FROM jobs WHERE scope=? ORDER BY created DESC LIMIT 20',(scope,))]


async def notify(job,db):
    client=get_feishu_client();result=job['result'];jid=job['id']
    if job['status']=='failed':
        await client.reply_text(job['message_id'],job['error']+'\n任务：'+jid+'\n发送 /重试 '+jid+' 可继续。')
    elif result.get('wiki_path'):
        await client.reply_card(job['message_id'],build_ingest_card(result['title'],result.get('summary',''),vault_path=result['wiki_path'],preview=result.get('preview',''),synced=result.get('synced',False),duplicate=result.get('duplicate',False),job_id=jid))
    elif result.get('answer'):
        await client.reply_card(job['message_id'],build_answer_card(result['question'],result['answer']))
    else:await client.reply_text(job['message_id'],result.get('text',HELP))
    db.update(jid,notified=1)


async def run_worker():
    import fcntl
    lock=(state_root()/'worker.lock').open('a')
    try:fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
    except BlockingIOError:
        lock.close();raise RuntimeError('Only one worker process may use STATE_PATH')
    db=Inbox();db.recover();last_notify=0
    try:
        while True:
            job=db.claim()
            if job:
                # The durable inbox already holds the complete incoming message.
                if job['attempts']==1 and job['payload']['kind']=='ingest':
                    try:await get_feishu_client().reply_text(job['message_id'],'已保存到收集队列，正在整理。任务：'+job['id'])
                    except Exception:logger.warning('receipt delivery failed for {}',job['id'])
                await process(job,db)
            if time.time()-last_notify>10:
                for item in db.notifications():
                    try:await notify(item,db)
                    except Exception:logger.warning('reply delivery pending for {}',item['id'])
                last_notify=time.time()
            if not job:await asyncio.sleep(settings.worker_poll_seconds)
    finally:lock.close()
