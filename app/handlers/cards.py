"""In-message previews; no duplicate cloud documents."""
from urllib.parse import quote
import re

def preview_markdown(text):
    text=re.sub(r'!?\[\[([^\]|]+)(?:\|([^\]]+))?\]\]',lambda m:m[2] or m[1],text)
    text=re.sub(r'!\[([^\]]*)\]\([^)]*\)',r'[图片：\1]',text)
    return text[:6500]+('\n\n（预览已截短，全文请在 Obsidian 阅读）' if len(text)>6500 else '')

def build_ingest_card(title,summary,tags=None,vault_path='',mirror_url=None,*,preview='',synced=True,duplicate=False,job_id=''):
    status='已同步到 Git' if synced else '已保存到服务器，Git 同步待重试'
    elements=[{'tag':'div','text':{'tag':'lark_md','content':preview_markdown(preview or summary)}},
              {'tag':'div','text':{'tag':'lark_md','content':f'**保存位置**：`{vault_path}`\n**状态**：{status}\n任务：`{job_id}`'}}]
    return {'config':{'wide_screen_mode':True},'header':{'title':{'tag':'plain_text','content':('已收藏过：' if duplicate else '已整理：')+title[:80]},'template':'green' if synced else 'orange'},'elements':elements}

def build_answer_card(question,answer_md,vault_path=None):
    return {'config':{'wide_screen_mode':True},'header':{'title':{'tag':'plain_text','content':'查询：'+question[:60]},'template':'blue'},'elements':[{'tag':'div','text':{'tag':'lark_md','content':preview_markdown(answer_md)}},{'tag':'note','elements':[{'tag':'plain_text','content':'本次回答未自动存入知识库；发送 /保存 可保存最近一次有来源的回答。'}]}]}
