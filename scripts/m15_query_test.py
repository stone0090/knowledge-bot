"""M15 检索自测：直接调 query()，绕过飞书 webhook。

跑通后能验证：ripgrep 扫 Wiki → LLM 生成答案 → 打印结果
"""
from __future__ import annotations

import asyncio
import sys

from loguru import logger

from app.handlers.query import query


async def main() -> int:
    logger.info("=== M15 search test ===")

    # 1. 有匹配的关键词
    result = await query("/查 知识库架构", reply_message_id=None)
    logger.info("result = {}", result)
    if not result.get("ok"):
        logger.error("❌ query failed")
        return 1
    logger.success("✅ 检索成功，候选 {} 篇", result.get("candidates", 0))
    logger.info("答案摘要: {}", result.get("answer", "")[:200])

    # 2. 空关键词（应返回最近修改的 N 篇）
    result2 = await query("/查 ", reply_message_id=None)
    logger.info("空关键词 result = {}", result2)
    logger.success("✅ 空关键词也跑通，候选 {} 篇", result2.get("candidates", 0))

    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
