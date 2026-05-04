"""LLM Wiki 编译：原始素材 → 结构化知识卡片。

按 SCHEMA.md 的四类页面（entity/concept/comparison/query）分路；
当前 MVP 仅区分 entity 与 concept（ingest 路径）。
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from loguru import logger

from app.config import settings

from .dashscope_client import chat, try_parse_json

SYSTEM_PROMPT = """你是一名知识架构师，在维护一个 LLM Wiki（Karpathy 方法论）。
用户会给你一段原始资料，请将其编译为一篇知识卡片。
请严格输出 JSON（不要 Markdown 代码块、不要解释），字段如下：
{
  "type": "entity 或 concept",            // entity: 人/工具/公司/项目；concept: 方法论/原则/术语
  "title": "一句话标题，不超过 20 字",
  "aliases": ["别名 / 缩写，若无为空数组"],
  "tags": ["3-5 个标签，优先从 SCHEMA.md 已有分组选（如 tool/agent, concept/rag, people/karpathy, meta/experience）"],
  "summary": "一句话摘要，不超过 80 字",
  "points": ["核心观点 1", "核心观点 2", "..."],
  "related": ["可能关联的已有词条标题，不确定可为空数组"],
  "confidence": "high 或 medium 或 low"    // 对素材结论的确定性
}
要求：
- 所有字段都必须存在；aliases / related 可为空数组。
- 标题不要带书名号、不要带「xxx 总结」之类冗余。
- points 精炼，不超过 8 条。
- 标签正文不要重复，格式统一为 英文小写/斩马分组 或 混中文单词。
- type 只能二选一：实体（有名有姓的东西）记 entity；方法/观点/原则记 concept。
"""


@dataclass
class KnowledgeCard:
    title: str
    tags: list[str]
    summary: str
    points: list[str]
    related: list[str]
    type: str = "entity"               # entity | concept
    aliases: list[str] = field(default_factory=list)
    confidence: str = "medium"         # high | medium | low

    def to_markdown(self, source_ref: str = "") -> str:
        """编译产物的正文部分；frontmatter（type/title/aliases/tags/…）由 vault.writer 写入。"""
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
            summary=(raw_text[:80] if raw_text else ""),
            points=[],
            related=[],
            type="entity",
            aliases=[],
            confidence="low",
        )

    def _as_list(v: Any) -> list[str]:
        if isinstance(v, list):
            return [str(x) for x in v]
        if isinstance(v, str) and v:
            return [v]
        return []

    _type = str(data.get("type") or "entity").strip().lower()
    if _type not in {"entity", "concept"}:
        _type = "entity"
    _confidence = str(data.get("confidence") or "medium").strip().lower()
    if _confidence not in {"high", "medium", "low"}:
        _confidence = "medium"

    return KnowledgeCard(
        title=str(data.get("title") or "未命名笔记").strip()[:40],
        tags=_as_list(data.get("tags"))[:5],
        summary=str(data.get("summary") or "")[:200],
        points=_as_list(data.get("points"))[:8],
        related=_as_list(data.get("related"))[:8],
        type=_type,
        aliases=_as_list(data.get("aliases"))[:5],
        confidence=_confidence,
    )
