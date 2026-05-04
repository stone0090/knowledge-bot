# 架构设计

## 核心决策

| 维度 | 选型 | 理由 |
|------|------|------|
| 存储 | ECS 本地 Vault（md + git） | 数据主权，零 SaaS 锁定；Obsidian 直接编辑；tar 即可迁移 |
| Git 中央节点 | ECS 自建 bare 仓库 | 不经第三方托管；SSH/HTTPS 双通道；每端完整副本 |
| AI | 阿里云百炼（Qwen 系列） | 中文友好，费用可控 |
| IM 入口 | 飞书自建机器人 | SDK 完善，手机端即时投喂 |
| 阅读端 | Obsidian 跨端 + obsidian-git | 离线可读，git 同步 |
| 飞书角色 | 只读镜像（best-effort） | 备用阅读入口，失败不阻断 |
| 方法论 | LLM Wiki 三层 + 红绿灯原则 | Raw 只读、SCHEMA 当契约、人机分三档 |

## 系统架构

```
[用户] → 飞书发送 URL / 文本 / 文件
         ↓ webhook
[FastAPI 后端（ECS）]
  ├─ 抓取层    按域名路由（见「URL 抓取分层」）
  ├─ 编译层    按 SCHEMA.md 抽实体/概念 → Wiki 页
  ├─ LLM       阿里云百炼 · OpenAI 兼容协议
  ├─ Vault     写 md + frontmatter → git commit/push
  └─ 飞书 API  IM 收发 + 云盘 docx 镜像（best-effort）
         ↓
[ECS 存储层]
  /opt/vault/           工作副本（Raw/ + Wiki/ + SCHEMA.md）
  /opt/vault-bare.git/  裸仓库（SSH 4500 或 HTTPS 4581 clone）
         ↓                              ↓
[飞书云盘 镜像]                    [Obsidian 各端]
```

## 知识组织：LLM Wiki 三层

| 层 | 路径 | 角色 |
|----|------|------|
| Raw | `Raw/{articles,notes,files,videos}/` | 原始来源，LLM 只读不改 |
| Wiki | `Wiki/{entities,concepts,comparisons,queries}/` + `index.md` + `log.md` | LLM 编译产物，自动维护 |
| SCHEMA | `SCHEMA.md` | 人机契约：页面命名、模板、标签、处理流程 |

- **检索**：ripgrep 扫 `Wiki/**/*.md` frontmatter + 正文，毫秒级。元数据随 md 走，无外部数据库。
- **飞书镜像**：仅 Wiki 编译产物转 docx 推云盘，best-effort，失败仅告警。

### 红绿灯原则

| 等级 | 策略 | 示例 |
|------|------|------|
| 🟢 绿灯 | 全托管 LLM | 摘要、索引、链接补全、孤儿页检查 |
| 🟡 黄灯 | 人机共审 | 矛盾裁决、概念合并、过时作废 |
| 🔴 红灯 | 绝不外包 | 核心事实写入、价值判断 |

## URL 抓取分层

| 分层 | 工具 | 覆盖 | 状态 |
|------|------|------|------|
| 通用网页 | Jina AI Reader | 90% 网页、GitHub、博客 | ✅ |
| 微信公众号 | 内置 httpx + BeautifulSoup | 永久链 `/s/*` | ✅ |
| 视频字幕 | yt-dlp | YouTube / B站 / 1800+ 站 | ✅ |
| Twitter/X | Jina Reader + 降级提示 | best-effort | ✅ |
| 结构化文件 | markitdown | PDF / PPT / Excel / Word | 二期 |
| 登录态平台 | Cookie / Playwright | 小红书 / LinkedIn | 按需 |

失败统一抛 `FetchError`，飞书卡片提示"请复制正文发送"。域名路由：`url_reader.py` 按正则自动分发。

## 工作流

### 投喂（Ingest）

1. 飞书发送 URL / 文本 → 抓取层拿纯文本
2. 原文写入 `Raw/{articles|notes|videos}/`（LLM 永不修改）
3. LLM 按 SCHEMA 编译 → `Wiki/{entities,concepts}/*.md` + 更新 index/log
4. `git commit && git push` → bare 仓库
5. 飞书镜像 Wiki → docx（best-effort）
6. 飞书卡片回复

### 检索（Query）

1. `/查 关键词` → ripgrep 扫 `Wiki/**/*.md` → Top-K 候选
2. LLM 生成带引用回答
3. 高质量答案可回填 `Wiki/queries/`
4. 飞书蓝色卡片回复
