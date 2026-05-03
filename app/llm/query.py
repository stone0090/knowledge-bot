"""基于候选文档回答用户问题（Qwen-Long）。"""
from __future__ import annotations

from app.config import settings

from .dashscope_client import chat

SYSTEM_PROMPT = """你是一名知识库助理。根据提供的「候选笔记」回答用户问题。
规则：
- 只使用候选笔记中的内容作答；如信息不足请明确说「资料不足」。
- 回答简洁，使用 Markdown。
- 结尾列出引用，格式：- [标题](URL)。
"""


def _format_candidates(candidates: list[dict]) -> str:
    parts = []
    for i, c in enumerate(candidates, 1):
        parts.append(
            f"### 候选 {i}: {c.get('title', '')}\n"
            f"URL: {c.get('url', '')}\n"
            f"摘要: {c.get('summary', '')}\n"
            f"观点:\n" + "\n".join(f"- {p}" for p in c.get("points", []))
        )
    return "\n\n".join(parts)


async def answer_question(question: str, candidates: list[dict]) -> str:
    if not candidates:
        return "暂未在知识库中找到相关内容。"
    context = _format_candidates(candidates)
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": f"问题：{question}\n\n候选笔记：\n{context}"},
    ]
    return await chat(settings.dashscope_model_query, messages)
