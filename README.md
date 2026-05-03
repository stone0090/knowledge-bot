# Knowledge Bot

基于飞书机器人 + 阿里云百炼 的个人知识库后端服务。

## 功能

本项目分三期交付：

**一期（已上线）——轻量闭环**

- 在飞书中 @机器人或私聊发送 **URL / 纯文本**，自动：
  1. 按域名路由抓取正文（微信公众号 / YouTube / B站 / Twitter / 通用网页）；
  2. 调百炼按 **SCHEMA** 编译为结构化页面（实体页 / 概念页）；
  3. 写入 **ECS 本地 Vault** `/opt/vault/Raw/` + `/opt/vault/Wiki/`；
  4. `git commit && git push` 到 ECS 自建 bare 仓库；
  5. **best-effort** 镜像 Wiki 编译产物为 docx 推到飞书云盘（失败仅告警）；
  6. 机器人回复卡片（标题 / 摘要 / vault 路径 / 镜像链接）。
- 发送 `/查 关键词` → `ripgrep` 扫 Wiki → 百炼生成带引用回答。
- 阅读端：Obsidian（桌面 / iOS / Android），SSH clone ECS bare 仓库，离线可读。

**二期——文件与双链**

- PDF / PPT / Excel / Word / 图片 OCR（`markitdown`）
- Wiki 子目录拆分 + 双向链接 `[[wikilink]]`
- 多模态智能路由（按场景选模）

**三期——自动体检**

- Wiki lint：定期扫矛盾 / 过时 / 孤儿页 / 索引缺口，飞书周报推送
- RSS / Reddit / Exa 语义搜索等更多抓取源

详细架构与参考文献见 [docs/技术方案.md](docs/技术方案.md)。

## 目录结构

```
knowledge-bot/
├── app/
│   ├── main.py              FastAPI 入口，/feishu/event 回调
│   ├── config.py            多环境配置加载（APP_ENV 切换 local/ecs）
│   ├── feishu/              飞书 SDK 封装（IM + 云盘只读镜像）
│   ├── vault/               Vault 写入（frontmatter/writer）+ git 同步 + ripgrep 检索
│   ├── parsers/             URL 多源抓取（微信/视频/Twitter/通用）+ 文本解析
│   ├── llm/                 百炼 LLM 封装
│   └── handlers/            投喂 / 检索 业务流程
├── envs/
│   ├── local.env            本机开发配置（可提交）
│   ├── ecs.env              ECS 生产配置（可提交）
│   ├── .env.secrets         密钥文件（不提交）
│   └── .env.secrets.example 密钥模板
├── scripts/
│   ├── deploy/              一键 ECS 部署 / SSH 免密 / Vault 初始化
│   └── tests/               端到端验证脚本（M13/M14/M15/URL）
├── docs/                    技术方案 / 飞书配置手册 / 待办 / 外部参考
├── requirements.txt         一期依赖
├── requirements-phase2.txt  二期文件解析栈（markitdown）
└── README.md

# ECS 上（不在 repo 内）：
/opt/vault/                  工作副本：Raw/ + Wiki/ + SCHEMA.md
/opt/vault-bare.git/         中央 bare 仓库
```

## 快速开始

1. 参照 [docs/feishu-setup.md](docs/feishu-setup.md) 完成飞书自建应用、云盘镜像目录、ECS Vault 初始化。
2. 复制 `envs/.env.secrets.example` → `envs/.env.secrets`，填入飞书 AppID/Secret、百炼 API Key。
3. 安装依赖并启动：
   ```bash
   pip install -r requirements.txt
   uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
   ```
4. 本地开发不需内网穿透，可直接 POST 手造事件自测；ECS 部署见 `bash scripts/deploy/deploy_to_ecs.sh full`。

## 里程碑

**一期**
- [x] M1 环境准备
- [x] M2 基础骨架 + 回显
- [x] M3 URL / 文本投喂
- [x] M5 检索 `/查`
- [x] M13 Vault 初始化 + Git 中央仓库
- [x] M14 飞书角色降级为只读镜像
- [x] M15 索引表下线（ripgrep）
- [x] M7 ECS 部署（HTTPS + 飞书回调 + 代理）
- [x] M11（部分）URL 多源抓取（微信/视频/Twitter）
- [ ] M16 移动端 Obsidian 接入验证
- [ ] M9 `SCHEMA.md` 编译器 MVP
- [ ] M10 `/查` 结果回填 Wiki

**二期**
- [ ] M4 PDF / PPT / Excel / 图片解析（markitdown）
- [ ] M6 Wiki 子目录拆分 + 双向链接
- [ ] M8 多模态智能路由（按场景选模）

**三期**
- [ ] M11（剩余）RSS / Reddit / Exa 语义搜索
- [ ] M12 Wiki lint + 周报

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
| URL 抓取 · 通用 | Jina AI Reader（90% 通用网页） | 一期 |
| URL 抓取 · 微信 | 内置 httpx + BeautifulSoup（模拟 UA 绕反爬） | 一期 |
| URL 抓取 · 视频 | `yt-dlp`（YouTube / B站字幕提取） | 一期 |
| URL 抓取 · 文件 | `markitdown`（PDF/PPT/Excel/Word/图片） | **二期** |
