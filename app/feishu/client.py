"""飞书 API 轻量封装。

基于官方 OpenAPI，仅封装本项目需要的能力：
1. 发送文本 / 卡片消息
2. 下载用户发来的文件
3. 在指定云盘目录创建 docx 文档（仅用于「知识库-镜像」目录）

注：多维表格（bitable）相关能力已随 M15 下线，改由 app/vault/search.py 用 ripgrep 本地扫描 md 实现。
"""
from __future__ import annotations

import json
from functools import lru_cache
from typing import Any

import httpx
from loguru import logger

from app.config import settings


class FeishuClient:
    """纯 HTTP 实现，避免不同版本 lark-oapi 的差异。"""

    BASE = "https://open.feishu.cn/open-apis"

    def __init__(self, app_id: str, app_secret: str) -> None:
        self.app_id = app_id
        self.app_secret = app_secret
        self._token: str | None = None
        self._client = httpx.AsyncClient(timeout=30.0)

    # ---------- 认证 ----------
    async def _tenant_token(self) -> str:
        # 为简化实现每次都重新获取；生产可加 TTL 缓存
        resp = await self._client.post(
            f"{self.BASE}/auth/v3/tenant_access_token/internal",
            json={"app_id": self.app_id, "app_secret": self.app_secret},
        )
        data = resp.json()
        token = data.get("tenant_access_token")
        if not token:
            raise RuntimeError(f"get tenant_access_token failed: {data}")
        return token

    async def _auth_headers(self) -> dict[str, str]:
        token = await self._tenant_token()
        return {"Authorization": f"Bearer {token}"}

    # ---------- 消息 ----------
    async def reply_text(self, message_id: str, text: str) -> None:
        url = f"{self.BASE}/im/v1/messages/{message_id}/reply"
        headers = await self._auth_headers()
        payload = {
            "msg_type": "text",
            "content": json.dumps({"text": text}, ensure_ascii=False),
        }
        r = await self._client.post(url, headers=headers, json=payload)
        logger.debug("reply_text -> {}", r.text)

    async def reply_card(self, message_id: str, card: dict[str, Any]) -> None:
        url = f"{self.BASE}/im/v1/messages/{message_id}/reply"
        headers = await self._auth_headers()
        payload = {"msg_type": "interactive", "content": json.dumps(card, ensure_ascii=False)}
        r = await self._client.post(url, headers=headers, json=payload)
        logger.debug("reply_card -> {}", r.text)

    async def send_text(self, receive_id: str, text: str, receive_id_type: str = "chat_id") -> None:
        url = f"{self.BASE}/im/v1/messages?receive_id_type={receive_id_type}"
        headers = await self._auth_headers()
        payload = {
            "receive_id": receive_id,
            "msg_type": "text",
            "content": json.dumps({"text": text}, ensure_ascii=False),
        }
        r = await self._client.post(url, headers=headers, json=payload)
        logger.debug("send_text -> {}", r.text)

    # ---------- 文件 ----------
    async def download_message_file(self, message_id: str, file_key: str, file_type: str = "file") -> bytes:
        """下载用户在消息中发送的文件 / 图片。file_type: file | image。"""
        url = f"{self.BASE}/im/v1/messages/{message_id}/resources/{file_key}?type={file_type}"
        headers = await self._auth_headers()
        r = await self._client.get(url, headers=headers)
        r.raise_for_status()
        return r.content

    # ---------- 云文档 ----------
    async def create_docx(self, folder_token: str, title: str) -> dict[str, Any]:
        """在指定文件夹创建一个空 docx，返回 {document_id, url}。"""
        url = f"{self.BASE}/docx/v1/documents"
        headers = await self._auth_headers()
        payload = {"folder_token": folder_token, "title": title}
        r = await self._client.post(url, headers=headers, json=payload)
        data = r.json()
        if data.get("code") != 0:
            raise RuntimeError(f"create_docx failed: {data}")
        document = data["data"]["document"]
        return {
            "document_id": document["document_id"],
            "url": f"https://feishu.cn/docx/{document['document_id']}",
            "title": title,
        }

    async def append_docx_text(self, document_id: str, text: str) -> None:
        """向 docx 追加一段文本（以 text_run 形式写入正文末尾）。"""
        url = f"{self.BASE}/docx/v1/documents/{document_id}/blocks/{document_id}/children"
        headers = await self._auth_headers()
        # 按空行切分段落，批量追加 text block
        paragraphs = [p for p in text.split("\n") if p is not None]
        children = []
        for p in paragraphs:
            children.append({
                "block_type": 2,  # text
                "text": {
                    "elements": [
                        {"text_run": {"content": p, "text_element_style": {}}}
                    ],
                    "style": {},
                },
            })
        # 飞书 API 限制一次最多 50 个 children，分批处理
        for i in range(0, len(children), 50):
            batch = children[i : i + 50]
            payload = {"children": batch, "index": -1}
            r = await self._client.post(url, headers=headers, json=payload)
            if r.json().get("code") != 0:
                logger.warning("append_docx_text batch failed: {}", r.text)


@lru_cache(maxsize=1)
def get_feishu_client() -> FeishuClient:
    return FeishuClient(settings.feishu_app_id, settings.feishu_app_secret)
