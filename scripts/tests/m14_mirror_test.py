"""M14 飞书镜像自测：投喂一段文本 → vault 写入 + 飞书 docx 镜像。

直接 reload settings 使 FEISHU_MIRROR_FOLDER_TOKEN 生效。
"""
from __future__ import annotations

import asyncio
import sys

from loguru import logger


async def main() -> int:
    # 强制 reload settings（绕过 lru_cache）
    from app import config
    config.get_settings.cache_clear()
    new_settings = config.get_settings()
    config.settings = new_settings
    logger.info("FEISHU_MIRROR_FOLDER_TOKEN = {}", new_settings.feishu_mirror_folder_token)

    if not new_settings.feishu_mirror_folder_token:
        logger.error("❌ token 为空，检查 .env")
        return 1

    from app.handlers.ingest import ingest

    result = await ingest(
        text=(
            "M14 飞书镜像验证：\n"
            "本次测试投喂一段文字，验证 vault 写入正常后，"
            "飞书云盘「知识库-镜像」目录下应自动出现一个 docx 文件。"
            "如果看到这个文档说明 best-effort 镜像链路已完全打通。"
        ),
        reply_message_id=None,
    )

    logger.info("result = {}", result)
    if not result.get("ok"):
        logger.error("❌ ingest failed")
        return 1

    if result.get("mirror_url"):
        logger.success("✅ 飞书镜像成功: {}", result["mirror_url"])
    else:
        logger.warning("⚠️ 飞书镜像返回 None（可能 token 无效或权限不足）")
        return 1

    logger.info("Wiki : {}", result.get("wiki_path"))
    logger.info("Raw  : {}", result.get("raw_path"))
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
