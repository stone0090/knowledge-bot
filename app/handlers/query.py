"""检索流程：问题 → Vault 本地扫描（ripgrep）→ 百炼生成答案 → 回填 Wiki/queries/。"""
from __future__ import annotations

import asyncio

from loguru import logger

from app.feishu import get_feishu_client
from app.llm import answer_question
from app.vault import append_index, append_log, commit_and_push, search_wiki, write_query

from .cards import build_answer_card


async def query(question: str, reply_message_id: str | None = None) -> dict:
    client = get_feishu_client()
    # 去掉前缀命令
    keyword = question.strip()
    for pfx in ("/查", "/q", "/search"):
        if keyword.startswith(pfx):
            keyword = keyword[len(pfx):].strip()
            break

    # Vault 本地检索（ripgrep 优先，纯 Python fallback）
    candidates = await asyncio.to_thread(search_wiki, keyword, 5)
    answer = await answer_question(question, candidates)

    # 回填 Wiki/queries/（best-effort）
    query_rel = None
    try:
        cand_paths = [c.get("path", "") for c in candidates if isinstance(c, dict)]
        query_rel = await asyncio.to_thread(
            write_query, keyword or question, answer, cand_paths
        )
        title = (keyword or question)[:40]
        await asyncio.to_thread(append_index, "query", title, "")
        await asyncio.to_thread(
            append_log, "query", title, str(query_rel).replace("\\", "/")
        )
        await asyncio.to_thread(commit_and_push, f"query: {title}")
    except Exception as exc:  # noqa: BLE001 - best-effort
        logger.warning("write_query 回填失败（不影响主流程）: {}", exc)

    if reply_message_id:
        vault_path = str(query_rel).replace("\\", "/") if query_rel else None
        await client.reply_card(
            reply_message_id,
            build_answer_card(question, answer, vault_path=vault_path),
        )

    return {
        "ok": True,
        "answer": answer,
        "candidates": len(candidates),
        "query_path": str(query_rel).replace("\\", "/") if query_rel else None,
    }
