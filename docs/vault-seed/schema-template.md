# Wiki Schema

> LLM Wiki 运行契约。LLM 每次 ingest / query / lint 前必读本文件。
> 方法论背景见项目代码仓库 `docs/llm-wiki-method.md`。

## Domain

个人 AI / 产品 / 管理领域的研究与实践笔记（stone0090 知识库）。覆盖 LLM 技术进展、产品设计、工程管理、跨端工具链。事实源优先"自己写过 + 消化过 + 干过的"素材，次选业界原始资料。

## Conventions

- 文件名：小写 + 连字符，允许中文（`transformer-architecture.md` / `hermes-技能实战体验.md`）
- 每个 Wiki 页面必须以 YAML frontmatter 开头
- 使用 `[[wikilink]]` 链接页面，**每页至少 2 个出站链接**
- 更新页面必须 bump `updated` 字段
- 新页面必须加入 `index.md` 对应 section（按字母序）
- 每次 ingest / update / archive / lint 追加一条到 `log.md`
- **Provenance marker**（来源锚注）：当页面综合 3+ 来源时，在论点末尾追加 `^[Raw/articles/xxx.md]` 让读者追溯单条声明

## Frontmatter

### Wiki 页面

```yaml
---
title: 页面标题
type: entity | concept | comparison | query | skill
created: YYYY-MM-DD
updated: YYYY-MM-DD
tags: [tag1, tag2]            # 必须来自下方 Tag Taxonomy
sources: [Raw/articles/xxx.md]
# 可选字段（质量信号）
aliases: [别名1, 别名2]        # entity 用，提升检索命中
confidence: high | medium | low
contested: true                # 页内存在未裁决的矛盾
contradictions: [other-slug]   # 与哪个页面冲突（双向标记）
# Skill 页专用字段（type=skill 时必填）
name: agent-skill-slug         # Qoder / Claude Code 等 agent 识别的 slug
description: Use when...       # agent 激活条件（英文，“Use when...” 句式）
---
```

### Raw 页面

```yaml
---
source_type: url | note | file
source_ref: https://example.com/article  # URL 或相对路径
ingested: YYYY-MM-DD
sha256: <hex>                            # body 的 SHA256，去重 + drift 检测
---
```

`sha256` 作用：同一 URL 二次投喂，body 一致则跳过编译；变化则标 drift 触发更新。

## Tag Taxonomy

**所有 tag 必须先登记于此，才能在页面中使用**。新 tag 先加表再用。

| 分组 | tags |
|------|------|
| Models | model, llm, embedding, benchmark, multimodal |
| People/Orgs | person, company, lab, open-source, community |
| Techniques | rag, prompt-engineering, fine-tuning, inference, alignment, agent, tool-use |
| Product | product-design, ux, pm, growth, metrics |
| Mgmt | leadership, okr, hiring, team, process |
| Tools | ide, cli, framework, platform, devops |
| Meta | comparison, timeline, controversy, methodology, reference |
| Flow | ingest, query, lint |
| Skill | agent-skill, workflow, prompt, tooling |

## Page Thresholds

| 动作 | 触发条件 |
|------|---------|
| **建页** | 实体/概念在 2+ 来源出现，或为单个来源的核心 |
| **合并到现有页** | 新来源提到已有页面 |
| **不建页** | 顺带一笔、次要细节、跨领域 |
| **拆页** | 单页超过 ~200 行 → 按子主题拆 + 交叉链接 |
| **归档** | 内容完全过时 → 移到 `_archive/`，从 `index.md` 删除 |

## Page Templates

### Entity Pages（人/产品/公司/模型/工具）

```markdown
# {Title}

## 概述
{一句话：它是什么 + 为什么值得记}

## 关键事实
- 类型：
- 发布/成立：
- 相关方：

## 与其他实体的关系
- [[link-1]]：关系描述
- [[link-2]]：关系描述

## 来源
- Raw/articles/xxx.md
```

### Concept Pages（方法/原理/术语）

```markdown
# {Title}

## 定义
{一句话抽象概括}

## 核心要点
- 要点 1
- 要点 2

## 相关概念
- [[link-1]]
- [[link-2]]

## 开放问题
- 目前的争议或未解之处

## 来源
- Raw/articles/xxx.md
```

### Comparison Pages（A vs B）

```markdown
# {A} vs {B}

## 为什么比
{用户关心哪个维度}

## 对比维度

| 维度 | {A} | {B} |
|------|-----|-----|
| ... | ... | ... |

## 结论
{综合判断}

## 相关
- [[A-entity]]
- [[B-entity]]

## 来源
- Raw/articles/xxx.md
```

### Query Pages（`/查` 回答归档）

```markdown
# {问题原文}

## 上下文
- 提问时间：YYYY-MM-DD HH:mm
- 提问端：feishu

## 回答
{LLM 生成的带引用答案}

## 相关页面
- [[link-1]]
- [[link-2]]
```

### Skill Pages（AI Agent 可消费的结构化技能）

> 定位：**沉淀**一段结构化操作步骤，到使用 Qoder / Claude Code 时手动拷到 `.qoder/skills/` 或 `.claude/skills/` 即可被 agent 读取。
> `name`：agent 识别的 slug（小写 + 连字符）。
> `description`：**必须英文**，“Use when...” / “Covers...” 句式，描述 agent 在什么场景应用该 skill。

```markdown
# {Title}

## Prerequisites
- 前置条件 1（工具 / 环境 / 版本）

## Steps
1. 可直接执行的命令 / 操作
2. ...

## Verify
- 做对了的表现 / 验收信号

## Common Pitfalls
- 踩过的坑 + 规避办法

## Notes
- 作者个人心得 / 扩展阅读
```

## Update Policy

新信息与既有内容冲突时：

1. **对日期**：较新来源通常覆盖旧来源，旧页面 `updated` 日期需 bump
2. **真矛盾**：同时记录两种说法，各附日期 + 来源引用
3. **frontmatter 标记**：冲突两侧都加 `contradictions: [other-slug]`
4. **标 contested**：`contested: true` → lint 浮现 → 等人裁决

## 红绿灯原则（人机边界）

| 灯 | 范围 | 由谁做 |
|----|------|-------|
| 🟢 绿灯 | 摘要生成、索引更新、链接补全、格式调整、孤儿页检查 | LLM 全托管 |
| 🟡 黄灯 | 矛盾裁决、概念合并、过时判定 | lint 时人工确认 |
| 🔴 红灯 | 核心事实写入、价值判断、最终签字 | 只能人做 |

破掉这条 → Wiki 退化为"通用知识的二手转述"，失去个人知识库的核心价值。

## Session Orientation（LLM 每次 ingest / query 必做）

1. 读 `SCHEMA.md`（本文件）—— 了解契约
2. 读 `index.md` —— 知道哪些页面已存在，避免重复
3. 扫 `log.md` 最近 30 条 —— 了解最近活动
4. 对大 Wiki（100+ 页），投喂前先 grep 本次主题
5. 再决定是新建还是合并到现有页
