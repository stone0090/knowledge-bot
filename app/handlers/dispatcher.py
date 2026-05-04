"""飞书事件派发：把消息事件路由到 ingest / query。"""
from __future__ import annotations

import asyncio
import json
from typing import Any

from loguru import logger

from app.feishu import get_feishu_client
from app.parsers.url_reader import FetchError
from app.vault import lint_vault
from app.vault.lint import format_lint_report

from .ingest import ingest
from .query import query
from .cleanup import handle_archive, handle_delete

QUERY_PREFIXES = ("/查", "/q", "/search")
LINT_PREFIXES = ("/lint",)
DELETE_PREFIXES = ("/delete", "/del")
ARCHIVE_PREFIXES = ("/archive",)
SKILL_PREFIXES = ("/skill", "/sk")


def _extract_text(message: dict[str, Any]) -> str:
    """从飞书消息 content 里取出纯文本。"""
    raw = message.get("content") or "{}"
    try:
        data = json.loads(raw) if isinstance(raw, str) else raw
    except json.JSONDecodeError:
        return ""
    # text 消息
    if "text" in data:
        return str(data["text"]).strip()
    # post 消息（富文本）
    if "title" in data or "content" in data:
        parts: list[str] = [str(data.get("title") or "")]
        for row in data.get("content", []) or []:
            for seg in row or []:
                if isinstance(seg, dict) and seg.get("tag") == "text":
                    parts.append(str(seg.get("text", "")))
        return "\n".join(p for p in parts if p).strip()
    return ""


def _extract_file(message: dict[str, Any]) -> tuple[str, str, str] | None:
    """返回 (file_key, file_name, file_type file|image) 或 None。"""
    msg_type = message.get("message_type")
    raw = message.get("content") or "{}"
    try:
        data = json.loads(raw) if isinstance(raw, str) else raw
    except json.JSONDecodeError:
        return None
    if msg_type == "file":
        return data.get("file_key"), data.get("file_name", "unknown"), "file"
    if msg_type == "image":
        return data.get("image_key"), "image.jpg", "image"
    return None


async def _handle_message(event: dict[str, Any]) -> None:
    message = event.get("message") or {}
    message_id = message.get("message_id")
    if not message_id:
        return

    client = get_feishu_client()

    # 文件/图片消息
    file_info = _extract_file(message)
    if file_info:
        file_key, file_name, file_type = file_info
        await client.reply_text(message_id, f"收到 {file_name}，开始整理…")
        try:
            data = await client.download_message_file(message_id, file_key, file_type)
            await ingest(file=(data, file_name), reply_message_id=message_id)
        except Exception as exc:
            logger.exception("ingest file failed: {}", exc)
            await client.reply_text(message_id, f"文件处理失败: {exc}")
        return

    # 文本消息
    text = _extract_text(message)
    if not text:
        return

    if any(text.startswith(p) for p in LINT_PREFIXES):
        try:
            result = await asyncio.to_thread(lint_vault)
            report = format_lint_report(result)
        except Exception as exc:
            logger.exception("lint failed: {}", exc)
            report = f"Lint 失败: {exc}"
        await client.reply_text(message_id, report)
        return

    if any(text.startswith(p) for p in ARCHIVE_PREFIXES):
        await handle_archive(text, reply_message_id=message_id)
        return

    if any(text.startswith(p) for p in DELETE_PREFIXES):
        await handle_delete(text, reply_message_id=message_id)
        return

    if any(text.startswith(p) for p in QUERY_PREFIXES):
        await query(text, reply_message_id=message_id)
        return

    # /skill 分支：剥前缀后走 ingest(as_skill=True)
    for pref in SKILL_PREFIXES:
        if text.startswith(pref):
            payload = text[len(pref):].strip()
            if not payload:
                await client.reply_text(
                    message_id,
                    "用法：`/skill <URL>` 或 `/skill <文本片段>`\n"
                    "作用：精炼为 agent-ready skill → Wiki/skills/\n"
                    "用时手工拷到 `.qoder/skills/` 或 `.claude/skills/`\u3002",
                )
                return
            await client.reply_text(message_id, "收到，正在精炼为 skill…")
            try:
                await ingest(text=payload, reply_message_id=message_id, as_skill=True)
            except FetchError as exc:
                logger.warning("/skill 抓取失败: {}", exc.reason)
                await client.reply_text(message_id, exc.user_hint)
            except Exception as exc:
                logger.exception("/skill failed: {}", exc)
                await client.reply_text(message_id, f"skill 精炼失败: {exc}")
            return

    # 默认当作投喂
    await client.reply_text(message_id, "收到，正在整理…")
    try:
        await ingest(text=text, reply_message_id=message_id)
    except FetchError as exc:
        logger.warning("投喂抓取失败: {}", exc.reason)
        await client.reply_text(message_id, exc.user_hint)
    except Exception as exc:
        logger.exception("ingest text failed: {}", exc)
        await client.reply_text(message_id, f"整理失败: {exc}")


async def dispatch_event(payload: dict[str, Any]) -> None:
    """飞书 v2 事件结构: {schema, header, event}."""
    header = payload.get("header") or {}
    event_type = header.get("event_type") or payload.get("type")
    event = payload.get("event") or {}

    logger.info("event_type = {}", event_type)

    if event_type == "im.message.receive_v1":
        # 业务处理放后台任务，快速给飞书返回
        asyncio.create_task(_handle_message(event))
        return

    logger.debug("忽略事件: {}", event_type)
