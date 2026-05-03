"""检索流程：问题 → Vault 本地扫描（ripgrep）→ 百炼生成答案。"""
from __future__ import annotations

import asyncio

from app.feishu import get_feishu_client
from app.llm import answer_question
from app.vault import search_wiki

from .cards import build_answer_card


async def query(question: str, reply_message_id: str | None = None) -> dict:
    client = get_feishu_client()
    keyword = question.strip().lstrip("/查").strip()

    # Vault 本地检索（ripgrep 优先，纯 Python fallback）
    candidates = await asyncio.to_thread(search_wiki, keyword, 5)

    answer = await answer_question(question, candidates)

    if reply_message_id:
        await client.reply_card(reply_message_id, build_answer_card(question, answer))

    return {"ok": True, "answer": answer, "candidates": len(candidates)}
