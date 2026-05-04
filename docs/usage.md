# 使用手册

> 面向最终用户（自己/家人/团队）的飞书机器人使用指南。方法论见 [llm-wiki-method.md](llm-wiki-method.md)，架构见 [architecture.md](architecture.md)。

## 总览

knowledge-bot 在飞书里提供 **5 种命令** + **1 种默认行为**：

| 动作 | 触发 | 效果 |
|------|------|------|
| 投喂（ingest） | 直接发送文本 / URL / 文件 | 解析 → LLM 编译 → 写入 Vault → Git push → 飞书镜像 |
| 检索（query） | `/查 <问题>` 或 `/q` / `/search` | ripgrep 扫 Wiki → LLM 生成带引用回答 → 自动回填 `Wiki/queries/` |
| 体检（lint） | `/lint` | 扫描 Wiki 全量，报告 frontmatter/孤儿页/遗留字段问题 |
| 归档（archive） | `/archive <标题>` | Wiki 页 + Raw 原文 mv 到 `_archive/`，从 index 移除（可恢复） |
| 删除（delete） | `/del <标题>` 或 `/delete` | 硬删 Wiki 页 + Raw 原文（不可恢复，仅 git history 有） |

所有写入都自动 `git commit && git push`，多端 Obsidian 下一次 pull 即可看到。

## 1. 投喂（Ingest）

### 1.1 直接发文本

飞书对话框粘贴任意一段文字：

```
最近读到一个观点：LLM Wiki 的核心不是检索，而是"每次 ingest 前都重读 SCHEMA.md"……
```

机器人会：

1. `Raw/notes/<时间戳>-<标题>.md` 保存原文（frontmatter: `source_type=text, source_ref=inline, ingested=...`）
2. LLM 按 SCHEMA.md 编译为 **entity** 或 **concept** 页 → `Wiki/entities/` 或 `Wiki/concepts/`
3. `index.md` / `log.md` 自动追加条目
4. 飞书卡片回复标题、摘要、Vault 相对路径

### 1.2 发送 URL

支持通用网页、微信公众号 `/s/*`、YouTube/B站字幕、Twitter/X（降级）。只发链接即可：

```
https://mp.weixin.qq.com/s/xxxxxxxxx
```

失败时卡片会提示"请复制正文发送"。

### 1.3 发送文件

Word / PPT / Excel / PDF（二期 markitdown）。当前一期仅 URL + 文本。

## 2. 检索（Query）

### 2.1 命令格式

```
/查 什么是 LLM Wiki 的红绿灯原则
/q hermes agent
/search 2026 LLM benchmark
```

### 2.2 行为

1. 对 vault 的 `Wiki/**/*.md` 做 ripgrep 关键词召回（Top-5）
2. 调用 qwen 生成带引用答案
3. 自动写入 `Wiki/queries/<时间戳>-<问题slug>.md`（frontmatter type=query）
4. 飞书蓝色卡片回复，附 Vault 路径

### 2.3 为什么要回填

`/查` 的问题往往反映真实检索动机。固化到 Wiki/queries/ 后：

- 同类问题二次发问，ripgrep 可直接命中历史答卷
- lint 周报能看到"被问得最多的主题"→ 倒推补哪块内容
- 是 LLM Wiki "Compile once, query forever" 的关键闭环

## 3. 体检（Lint）

```
/lint
```

机器人扫一遍 `Wiki/**/*.md`，按类别分组报告问题：

- **缺 frontmatter**：md 开头不是 `---`
- **必填字段缺失**：type / title / created / updated / sources / tags 其一为空
- **type 值非法**：不在 `{entity, concept, comparison, query}`
- **遗留旧版字段**：存在 `area` / `summary` / `source_ref` / `created_at`（方法论切换前的字段）
- **孤儿页**：页面 title 未在 `index.md` 出现

问题超过 10 条的类别会折叠显示。lint 只读不改，可随时触发。

## 4. 跨端阅读

Vault 是 git 仓库，Obsidian Git 插件做同步，详见 [obsidian-git.md](obsidian-git.md)：

- **PC（桌面）**：SSH (port 4500) 或 HTTPS (port 4581)
- **Android**：obsidian-git + HTTPS
- **iOS**：Working Copy + SSH

每次投喂成功后，各端 `pull` 一下即可看到新页。推荐开启插件的 `autoPullOnBoot` + `autoPull interval`。

## 5. 常见问题

### 5.1 我发了 URL 但回复"请复制正文发送"

抓取层失败（登录态、反爬、CDN 403）。按提示从网页复制正文直接粘贴到飞书，机器人会当普通文本处理。

### 5.2 同一篇文章二次投喂会重复吗

当前一期会重复写 Raw（时间戳不同），但 Wiki 页会被同 slug 覆盖更新。二期会基于 `sha256` 做 drift 检测，内容一致则跳过编译。

### 5.3 Wiki 页生成得不对，怎么改

Obsidian 任一端直接手改 → `git push`。下次 `/lint` 会校验 frontmatter 是否仍合规。红绿灯原则下这是**红灯**范畴：核心事实以人写入为准，LLM 不覆盖。

### 5.3a 数据不对想删除

优先用 `/archive <标题>`（软删，可从 git 恢复）——这是符合 SCHEMA.md 约定的标准路径。

**支持三种输入**（任选其一）：

```
/archive Hermes 技能实战体验              # 1. frontmatter.title（自然语言，含空格）
/archive Hermes-技能实战体验              # 2. 文件名 stem（连字符 slug）
/archive Raw/notes/20260504-001224-Hermes.md  # 3. Vault 相对路径（Wiki/开头或 Raw/开头）
```

匹配规则：大小写不敏感，连字符/下划线/空格三者等价。

动作：

1. 找到 Wiki 页（或 Raw 路径反查回对应 Wiki 页），依据其 `sources` 字段一起处理 Raw 原文
2. `Wiki/entities/xxx.md` → `_archive/Wiki/entities/xxx.md`（保持相对路径）
3. `Raw/notes/yyy.md` → `_archive/Raw/notes/yyy.md`
4. `index.md` 移除 `[[标题]]` 条目，`log.md` 追加 `archived` 时间线
5. `commit && push`；各端 Obsidian pull 后即不再看到（`_archive/` 不被 `/查` / `/lint` 扫描）

如果 Raw 是孤儿文件（没有任何 Wiki 页的 `sources` 引用它），传 Raw 路径就会只处理该 Raw。

确认永久丢弃用 `/del <标题>`：相同匹配逻辑，但是 **rm** 而非 mv。git history 依然能找回内容，但当前树纯净。

批量处理：连续发几条 `/del xxx` / `/archive yyy` 即可，没有一次性多选，避免误杀。

### 5.4 `/查` 的回填能关掉吗

默认开启且无开关。但**回填已是后台异步**：飞书卡片在 LLM 答案生成后立即回复，`write_query` + `commit_and_push` 在后台进行，不阻塞主流程。你看到答案后约 1-3 秒，`index.md` 和 `Wiki/queries/` 才会更新。

为什么保留这个机制：

- **二次命中免 LLM**：同类问题再问时 ripgrep 会先在 `Wiki/queries/` 里命中旧答卷
- **主题风向标**：每周看 `/lint` 报告时，被问得最多的主题就是下步要补的 Wiki 内容
- **知识资产化**：问答本身也是一手素材，符合 Karpathy *compile once, query forever*

如果真想关掉：编辑 [query.py](../app/handlers/query.py) 注掉 `asyncio.create_task(_persist_query(...))` 一行即可。未来会加飞书按钮「保存 / 不保存」。

### 5.5 新项目/重装怎么初始化 vault

```bash
# 1. 把 docs/vault-seed/ 下 4 个模板推到裸仓库的工作副本
scp docs/vault-seed/{schema-template.md,index.md,log.md} <ecs>:/opt/vault/
#    （schema-template.md 重命名为 SCHEMA.md）
# 2. 按需把 sample-entity.md 当参考（不强制）
# 3. git init bare + ECS bootstrap，见 scripts/deploy/ecs_bootstrap_vault.sh
```

## 6. 红绿灯速查

| 场景 | 归属 | 操作 |
|------|------|------|
| 每天发 5 篇文章攒素材 | 🟢 机器 | 飞书粘贴即可 |
| `/查` 出来的答案不对 | 🟡 人机 | 手动修 `Wiki/queries/<...>.md` + push |
| 两篇 Wiki 页结论冲突 | 🟡 人机 | 任一页加 `contradictions` 字段，lint 报，人来裁 |
| 要不要新建 entity 页 | 🔴 人 | 参考 SCHEMA.md §Page Thresholds（2+ 来源建页） |
