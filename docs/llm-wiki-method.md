# LLM Wiki 方法论

> 本项目知识整理层的设计准则。基于 Andrej Karpathy 的 [LLM Wiki gist](https://gist.github.com/karpathy/442a6bf555914893e9891c11519de94f) + Nous Research Hermes Agent `llm-wiki` SKILL v2.1 + 王树义「红绿灯原则」。
>
> **运行契约**见 Vault 根的 [SCHEMA.md](../../../opt/vault/SCHEMA.md)（ECS）—— 本文讲"为什么 & 怎么设计"，SCHEMA 讲"怎么执行"。

---

## 1. 为什么不用传统 RAG

传统 RAG 每次查询都从零开始：向量化 → 召回 → 拼 prompt → 生成。你读 50 篇文章喂进去，下次问问题它还是把每篇当作第一次见。

**问题是 RAG 不沉淀**：
- 同一问题两次问可能得两个答案
- 新内容和旧内容对不上，它不会主动发现
- 用得越久，感觉越像金鱼（7 秒记忆）

## 2. LLM Wiki 的核心思路

一句话：**编译，不检索**。

> Obsidian 是你的 IDE，LLM 是你的程序员，Wiki 是你的代码库。

让 LLM 把原始资料**编译**成结构化 markdown（`.md` + frontmatter + `[[wikilink]]`），查询发生在编译后的 Wiki 上，不是原始素材上。这样：

- 每加一条新原材料 → LLM 更新现有页面 + 建交叉链接 + 标冲突
- 所有查询都从"已经整理过的知识"出发，而非从零重新拼凑
- 你的 Wiki 越用越厚，越用越准，**知识复利**

---

## 3. 三层架构

```
vault/
├── SCHEMA.md           # 第 3 层：规则层（人机共同维护的契约）
├── index.md            # 内容目录（按 type 分区的一句话摘要）
├── log.md              # 操作日志（append-only，按年滚动）
├── Raw/                # 第 1 层：原始事实源（LLM 只读，绝不修改）
│   ├── articles/       # 网页文章、剪藏
│   ├── notes/          # 飞书手写笔记
│   ├── papers/         # PDF / 论文
│   ├── transcripts/    # 字幕、会议转录
│   ├── files/          # 二期：PDF/PPT/Excel/Word 结构化
│   └── assets/         # 图片等附件
└── Wiki/               # 第 2 层：LLM 编译产物
    ├── entities/       # 实体页（人/产品/公司/模型/事件）
    ├── concepts/       # 概念页（方法/原理/术语）
    ├── comparisons/    # 对比页（A vs B 分析）
    └── queries/        # 查询归档页（好答案保留）
```

### 三层的契约
| 层 | 写入方 | 读取方 | 变更频率 |
|----|-------|-------|---------|
| Raw | 用户（飞书投喂） | LLM | 高频只进不改 |
| Wiki | LLM（编译） | 用户（Obsidian 阅读）+ LLM（检索） | 中频覆盖更新 |
| SCHEMA | 用户（定契约） | LLM（按契约工作） | 低频迭代 |

**读写分离 + 规则写死 + 规则自身可迭代** —— 这是 Wiki 不变成浆糊的三大支柱。

---

## 4. 四类 Wiki 页面

| type | 用途 | 典型标题 |
|------|------|----------|
| `entity` | 可指称的"物"：人、产品、公司、模型、工具、事件 | `qwen3-max.md`、`andrej-karpathy.md` |
| `concept` | 抽象方法、原理、术语、设计模式 | `llm-wiki-pattern.md`、`rag.md` |
| `comparison` | 两个或多个实体/概念的对比 | `llm-wiki-vs-rag.md` |
| `query` | 来自 `/查` 的高质量回答归档 | `20260504-hermes-llm-wiki-区别.md` |

**判定规则**：
- 指向一个"东西"且有名字 → entity
- 指向一种"做法 / 想法" → concept
- 明显是"A vs B" → comparison
- 来源是用户提问 → query

边界模糊时默认 `entity`（更具体，后期易重构成 concept）。

---

## 5. Frontmatter 规范

### Wiki 页面

```yaml
---
title: Page Title
type: entity | concept | comparison | query
created: YYYY-MM-DD
updated: YYYY-MM-DD
tags: [tag1, tag2]          # 必须来自 SCHEMA.md 的 Tag Taxonomy
sources: [Raw/articles/xxx.md, Raw/papers/yyy.md]
# 可选（质量信号）
aliases: [别名1, 别名2]     # entity 用，提升检索命中
confidence: high | medium | low
contested: true             # 页内存在未裁决的矛盾
contradictions: [page-slug] # 与哪个页面冲突（双向标记）
---
```

### Raw 页面

```yaml
---
source_type: url | note | file
source_ref: https://example.com/article  # 原链接或路径
ingested: YYYY-MM-DD
sha256: <hex>               # body 的 SHA256，用于重复投喂去重 + drift 检测
---
```

**sha256 作用**：同一 URL 重复投喂，body 一致则跳过编译；变化则标"drift"，触发 Wiki 更新。

---

## 6. Tag Taxonomy

### 原则
- 所有 tag 必须**先登记在 SCHEMA.md 的 Tag Taxonomy 表里**，才能使用
- 新 tag 要加进去，先加后用，防 tag sprawl（标签爆炸）
- 顶层分组 10-20 个，过多会让 LLM 选择困难

### 我们的分组（初稿，见 SCHEMA.md 权威版）

| 分组 | tags |
|------|------|
| Models | model, llm, embedding, benchmark |
| People/Orgs | person, company, lab, open-source |
| Techniques | rag, prompt-engineering, fine-tuning, inference, alignment |
| Product | product-design, ux, pm |
| Mgmt | leadership, okr, hiring |
| Meta | comparison, timeline, controversy, methodology |

---

## 7. 页面阈值

| 动作 | 触发条件 |
|------|---------|
| **建页** | 同一实体/概念在 2+ 来源出现，或在单个来源中是核心 |
| **合并到现有页** | 来源提到的实体已有页面 |
| **不建页** | 顺带一笔、次要细节、跨领域 |
| **拆页** | 单页超过 ~200 行，按子主题拆 + 加交叉链接 |
| **归档** | 内容被完全取代 → 移到 `_archive/`，从 `index.md` 删除 |

---

## 8. 更新策略与冲突处理

新信息与旧内容冲突时：

1. **对日期**：较新来源通常覆盖旧来源
2. **真矛盾**：同时记录两种说法，各附日期 + 来源
3. **frontmatter 标记**：冲突两侧都加 `contradictions: [other-page-slug]`
4. **LLM 必须主动触发**：`contested: true`，在 lint 报告里浮现，等人裁决

关键：**LLM 不替人拍板核心事实**，只把矛盾显性化。见下一节红绿灯。

---

## 9. 红绿灯原则（核心价值观）

| 灯 | 范围 | 举例 | 谁来做 |
|----|------|------|-------|
| 🟢 绿灯 | 放心交给 LLM | 摘要、索引、链接补全、格式调整、孤儿页检查 | LLM 全托管 |
| 🟡 黄灯 | 人机共审 | 矛盾裁决、概念合并、过时判定 | lint 时人工确认 |
| 🔴 红灯 | 绝不外包 | 核心事实写入、价值判断、最终签字 | 只能人做 |

破掉这条 → Wiki 退化为"通用知识的二手转述"，失去个人知识库的核心价值。

---

## 10. 工作流

### 10.1 Ingest（投喂）

```
飞书投喂 URL / 文本 / 文件
  → 抓取纯文本
  → 写 Raw/{articles|notes|transcripts|papers|files}/ + sha256 frontmatter
  → LLM 读 SCHEMA.md 判 type
  → 按 type 模板编译 → Wiki/{entities|concepts}/ + 完整 frontmatter
  → indexer: 更新 index.md 对应 section + 追加 log.md
  → git commit + push
  → 飞书卡片回复（带 Vault 路径 + 镜像链接）
```

**LLM 在 ingest 时必须做的 orientation（每次）**：
1. 读 `SCHEMA.md` —— 了解契约
2. 读 `index.md` —— 知道哪些页面已存在，别重复建
3. 扫最近 `log.md` 20-30 行 —— 了解最近活动

### 10.2 Query（查询）

```
/查 关键词
  → ripgrep 扫 Wiki/**/*.md
  → Top-K 候选
  → LLM 带引用生成答案
  → 飞书蓝色卡片回复（含「保存到 Wiki/queries/」按钮）
  → 用户点保存 → write_query() → git push
```

### 10.3 Lint（体检）

建议周期：**每周一次**（或投喂量大时临时触发）。

lint 扫描产物：
- 孤儿页（没有任何地方链接过来）
- 链接数 < 2（SCHEMA 要求每页至少 2 个出站 `[[wikilink]]`）
- `contested: true` 未决项
- `confidence: low` 久未复核（> 30 天）
- 页面 > 200 行（该拆分）
- tag 未登记（不在 Tag Taxonomy 里）
- index.md 里有但文件不存在 / 文件存在但 index.md 没登记

### 红绿灯视角下的 lint
- 🟢 清单生成、格式修复 → LLM 自动
- 🟡 concept 合并建议、过时标记 → 报告给人看
- 🔴 矛盾裁决、事实订正 → 只标不改

---

## 11. 何时不要上

Karpathy 原话：**个人知识库量级下（约 100 篇 / 40 万字以内），index.md + 摘要已足够导航**，不用急着上向量数据库。

等规模超过那个线再谈 RAG 混合。MVP 阶段相信 ripgrep + frontmatter + wikilink。

---

## 12. 参考文献

- [Karpathy LLM Wiki gist](https://gist.github.com/karpathy/442a6bf555914893e9891c11519de94f) —— 原始提法
- [Hermes Agent llm-wiki SKILL.md v2.1](https://github.com/NousResearch/hermes-agent/blob/main/skills/research/llm-wiki/SKILL.md) —— production-ready 标准实现
- [cclank/Hermes-Wiki SCHEMA.md](https://github.com/cclank/Hermes-Wiki/blob/master/SCHEMA.md) —— 真实 SCHEMA 样例
- [docs/references/Karpathy LLM Wiki.md](references/Karpathy%20LLM%20Wiki.md) —— 林月半子的中文导读
- 王树义「红绿灯原则」—— 人机协作边界
