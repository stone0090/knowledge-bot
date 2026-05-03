# Knowledge Bot

基于飞书机器人 + 阿里云百炼 的个人知识库后端服务。

## 功能

本项目分两期交付：

**一期（当前）——轻量上线**

- 在飞书中 @机器人或私聊发送 **URL / 纯文本**，自动：
  1. 解析为纯文本（URL 走 Jina AI Reader）；
  2. 调百炼按 **SCHEMA** 编译为结构化页面（实体页 / 概念页）；
  3. 写入 **ECS 本地 Vault** `/opt/vault/Raw/`（原文，LLM 只读不改）和 `/opt/vault/Wiki/`（编译产物）；
  4. 元数据以 **YAML frontmatter** 写入每个 md 文件头部（title/domain/tags/summary/source_url/created_at）；
  5. `git commit && git push` 到 ECS 自建 bare 仓库（`/opt/vault-bare.git`）；
  6. **best-effort** 把本次新增/更新的 Wiki md 镜像为 docx 推到飞书云盘 `知识库-镜像/`（失败仅告警）；
  7. 机器人回复卡片，附带标题 / 摘要 / vault 路径 / 飞书镜像链接。
- 发送 `/查 关键词` 或自然语言问题 → `ripgrep` 本地扫 `/opt/vault/Wiki/**/*.md`（**不走 Raw**）召回候选页 → 百炼生成带引用的回答；高质量问答回填到 `/opt/vault/Wiki/queries/`。
- 阅读端：桌面 Obsidian（+ obsidian-git）/ iOS Working Copy + Obsidian / Android MGit + Obsidian，均通过 SSH clone ECS bare 仓库，离线可读。

**二期——文件与双链**

- PDF / PPT / Excel / Word / 图片 OCR（`markitdown`）
- Wiki 细分子目录：`entities/` `concepts/` `comparisons/` `queries/`；双向链接 `[[wikilink]]`
- 多模态智能路由（含图/代码场景选模）

**三期——多源抓取与自动体检**

- 视频字幕（`yt-dlp`：YouTube / B站）、推特（`xreach`）、RSS、Reddit / Exa 语义搜索
- Wiki lint：每周自动扫矛盾 / 过时 / 孤儿页 / 索引缺口，飞书周报卡片推送

详细架构与参考文献见 [docs/技术方案.md](docs/技术方案.md)。

## 目录结构

```
knowledge-bot/
├── app/
│   ├── main.py              FastAPI 入口，/feishu/event 回调
│   ├── config.py            配置加载
│   ├── feishu/              飞书 SDK 封装（IM + 云盘只读镜像；M15 后不再包含 bitable）
│   ├── vault/               Vault 写入与 git 同步（M13 新增：writer / git_sync / frontmatter）
│   ├── parsers/             URL / 文本 / 文件解析器
│   ├── llm/                 百炼 LLM 封装
│   ├── handlers/            投喂 / 检索 业务流程
│   └── utils/
├── docs/
│   ├── 技术方案.md          架构 / 分期 / 知识组织 / 抓取分层 / 工作流
│   ├── feishu-setup.md       飞书应用 / 云盘镜像 / Vault 初始化 / 百炼 / 本地与 ECS
│   ├── todo.md               未完成事项单一来源（代码 / 测试 / 运维）
│   └── 外部参考/             本地归档的上游参考文章
├── requirements.txt          一期依赖
├── requirements-phase2.txt   二期文件解析栈（markitdown）
├── .env.example
└── README.md

# 部署时在 ECS 上额外创建（**不在 repo 内**，作为知识资产的真相源）：
/opt/vault/                  工作副本：Raw/ + Wiki/ + SCHEMA.md
/opt/vault-bare.git/         中央 bare 仓库，所有端 SSH clone 到这里
```

## 快速开始

1. 参照 [docs/feishu-setup.md](docs/feishu-setup.md) 完成飞书自建应用（仅 IM + 云盘镜像）、云盘 `知识库-镜像/` 目录、ECS Vault 与 bare 仓库初始化。
2. 复制 `.env.example` 为 `.env`，填入 AppID / AppSecret / DashScope API Key / 镜像目录 Token / Vault 路径。
3. 安装一期依赖（不含文件解析栈）：
   ```bash
   pip install -r requirements.txt
   ```
   如需人工启用二期文件解析（PDF/PPT/Excel），额外运行：
   ```bash
   pip install -r requirements-phase2.txt
   ```
4. 启动服务：
   ```bash
   uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
   ```
5. 本地开发不需内网穿透，可直接 `POST http://localhost:8000/feishu/event` 手造事件负载自测；于 ECS 上线后再配域名 + Nginx + HTTPS，细节见 [docs/feishu-setup.md](docs/feishu-setup.md) §5。

## 里程碑

**一期**
- [x] M1 环境准备（见 docs/feishu-setup.md）
- [x] M2 基础骨架 + 回显
- [x] M3 URL / 文本投喂
- [x] M5 检索 `/查`
- [ ] M7 本地全链路联调 → ECS 部署
- [ ] **M13 Vault 初始化 + Git 中央仓库**（存储层迁移，编译器 MVP 前置）
- [ ] **M14 飞书角色降级为只读镜像**（仅镜像 Wiki 编译产物 docx）
- [ ] **M15 索引表下线**（检索换为本地 ripgrep）
- [ ] **M16 移动端 Obsidian 接入验证**（桌面 + iOS + Android）
- [ ] M9 `SCHEMA.md` 编译器 MVP（抽出实体/概念 → 写入 `/opt/vault/Wiki/` 与 index/log）
- [ ] M10 `/查` 结果回填 `/opt/vault/Wiki/queries/`

**二期**
- [ ] M4 PDF / PPT / Excel / 图片解析（markitdown）
- [ ] M6 Wiki 子目录拆分（entities/concepts/comparisons/queries）+ 双向链接
- [ ] M8 多模态智能路由接入（按场景选模）

**三期**
- [ ] M11 视频字幕抓取（yt-dlp）+ 推特（xreach）+ RSS
- [ ] M12 Wiki lint（矛盾/过时/孤儿/缺索引）+ 周报

## 技术栈

| 模块 | 选型 | 分期 |
|------|------|------|
| Web 框架 | FastAPI | 一期 |
| 飞书 SDK | `lark-oapi`（仅 IM + 云盘 docx 镜像） | 一期 |
| 百炼调用 | OpenAI 兼容协议（`coding.dashscope.aliyuncs.com/v1`）+ httpx | 一期 |
| 知识组织 | **LLM Wiki 三层**（Raw / Wiki / SCHEMA）+ 红绿灯原则 | 一期 |
| **存储层** | **ECS 本地 Vault（纯 md）+ 自建 bare 仓库**（`/opt/vault-bare.git`） | **一期·M13** |
| 元数据 | md 头部 YAML frontmatter（无外部数据库） | 一期 |
| 检索 | `ripgrep` 本地扫 Wiki；二期可改 SQLite FTS5 | 一期·M15 |
| 飞书镜像 | `drive + docx` 写入·仅镜像 Wiki·best-effort | 一期·M14 |
| 阅读端 | Obsidian（桌面 + obsidian-git / iOS Working Copy / Android MGit） | 一期·M16 |
| URL 抓取 · L1 | Jina AI Reader（90% 通用网页） | 一期 |
| URL 抓取 · L2 | `markitdown`（PDF/PPT/Excel/Word/图片） | **二期** |
| URL 抓取 · L3–L5 | `yt-dlp` / `xreach` / Playwright | **三期** |
| 微信公众号 | 反爬强度无解，项目不支持抓取 | — |
