# LLM Wiki 体系重构（M9-Wiki）

## 背景与目标

**现状盘点**
- 管道已通：飞书 → compile → Vault → git → 多端 Obsidian（PC / Android 双向实时）
- 骨架已在：`Raw/{articles,notes,files,videos}` + `Wiki/{entities,concepts,comparisons,queries}` + `Wiki/index.md` + `Wiki/log.md`
- 差在"规则层"：**`SCHEMA.md` 不存在**、frontmatter 字段薄、无页面阈值、无冲突处理、无 lint、index/log 位置不标准

**权威参照**
- Karpathy 原始 gist（提出 LLM Wiki 模式）
- Hermes Agent `llm-wiki` SKILL v2.1（production-ready 标准实现）
- 王树义「红绿灯原则」（已纳入 architecture.md）

**目标（验收口径）**
写入一条新内容 → LLM 按 SCHEMA 识别 type → entity/concept 分别落盘 + frontmatter 完整 → index.md/log.md 自动更新 → 冲突时 flag `contested` → 周期 lint 产出健康报告

---

## 阶段 A · 方法论与契约（docs-first，不碰代码）

### A1. 新增 `docs/llm-wiki-method.md`（项目方法论长文）
- 核心理念：RAG vs Wiki、"编译而非检索"、知识复利
- 三层架构：Raw（只读事实源）/ Wiki（LLM 编译）/ SCHEMA（契约）
- 四类页面：entity / concept / comparison / query
- Frontmatter 字段规范（含 `type` `updated` `sources` `confidence` `contested` `contradictions`）
- Tag Taxonomy 方法（分组列举 + 新标签必须先入表）
- 页面阈值（2+ 来源建页、200 行拆分、完全过时归档 `_archive/`）
- 更新策略（冲突检测 + contradictions 交叉标记）
- 红绿灯原则（已存在）
- 工作流三件套：ingest / query / lint
- 参考文献

### A2. 新增 `/opt/vault/SCHEMA.md`（Vault 运行契约，LLM 在 runtime 读这个）
- `Domain` 一句话（**决策点 1**）
- Conventions（文件命名、wikilink 规则、每次更新 bump `updated`）
- Wiki Frontmatter 模板 + Raw Frontmatter 模板（含 `sha256` 去重）
- Tag Taxonomy 分组表（基于现有 area 枚举扩展）
- Page Thresholds 具体数值
- 4 类页面模板（entity / concept / comparison / query 各给一段 markdown）
- Update Policy

### A3. 现有文档对齐
- `docs/architecture.md`：三层架构段升级到 Karpathy/Hermes 标准版本，图里补 `SCHEMA.md` / `index.md` / `log.md`
- `docs/todo.md`：拆 M9 为 M9a/b/c；M10 描述细化；M12 lint 按新方法重述
- `README.md`：加一句"LLM Wiki 方法论见 docs/llm-wiki-method.md"

---

## 阶段 B · Vault 骨架就位（ECS 文件操作）

### B1. 清理 & 初始化
- 删除 5 个接入测试 md：`pc-obsidian-pull-test.md`、`android-obsidian-pull-test.md`、`android-connectivity-test.md`、`obsidian-https-test.md`、`termux-sync-test.md`（**决策点 3**）
- `Wiki/index.md` → `/opt/vault/index.md`（按 Karpathy 规范放 vault 根）
- `Wiki/log.md` → `/opt/vault/log.md`（同上）
- 落地 `/opt/vault/SCHEMA.md`（A2 产物）

### B2. Raw 子目录对齐（**决策点 2**）

| 现状 | 目标 | 说明 |
|---|---|---|
| Raw/articles | Raw/articles | ✅ |
| Raw/notes | Raw/notes | ✅（Karpathy 无，我们需要） |
| Raw/files | Raw/files | ✅（二期多格式用） |
| Raw/videos | `Raw/transcripts` | 改名更准确（yt-dlp 结果是字幕文本） |
| — | Raw/papers | 新增，PDF/论文 |
| — | Raw/assets | 新增，图片等 |

### B3. 存量 Wiki 页迁移
唯一真实内容页 `Wiki/entities/Hermes-技能实战体验.md`：
- 升级 frontmatter 到新规范（补 `type: entity`、`updated`、`sources`）
- 补内容到 `index.md` Entities 分区

---

## 阶段 C · 代码改造

### C1. `app/llm/compile.py`（M9 主体）
- SYSTEM_PROMPT 升级：先判 `type`（entity / concept）再按模板产出
- 输出 JSON 加 `type`；`aliases`（entity 用）、`related`（已有）、`confidence` 可选
- `KnowledgeCard` → `WikiPage` 数据类（多 type 统一接口）

### C2. `app/vault/writer.py`
- 按 `type` 分路径：`Wiki/entities/` 或 `Wiki/concepts/`
- Frontmatter 升级到新字段（`title/created/updated/type/tags/sources/confidence`）
- `write_wiki` 拆成 `write_entity` / `write_concept`（便于后续扩 comparison/query）

### C3. 新增 `app/vault/indexer.py`
- `append_log(action, subject)` → `/opt/vault/log.md`（追加）
- `upsert_index(page)` → `/opt/vault/index.md` 对应 type section（按字母序插入）

### C4. 卡片回填 queries（= 原 M10）
- `build_answer_card` 加「保存到 Wiki/queries/」action button
- `dispatcher.py` 接收 card action callback
- 新增 `write_query(question, answer)` → `Wiki/queries/{stamp}-{slug}.md`
- 触发 git commit + push + 飞书卡片反馈

### C5. Lint 工作流（= 原 M12 提前，**决策点 4**）
- `app/vault/lint.py` 扫 `Wiki/**` 产出报告：孤儿页 / 链接数 < 2 / `contested: true` 未决 / `confidence: low` 未复核 / 200 行超限 / taxonomy 未登记的 tag
- 飞书 `/lint` 命令触发 → 生成报告卡片

---

## 决策点（等你拍板）

| # | 问题 | 选项 |
|---|---|---|
| 1 | SCHEMA.md 的 `Domain` 一句话怎么写？ | 默认草案："个人 AI / 产品 / 管理领域的研究与实践笔记" |
| 2 | Raw/ 改名是否接受？`videos → transcripts` + 新增 `papers` `assets` | ⭐ 建议接受 |
| 3 | 是否一次删掉 5 个接入测试 md？ | ⭐ 建议删（任务已闭环，留着噪音） |
| 4 | Lint (C5) 是否跟 M9 一起做？ | ⭐ 建议做（否则 Wiki 会退化吃灰） |

---

## 执行顺序

```
A1 A2 A3 (文档)  →  B1 B2 B3 (骨架)  →  C4 (M10)  →  C1 C2 C3 (M9)  →  C5 (lint)
      1d               0.5d            0.5d          2d             1d
```

- 阶段 A 我立刻开工（不等决策点 1，先写草案你来改）
- 阶段 C 等你 review A 的 SCHEMA 后再动（免得写完返工）
- **阶段 C4（M10）独立性高**，可随时插入

---

## 风险 & 降级

- **SCHEMA 写重了** → LLM 输出不稳定。对策：MVP 阶段 frontmatter 只上必须 5 字段，`contested/contradictions` 等可选字段慢慢加
- **index/log 并发写冲突** → 多端同时投喂时罕见。对策：写 vault 用同一进程锁
- **Lint 初期噪声大** → 存量页都缺字段会爆报告。对策：首次 lint 只看新页，旧页标 `legacy: true` 豁免

---

## 产出清单（完工后）

- `docs/llm-wiki-method.md`（新）
- `/opt/vault/SCHEMA.md`（新，随 git 分发多端）
- `/opt/vault/index.md` + `/opt/vault/log.md`（迁移 + 规范化）
- `docs/architecture.md` / `docs/todo.md` / `README.md`（对齐）
- `app/llm/compile.py` / `app/vault/writer.py` / `app/handlers/query.py` / `app/handlers/cards.py`（改）
- `app/vault/indexer.py` / `app/vault/lint.py`（新）