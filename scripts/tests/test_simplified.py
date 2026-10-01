"""Offline safety and behavior tests. No messages, network services or real vault writes."""
from __future__ import annotations
import asyncio,json,os,subprocess,tempfile,unittest
from pathlib import Path
from unittest.mock import patch,AsyncMock
from app.config import settings
from app.jobs import Inbox
from app.worker import process
from app.vault.git_sync import SyncResult,sync_vault
from app.vault.collection import save_received,save_page
from app.llm.compile import KnowledgeCard
from app.handlers.dispatcher import dispatch_event,_extract_text
from app.vault.search import search_wiki
from scripts.migrate_collection import migrate

def card(title='沟通练习'):
    return KnowledgeCard(title=title,tags=['沟通'],summary='保留例子和实践步骤',points=['先复述对方的问题'],related=['不存在的词条'])

class FlowTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.base=Path(self.tmp.name)
        self.old=(settings.vault_path,settings.state_path,settings.max_job_attempts)
        settings.vault_path=str(self.base/'vault');Path(settings.vault_path).mkdir()
        settings.state_path=str(self.base/'state');settings.max_job_attempts=1
        self.db=Inbox();self.root=Path(settings.vault_path)
    def tearDown(self):
        settings.vault_path,settings.state_path,settings.max_job_attempts=self.old
        self.tmp.cleanup()
    def new(self,mid='m1',kind='ingest',text='沟通时先确认对方问题'):
        return self.db.enqueue(mid,'chat:user',{'kind':kind,'text':text})
    async def runjob(self,job):
        claimed=self.db.claim();self.assertEqual(claimed['id'],job['id'])
        await process(claimed,self.db);return self.db.get(job['id'])
    async def test_webhook_duplicate_durable_and_recover(self):
        event={'header':{'event_type':'im.message.receive_v1'},'event':{'sender':{'sender_id':{'open_id':'user'}},'message':{'message_id':'m1','chat_id':'chat','content':json.dumps({'text':'笔记内容'})}}}
        await dispatch_event(event);await dispatch_event(event)
        with self.db.connect() as db:self.assertEqual(db.execute('SELECT count(*) FROM jobs').fetchone()[0],1)
        job=self.db.claim();self.assertIsNotNone(job)
        Inbox().recover();self.assertEqual(self.db.get(job['id'])['status'],'retry')
        self.assertEqual(self.db.get(job['id'])['payload']['text'],'笔记内容')
    async def test_raw_survives_model_error_and_retry(self):
        j=self.new()
        with patch('app.handlers.ingest.sync_vault',return_value=SyncResult(True,'synced')),patch('app.handlers.ingest.compile_knowledge',AsyncMock(side_effect=RuntimeError('dashscope error 401'))):
            result=await self.runjob(j)
        self.assertEqual(result['status'],'failed');self.assertEqual(len(list((self.root/'Raw').rglob('*.md'))),1)
        self.assertFalse((self.root/'Wiki').exists())
        self.assertEqual(self.db.retry('chat:user',j['id']),j['id'])
        with patch('app.handlers.ingest.sync_vault',return_value=SyncResult(True,'synced')),patch('app.worker.sync_vault',return_value=SyncResult(True,'synced')),patch('app.handlers.ingest.compile_knowledge',AsyncMock(return_value=card())):
            result=await self.runjob(j)
        self.assertEqual(result['status'],'done');self.assertTrue(result['result']['synced'])
        self.assertFalse((self.root/'index.md').exists());self.assertFalse((self.root/'log.md').exists())
    async def test_images_are_synced_with_raw_before_model_failure(self):
        from app.parsers.dispatcher import ParsedContent
        from app.vault.images import FetchError
        from app.jobs import state_root
        text='![图片](<https://cdn.example/a.jpg>)'
        j=self.new(text='https://example.com/article')
        with patch('app.handlers.ingest.parse_any',AsyncMock(return_value=ParsedContent('url','https://example.com/article',text))), patch('app.handlers.ingest.download_images',AsyncMock(return_value={'https://cdn.example/a.jpg':(b'\xff\xd8\xffimage','.jpg')})), patch('app.handlers.ingest.sync_vault',return_value=SyncResult(True,'synced')) as sync, patch('app.handlers.ingest.compile_knowledge',AsyncMock(side_effect=RuntimeError('model failed'))):
            result=await self.runjob(j)
        assets=result['result']['asset_paths']
        self.assertEqual(len(assets),1)
        self.assertTrue((self.root/assets[0]).is_file())
        self.assertIn(assets[0],sync.call_args.args[1])
        raw=(self.root/result['result']['raw_path']).read_text()
        self.assertIn('_assets/',raw);self.assertNotIn('https://cdn.example/a.jpg',raw)
        self.db.retry('chat:user',j['id'])
        with patch('app.handlers.ingest.sync_vault',return_value=SyncResult(True,'synced')), patch('app.handlers.ingest.download_images',AsyncMock(side_effect=FetchError('expired','expired'))):
            await self.runjob(j)
        self.assertFalse((state_root()/'parsed'/(j['id']+'.json')).exists())
    async def test_duplicate_content_preserves_manual_edit(self):
        with patch('app.handlers.ingest.sync_vault',return_value=SyncResult(True,'synced')),patch('app.worker.sync_vault',return_value=SyncResult(True,'synced')),patch('app.handlers.ingest.compile_knowledge',AsyncMock(return_value=card())) as llm:
            a=await self.runjob(self.new());p=self.root/a['result']['wiki_path'];p.write_text(p.read_text()+'\n我自己的经验。\n')
            b=await self.runjob(self.new('m2'))
        self.assertTrue(b['result']['duplicate']);self.assertEqual(llm.await_count,1)
        self.assertIn('我自己的经验',p.read_text());self.assertNotIn('不存在的词条',p.read_text())
        self.assertEqual(len(list((self.root/'Wiki').rglob('*.md'))),1)
    async def test_push_retry_does_not_recompile(self):
        j=self.new()
        with patch('app.handlers.ingest.sync_vault',return_value=SyncResult(True,'synced')),patch('app.worker.sync_vault',return_value=SyncResult(False,'push_failed')),patch('app.handlers.ingest.compile_knowledge',AsyncMock(return_value=card())):
            a=await self.runjob(j)
        self.assertEqual(a['status'],'sync_pending');self.assertFalse(a['result']['synced'])
        self.db.update(j['id'],due=0)
        with patch('app.worker.sync_vault',return_value=SyncResult(True,'synced')),patch('app.handlers.ingest.compile_knowledge',AsyncMock(side_effect=AssertionError('must not recompile'))):b=await self.runjob(j)
        self.assertTrue(b['result']['synced'])
    async def test_query_readonly_and_explicit_save(self):
        candidates=[{'path':'Raw/a.md','url':'Raw/a.md','title':'沟通','excerpt':'先复述','kind':'原文'}]
        with patch('app.worker.sync_vault',return_value=SyncResult(True,'synced')) as refresh,patch('app.handlers.query.search_wiki',return_value=candidates),patch('app.handlers.query.answer_question',AsyncMock(return_value='先复述问题。[来源](Raw/a.md)')):
            q=await self.runjob(self.new(kind='query',text='沟通'))
        refresh.assert_called_once_with()
        self.assertEqual(q['result']['refresh_state'],'synced')
        self.assertEqual(list(self.root.rglob('*.md')),[])
        with patch('app.worker.sync_vault',return_value=SyncResult(True,'synced')):
            saved=await self.runjob(self.new('m2','save',''))
        self.assertEqual(saved['status'],'done');self.assertEqual(len(list(self.root.rglob('*.md'))),1)
        self.assertIn('(../../Raw/a.md)',(self.root/saved['result']['wiki_path']).read_text())
    async def test_callback_auth_and_persistence_without_sending(self):
        import httpx
        from app.main import app
        with patch.object(settings,'feishu_verification_token','offline-test-token'):
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app),base_url='http://test') as client:
                denied=await client.post('/feishu/event',json={'type':'url_verification','challenge':'hello','token':'wrong'})
                self.assertEqual(denied.status_code,403)
                allowed=await client.post('/feishu/event',json={'type':'url_verification','challenge':'hello','token':'offline-test-token'})
                self.assertEqual(allowed.json(),{'challenge':'hello'})
                event={'header':{'token':'offline-test-token','event_type':'im.message.receive_v1'},'event':{'sender':{'sender_id':{'open_id':'user'}},'message':{'message_id':'offline-callback','chat_id':'chat','content':json.dumps({'text':'持久化测试'})}}}
                for _ in range(2):self.assertEqual((await client.post('/feishu/event',json=event)).status_code,200)
        with self.db.connect() as db:self.assertEqual(db.execute('SELECT count(*) FROM jobs').fetchone()[0],1)

    async def test_retry_cannot_cross_chat_scope(self):
        j=self.new();self.db.update(j['id'],status='failed')
        self.assertIsNone(self.db.retry('other:user',j['id']))
    async def test_url_with_comment_and_post_link(self):
        from app.parsers.dispatcher import parse_text
        with patch('app.parsers.dispatcher.fetch_url_as_markdown',AsyncMock(return_value='公开文章正文')):
            parsed=await parse_text('https://example.com/article 这篇以后做沟通练习时用')
        self.assertEqual(parsed.remark,'这篇以后做沟通练习时用')
        msg={'content':json.dumps({'zh_cn':{'title':'文章','content':[[{'tag':'a','href':'https://example.com','text':'链接'}]]}})}
        self.assertIn('https://example.com',_extract_text(msg))
    async def test_search_rank_and_old_answers_excluded(self):
        (self.root/'Raw').mkdir();(self.root/'Wiki/queries').mkdir(parents=True)
        (self.root/'Raw/表达.md').write_text('# 提升表达能力\n\n沟通时可以先复述对方的问题。')
        (self.root/'Wiki/queries/旧答案.md').write_text('沟通表达'*50)
        found=search_wiki('以前收藏过什么关于沟通表达的资料？')
        self.assertEqual(found[0]['path'],'Raw/表达.md');self.assertIn('复述',found[0]['excerpt']);self.assertEqual(len(found),1)
    async def test_related_links_use_actual_existing_paths(self):
        path,_=save_page(card(),'a'*64,['Raw/a.md'])
        second=card('反馈练习');second.related=['沟通练习','虚构词条']
        saved,_=save_page(second,'b'*64,['Raw/b.md'])
        content=(self.root/saved).read_text()
        self.assertIn('[['+str(Path(path).with_suffix(''))+']]',content)
        self.assertNotIn('虚构词条',content)

    async def test_dynamic_rules_and_unknown_category(self):
        from app.vault.categories import load_rules
        from app.llm.compile import compile_knowledge
        rule=self.root/'分类规则.md'
        rule.write_text('# 分类规则\n## 开发工具\n- 目录：Wiki/开发工具\n- 收录：终端\n')
        self.assertEqual(load_rules().select('Wiki/开发工具'),'Wiki/开发工具')
        payload={'title':'终端配置','category':'Wiki/不存在','points':['配置字体']}
        with patch('app.llm.compile.chat',AsyncMock(return_value=json.dumps(payload))):
            result=await compile_knowledge('终端配置',rules=load_rules())
        self.assertEqual(result.category,'Wiki/待整理')
        rule.write_text('# 分类规则\n## 生活\n- 目录：Wiki/生活\n- 收录：日常生活\n')
        self.assertEqual(load_rules().select('Wiki/生活'),'Wiki/生活')
        self.assertEqual(load_rules().select('Wiki/开发工具'),'Wiki/待整理')
        rule.write_text('# 分类规则\n## 错误\n- 目录：Wiki/../../escape\n')
        self.assertTrue(load_rules().warning)

    async def test_readable_paths_category_links_and_raw_retry(self):
        from app.vault.collection import rename_source, source_path
        (self.root/'分类规则.md').write_text('# 分类规则\n## 开发工具\n- 目录：Wiki/开发工具\n- 收录：终端\n')
        raw=save_received('task-id','https://example.com','https://example.com')
        renamed,retired=rename_source('task-id','终端配置')
        self.assertEqual(source_path('task-id'),Path(renamed))
        self.assertEqual(save_received('task-id','ignored'),renamed)
        self.assertRegex(renamed,r'^Raw/\d{4}/\d{2}/终端配置.md$')
        self.assertFalse((self.root/retired).exists())
        note=card('终端配置');note.category='Wiki/开发工具'
        path,_=save_page(note,'c'*64,[renamed])
        self.assertEqual(path,'Wiki/开发工具/终端配置.md')
        self.assertIn('../../Raw/',(self.root/path).read_text())
        second,_=save_page(note,'d'*64,[renamed])
        self.assertEqual(second,'Wiki/开发工具/终端配置（2）.md')
        # Moving a note by hand still preserves deduplication and the body.
        moved=self.root/'Wiki/手工目录/我的终端.md';moved.parent.mkdir()
        (self.root/path).rename(moved)
        found,duplicate=save_page(note,'c'*64,[renamed])
        self.assertTrue(duplicate);self.assertEqual(found,'Wiki/手工目录/我的终端.md')

    async def test_title_collision_does_not_overwrite(self):
        save_page(card(),'a'*64,['Raw/a.md']);save_page(card(),'b'*64,['Raw/b.md'])
        self.assertEqual(len(list((self.root/'Wiki').rglob('*.md'))),2)
    async def test_migration_preserves_notes_and_repairs_links(self):
        (self.root/'Wiki/entities').mkdir(parents=True);(self.root/'Wiki/concepts').mkdir();(self.root/'Wiki/queries').mkdir()
        (self.root/'Raw').mkdir();(self.root/'Raw/a.md').write_text('原文')
        (self.root/'Wiki/entities/a.md').write_text('---\ntitle: A\nsources: [Raw/a.md]\n---\n# 我手写的内容\n[原文](../../Raw/a.md)\n[[Wiki/concepts/b]]\n')
        (self.root/'Wiki/concepts/b.md').write_text('# B\n')
        (self.root/'Wiki/queries/q.md').write_text('旧问答')
        (self.root/'index.md').write_text('旧目录')
        r=migrate(self.root,self.base/'backup',True)
        self.assertTrue(r['applied']);self.assertIn('我手写的内容',(self.root/'Wiki/a.md').read_text())
        self.assertIn('../Raw/a.md',(self.root/'Wiki/a.md').read_text());self.assertIn('[[Wiki/b.md]]',(self.root/'Wiki/a.md').read_text())
        self.assertTrue((self.root/'_archive/历史问答/q.md').is_file());self.assertTrue((self.base/'backup/index.md').is_file())

class GitTests(unittest.TestCase):
    def test_conflict_preserves_both_sides_and_never_claims_synced(self):
        old=settings.vault_path
        with tempfile.TemporaryDirectory() as tmp:
            b=Path(tmp);remote=b/'remote.git';a=b/'a';c=b/'c'
            def run(cwd,*args):return subprocess.run(['git',*args],cwd=cwd,capture_output=True,text=True,check=True).stdout.strip()
            run(b,'init','--bare',str(remote));run(b,'clone',str(remote),str(a))
            for k,val in [('user.name','Test'),('user.email','test@example.invalid')]:run(a,'config',k,val)
            (a/'note.md').write_text('base\n');run(a,'add','.');run(a,'commit','-m','base');run(a,'push','-u','origin','HEAD')
            run(b,'clone',str(remote),str(c))
            for k,val in [('user.name','Test'),('user.email','test@example.invalid')]:run(c,'config',k,val)
            (c/'note.md').write_text('human edit\n');run(c,'add','.');run(c,'commit','-m','human');run(c,'push')
            (a/'note.md').write_text('bot edit\n');settings.vault_path=str(a)
            try:
                result=sync_vault('bot',['note.md'])
                self.assertFalse(result.ok);self.assertEqual(result.state,'conflict')
                self.assertEqual((a/'note.md').read_text(),'bot edit\n');self.assertEqual((c/'note.md').read_text(),'human edit\n')
                self.assertFalse((a/'.git/MERGE_HEAD').exists())
            finally:settings.vault_path=old

if __name__=='__main__':unittest.main()
