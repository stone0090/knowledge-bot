"""检索流程：问题 → Vault 本地扫描（ripgrep）→ 百炼生成答案 → 回填 Wiki/queries/（后台异步）。"""
from __future__ import annotations

import asyncio

from loguru import logger

from app.feishu import get_feishu_client
from app.llm import answer_question
from app.vault import (
    append_index,
    append_log,
    commit_and_push,
    search_wiki,
    vault_write_gate,
    write_query,
)

from .cards import build_answer_card


async def _persist_query(title_hint: str, answer: str, candidates: list) -> None:
    """后台回填：写 query 文件 + 更新 index/log + git push。失败只记日志不影响主流程。

    共享 vault 写闸锁，与 ingest / cleanup 串行。用户不等后台回填，故不发排队提示。
    """
    try:
        cand_paths = [c.get("path", "") for c in candidates if isinstance(c, dict)]
        async with vault_write_gate.acquire():
            query_rel = await asyncio.to_thread(
                write_query, title_hint, answer, cand_paths
            )
            title = title_hint[:40]
            await asyncio.to_thread(append_index, "query", title, "")
            await asyncio.to_thread(
                append_log, "query", title, str(query_rel).replace("\\", "/")
            )
            await asyncio.to_thread(commit_and_push, f"query: {title}")
        logger.info("query 后台回填完成: {}", query_rel)
    except Exception as exc:  # noqa: BLE001 - best-effort
        logger.warning("query 后台回填失败（不影响主流程）: {}", exc)


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

    # 先回复用户（不等回填）
    if reply_message_id:
        await client.reply_card(
            reply_message_id,
            build_answer_card(question, answer, vault_path=None),
        )

    # 后台 fire-and-forget 回填 Wiki/queries/
    asyncio.create_task(_persist_query(keyword or question, answer, candidates))

    return {
        "ok": True,
        "answer": answer,
        "candidates": len(candidates),
    }
