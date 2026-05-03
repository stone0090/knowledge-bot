"""LLM Wiki 归纳：原始素材 → 结构化 JSON。"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from loguru import logger

from app.config import settings

from .dashscope_client import chat, try_parse_json

SYSTEM_PROMPT = """你是一名知识架构师。用户会给你一段原始资料，请将其整理为结构化知识条目。
请严格输出 JSON（不要包含 Markdown 代码块、不要解释），字段如下：
{
  "title": "用一句话概括的标题，不超过 20 字",
  "tags": ["3-5 个关键词"],
  "area": "Concepts 或 Areas-AI 或 Areas-Product 或 Areas-Mgmt 或 Archives",
  "summary": "一句话摘要，不超过 80 字",
  "points": ["核心观点 1", "核心观点 2", "..."],
  "related": ["可能关联的已有词条标题，若不确定可为空数组"]
}
要求：
- 所有字段都必须存在。
- 标题不要带书名号、不要带「xxx 总结」之类冗余。
- points 精炼，不超过 8 条。
"""


@dataclass
class KnowledgeCard:
    title: str
    tags: list[str]
    area: str
    summary: str
    points: list[str]
    related: list[str]

    def to_markdown(self, source_ref: str = "") -> str:
        """编译产物的正文部分；元数据（title/tags/area/source）由 vault.writer 写入 frontmatter。"""
        lines = [
            f"# {self.title}",
            "",
            "## 摘要",
            self.summary,
            "",
            "## 核心观点",
        ]
        lines += [f"- {p}" for p in self.points]
        if self.related:
            lines += ["", "## 关联"]
            lines += [f"- [[{r}]]" for r in self.related]
        return "\n".join(lines)


async def compile_knowledge(raw_text: str) -> KnowledgeCard:
    """调用 qwen-max 把原始文本归纳为知识卡片。"""
    # 超长文本截断，避免超出上下文
    if len(raw_text) > 30000:
        raw_text = raw_text[:30000] + "\n...(内容过长已截断)"

    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": raw_text},
    ]
    text = await chat(settings.dashscope_model_compile, messages)
    data = try_parse_json(text)
    if not data:
        logger.warning("compile 返回无法解析为 JSON: {}", text[:200])
        # 兜底：只生成最简卡片
        return KnowledgeCard(
            title=raw_text.splitlines()[0][:20] if raw_text else "未命名笔记",
            tags=[],
            area="Archives",
            summary=(raw_text[:80] if raw_text else ""),
            points=[],
            related=[],
        )

    def _as_list(v: Any) -> list[str]:
        if isinstance(v, list):
            return [str(x) for x in v]
        if isinstance(v, str) and v:
            return [v]
        return []

    return KnowledgeCard(
        title=str(data.get("title") or "未命名笔记").strip()[:40],
        tags=_as_list(data.get("tags"))[:5],
        area=str(data.get("area") or "Archives"),
        summary=str(data.get("summary") or "")[:200],
        points=_as_list(data.get("points"))[:8],
        related=_as_list(data.get("related"))[:8],
    )
