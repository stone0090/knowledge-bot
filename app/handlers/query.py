"""Read-only retrieval. Answers are only persisted by an explicit /保存 command."""
from __future__ import annotations
import asyncio
from app.vault.search import search_wiki
from app.llm import answer_question

async def query(question: str, reply_message_id=None):
    keyword=question.strip()
    for prefix in ('/search','/查','/q'):
        if keyword==prefix or keyword.startswith(prefix+' '):
            keyword=keyword[len(prefix):].strip();break
    candidates=await asyncio.to_thread(search_wiki,keyword,5)
    answer=await answer_question(keyword,candidates)
    return {'ok':True,'question':keyword,'answer':answer,'candidates':candidates}
