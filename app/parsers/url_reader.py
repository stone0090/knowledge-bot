"""URL 抓取：优先使用 Jina AI Reader，无需 API Key。"""
from __future__ import annotations

import httpx
from loguru import logger

JINA_READER = "https://r.jina.ai/"


async def fetch_url_as_markdown(url: str) -> str:
    """将任意 URL 的主要内容转为 Markdown 文本。"""
    target = JINA_READER + url
    async with httpx.AsyncClient(timeout=30.0, follow_redirects=True) as client:
        r = await client.get(target, headers={"Accept": "text/plain"})
        if r.status_code != 200:
            logger.warning("jina reader failed {} -> {}", url, r.status_code)
            raise RuntimeError(f"jina reader status={r.status_code}")
        return r.text
