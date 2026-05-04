"""M13 端到端自测：直接调 ingest(text=...)，绕过飞书 webhook。

跑通后能验证：LLM 编译 → vault 写 md → git commit + push → 打印结果
"""
from __future__ import annotations

import asyncio
import sys

from loguru import logger

from app.handlers.ingest import ingest


SAMPLE_TEXT = (
    "知识库架构升级说明：\n"
    "本项目从「飞书主存储 + 多维表格索引」彻底切换为「ECS Vault 主存储 + 飞书只读镜像」。"
    "真相源是 ECS /opt/vault 目录下的 markdown 文件 + Git bare 仓库。"
    "所有客户端（桌面/手机 Obsidian + obsidian-git、iOS Working Copy）通过 SSH 或 HTTPS 与 /opt/vault-bare.git 同步，"
    "不依赖任何第三方 SaaS。飞书仅充当 IM 入口和云盘只读镜像端。"
    "检索改为本地 ripgrep 扫 Wiki/*.md，配合 YAML frontmatter 做元数据。"
)


async def main() -> int:
    logger.info("=== M13 end-to-end test: direct ingest() ===")
    result = await ingest(text=SAMPLE_TEXT, reply_message_id=None)
    logger.info("result = {}", result)
    if not result.get("ok"):
        logger.error("❌ ingest failed")
        return 1
    logger.success("✅ ingest OK")
    logger.info("Raw  : {}", result.get("raw_path"))
    logger.info("Wiki : {}", result.get("wiki_path"))
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
