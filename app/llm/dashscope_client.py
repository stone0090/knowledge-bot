"""与百炼通用的调用辅助（走 OpenAI 兼容协议，适配 sk-sp- 类型的 key）。"""
from __future__ import annotations

import json
from typing import Any

import httpx
from loguru import logger

from app.config import settings


async def chat(model: str, messages: list[dict[str, str]], **kwargs: Any) -> str:
    """走百炼 OpenAI 兼容端点 `/chat/completions`，返回 assistant 文本。"""
    if not settings.dashscope_api_key:
        raise RuntimeError("DASHSCOPE_API_KEY 未配置")

    url = settings.dashscope_base_url.rstrip("/") + "/chat/completions"
    headers = {
        "Authorization": f"Bearer {settings.dashscope_api_key}",
        "Content-Type": "application/json",
    }
    payload: dict[str, Any] = {
        "model": model,
        "messages": messages,
    }
    payload.update(kwargs)

    async with httpx.AsyncClient(timeout=httpx.Timeout(60.0, read=120.0)) as client:
        resp = await client.post(url, headers=headers, json=payload)

    if resp.status_code != 200:
        logger.error("dashscope call failed: status={} body={}", resp.status_code, resp.text[:500])
        raise RuntimeError(f"dashscope error {resp.status_code}: {resp.text[:200]}")

    data = resp.json()
    choices = data.get("choices") or []
    if not choices:
        raise RuntimeError(f"dashscope empty choices: {data}")
    message = choices[0].get("message") or {}
    content = message.get("content")
    if not isinstance(content, str):
        raise RuntimeError(f"dashscope unexpected content: {message}")
    return content


def try_parse_json(text: str) -> dict[str, Any] | None:
    """尽可能从模型输出里抽出 JSON 对象。"""
    text = text.strip()
    # 直接解析
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    # 去掉 ```json ... ``` 代码块包裹
    if "```" in text:
        fragments = text.split("```")
        for frag in fragments:
            frag = frag.strip()
            if frag.startswith("json"):
                frag = frag[4:].strip()
            if frag.startswith("{") and frag.endswith("}"):
                try:
                    return json.loads(frag)
                except json.JSONDecodeError:
                    continue
    # 截取第一个 { 到最后一个 }
    start, end = text.find("{"), text.rfind("}")
    if start != -1 and end != -1 and end > start:
        try:
            return json.loads(text[start : end + 1])
        except json.JSONDecodeError:
            return None
    return None
