"""URL 投喂本地自测：直接调 ingest(text=url)，绕过飞书 webhook。

流程：URL → Jina Reader 抓取 → LLM 编译 → Vault 写 md → git push → 飞书镜像
"""
from __future__ import annotations

import asyncio
import sys

from loguru import logger


async def main() -> int:
    # 强制 reload settings
    from app import config
    config.get_settings.cache_clear()
    config.settings = config.get_settings()

    from app.handlers.ingest import ingest

    url = sys.argv[1] if len(sys.argv) > 1 else "https://sspai.com/post/78928"
    logger.info("=== URL 投喂测试: {} ===", url)

    result = await ingest(text=url, reply_message_id=None)

    logger.info("result = {}", result)
    if not result.get("ok"):
        logger.error("❌ ingest failed")
        return 1

    logger.success("✅ 投喂成功")
    logger.info("Title : {}", result.get("title"))
    logger.info("Wiki  : {}", result.get("wiki_path"))
    logger.info("Raw   : {}", result.get("raw_path"))
    logger.info("Mirror: {}", result.get("mirror_url"))
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
