"""LLM Wiki 编译：原始素材 → 结构化知识卡片。

按 SCHEMA.md 的五类页面（entity/concept/comparison/query/skill）分路：
- entity / concept：默认 ingest 路径 → compile_knowledge()
- skill：/skill 命令触发 → compile_skill()，产出 agent-ready 技能脚本
- comparison / query：其他流程使用
"""
from __future__ import annotations

import re
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


# ---------------------------------------------------------------------------
# Skill 沉淀路径：`/skill <URL|片段>` → agent-ready skill md
# ---------------------------------------------------------------------------

SKILL_PROMPT = """你是一名 AI Agent Skill 工程师，在维护一个个人知识库的 `Wiki/skills/` 目录。
用户投喂一段原文 / 片段，请你把它精炼成一段 **可被 Qoder / Claude Code 等 agent 直接读取激活的结构化技能**。

请严格输出 JSON（不要 Markdown 代码块、不要解释），字段如下：
{
  "title": "一句话标题，中文，不超过 20 字",
  "name": "slug式英文名，小写+连字符，如 'ghostty-quick-start'",
  "description": "**必须英文**，Use when... / Covers... 句式，描述 agent 在什么场景应调用该 skill，限 1-2 句",
  "tags": ["1-3 个标签，从 SCHEMA 已有分组选 (tool/*, agent-skill, workflow, prompt, tooling 等)"],
  "summary": "一句话中文摘要，不超过 80 字",
  "prerequisites": ["前置条件 1（工具/环境/版本）", "..."],
  "steps": ["可执行的步骤 1，带具体命令/操作", "..."],
  "verify": ["验收信号 1（如何判断做对了）", "..."],
  "pitfalls": ["常见坑 1 + 规避办法", "..."],
  "notes": ["扩展阅读 / 个人心得，可为空"],
  "confidence": "high 或 medium 或 low"
}

硬性要求：
- `description` 必须英文且包含 `Use when` 或 `Covers` 关键词，agent 匹配时依赖它。
- `name` 只能含小写英文、数字、连字符；不能以数字开头。
- `steps` 至少 2 条，每条能独立执行；命令语句用反引号包起。
- `prerequisites` / `verify` / `pitfalls` / `notes` 可为空数组，但字段必须存在。
- 若原文信息不足以提练成技能，`confidence` 记 low，`steps` 可少但不能构造不存在的命令。
"""


_SLUG_SAFE = re.compile(r"[^a-z0-9-]+")


def _normalize_skill_name(raw: str, fallback_title: str) -> str:
    """清洗 LLM 返回的 name 为合法 slug，失效回退用 title 的 ASCII 化。"""
    s = (raw or "").strip().lower().replace("_", "-").replace(" ", "-")
    s = _SLUG_SAFE.sub("", s).strip("-")
    if s and not s[0].isdigit():
        return s[:60]
    # 回退：从 title ASCII 化，不行就用 'skill'
    t = (fallback_title or "skill").strip().lower().replace(" ", "-")
    t = _SLUG_SAFE.sub("", t).strip("-")
    return (t or "skill")[:60]


@dataclass
class SkillCard:
    title: str
    name: str                               # agent-readable slug
    description: str                        # 英文激活条件（Use when…）
    tags: list[str]
    summary: str
    prerequisites: list[str]
    steps: list[str]
    verify: list[str]
    pitfalls: list[str]
    notes: list[str] = field(default_factory=list)
    type: str = "skill"
    confidence: str = "medium"

    def to_markdown(self, source_ref: str = "") -> str:
        """正文：Prerequisites / Steps / Verify / Common Pitfalls / Notes 五段。"""
        lines = [f"# {self.title}", ""]
        if self.summary:
            lines += ["## 摘要", self.summary, ""]
        lines += ["## Prerequisites"]
        lines += [f"- {p}" for p in self.prerequisites] or ["- （无）"]
        lines += ["", "## Steps"]
        for i, step in enumerate(self.steps, 1):
            lines.append(f"{i}. {step}")
        if not self.steps:
            lines.append("1. （待补充）")
        lines += ["", "## Verify"]
        lines += [f"- {v}" for v in self.verify] or ["- （无）"]
        lines += ["", "## Common Pitfalls"]
        lines += [f"- {p}" for p in self.pitfalls] or ["- （无）"]
        if self.notes:
            lines += ["", "## Notes"]
            lines += [f"- {n}" for n in self.notes]
        return "\n".join(lines)


async def compile_skill(raw_text: str) -> SkillCard:
    """调用 qwen-max 把原文/片段精炼为 agent-ready skill。"""
    if len(raw_text) > 30000:
        raw_text = raw_text[:30000] + "\n...(内容过长已截断)"

    messages = [
        {"role": "system", "content": SKILL_PROMPT},
        {"role": "user", "content": raw_text},
    ]
    text = await chat(settings.dashscope_model_compile, messages)
    data = try_parse_json(text)
    if not data:
        logger.warning("compile_skill 返回无法解析为 JSON: {}", text[:200])
        first_line = raw_text.splitlines()[0][:20] if raw_text else "Untitled Skill"
        return SkillCard(
            title=first_line or "未命名技能",
            name=_normalize_skill_name("", first_line),
            description="Use when the user asks for a quick how-to covered by this note.",
            tags=["agent-skill"],
            summary=(raw_text[:80] if raw_text else ""),
            prerequisites=[],
            steps=[],
            verify=[],
            pitfalls=[],
            notes=[],
            confidence="low",
        )

    def _as_list(v: Any) -> list[str]:
        if isinstance(v, list):
            return [str(x) for x in v if str(x).strip()]
        if isinstance(v, str) and v:
            return [v]
        return []

    title = str(data.get("title") or "未命名技能").strip()[:40]
    raw_name = str(data.get("name") or "")
    name = _normalize_skill_name(raw_name, title)
    description = str(data.get("description") or "").strip()[:400]
    if "use when" not in description.lower() and "covers" not in description.lower():
        # 强制补 "Use when" 前缀，保 agent 匹配
        description = f"Use when the user asks about {title}. {description}".strip()

    _confidence = str(data.get("confidence") or "medium").strip().lower()
    if _confidence not in {"high", "medium", "low"}:
        _confidence = "medium"

    return SkillCard(
        title=title,
        name=name,
        description=description,
        tags=(_as_list(data.get("tags"))[:5]) or ["agent-skill"],
        summary=str(data.get("summary") or "")[:200],
        prerequisites=_as_list(data.get("prerequisites"))[:10],
        steps=_as_list(data.get("steps"))[:15],
        verify=_as_list(data.get("verify"))[:8],
        pitfalls=_as_list(data.get("pitfalls"))[:8],
        notes=_as_list(data.get("notes"))[:5],
        confidence=_confidence,
    )
