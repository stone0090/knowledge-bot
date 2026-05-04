"""投喂流程：原始素材 → Vault（主）→ Git push → 飞书镜像（best-effort）。"""
from __future__ import annotations

import asyncio
from pathlib import Path

from loguru import logger

from app.config import settings
from app.feishu import get_feishu_client
from app.llm import compile_knowledge
from app.parsers import parse_any
from app.parsers.dispatcher import ParsedContent
from app.parsers.url_reader import FetchError
from app.vault import (
    append_log,
    append_index,
    commit_and_push,
    vault_write_gate,
    write_raw,
    write_wiki,
)

from .cards import build_ingest_card


async def _mirror_to_feishu(title: str, markdown: str) -> str | None:
    """best-effort：把 Wiki md 镜像为飞书 docx；失败仅告警不中断主流程。"""
    folder_token = settings.feishu_mirror_folder_token
    if not folder_token:
        logger.info("未配置 FEISHU_MIRROR_FOLDER_TOKEN，跳过飞书镜像")
        return None
    try:
        client = get_feishu_client()
        doc = await client.create_docx(folder_token, title)
        await client.append_docx_text(doc["document_id"], markdown)
        return doc["url"]
    except Exception as exc:  # noqa: BLE001 - best-effort
        logger.warning("飞书镜像失败（不影响主流程）: {}", exc)
        return None


async def ingest(*, text: str | None = None, file: tuple[bytes, str] | None = None,
                 reply_message_id: str | None = None) -> dict:
    """执行完整投喂流程，返回结果字典。"""
    client = get_feishu_client()

    # 1. 解析
    try:
        parsed: ParsedContent = await parse_any(text=text, file=file)
    except FetchError as exc:
        logger.warning("抓取失败: {}", exc.reason)
        if reply_message_id:
            await client.reply_text(reply_message_id, exc.user_hint)
        return {"ok": False, "reason": exc.reason}
    if not parsed.text.strip():
        if reply_message_id:
            await client.reply_text(reply_message_id, "抱歉，未解析到有效内容。")
        return {"ok": False, "reason": "empty"}

    # 2. 归纳（LLM）——在锁外执行，避免 LLM 超时挂住闸道
    card = await compile_knowledge(parsed.text)

    # 3-4. 写 Vault + git push（共享 vault 写闸锁，排队时先提示用户）
    wiki_markdown = card.to_markdown(parsed.source_ref)

    async def _notify_queued(ahead: int) -> None:
        if reply_message_id:
            await client.reply_text(
                reply_message_id,
                f"⏳ 前方还有 {ahead} 个任务处理中，收到的内容已排队…",
            )

    async with vault_write_gate.acquire(on_queued=_notify_queued):
        raw_rel: Path = await asyncio.to_thread(
            write_raw,
            card.title,
            parsed.source_type,
            parsed.source_ref,
            parsed.text,
        )
        wiki_rel: Path = await asyncio.to_thread(
            write_wiki,
            type=card.type,
            title=card.title,
            tags=card.tags,
            summary=card.summary,
            source_ref=str(raw_rel).replace("\\", "/"),
            body_markdown=wiki_markdown,
            aliases=card.aliases,
            confidence=card.confidence,
        )
        await asyncio.to_thread(append_index, card.type, card.title, card.summary)
        await asyncio.to_thread(append_log, card.type, card.title, str(wiki_rel).replace("\\", "/"))
        await asyncio.to_thread(commit_and_push, f"ingest: {card.title}")

    # 5. 飞书镜像（best-effort，锁外）
    mirror_url = await _mirror_to_feishu(card.title, wiki_markdown)

    # 6. 回复卡片
    if reply_message_id:
        await client.reply_card(
            reply_message_id,
            build_ingest_card(
                title=card.title,
                summary=card.summary,
                tags=card.tags,
                vault_path=str(wiki_rel).replace("\\", "/"),
                mirror_url=mirror_url,
            ),
        )

    return {
        "ok": True,
        "title": card.title,
        "wiki_path": str(wiki_rel).replace("\\", "/"),
        "raw_path": str(raw_rel).replace("\\", "/"),
        "mirror_url": mirror_url,
    }
