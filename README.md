# Knowledge Bot

基于飞书机器人 + 阿里云百炼的个人知识库后端服务。

## 功能

**一期（已上线）** — 飞书发 URL / 纯文本 → 按域名路由抓取（微信 / 视频 / Twitter / 通用）→ 百炼编译为 Wiki 页 → 写入 ECS Vault（md + git）→ 飞书卡片回复。`/查` 检索 → ripgrep 扫 Wiki → 带引用回答。阅读端：Obsidian 跨端（SSH 或 HTTPS）clone。

**二期** — PDF / PPT / Excel / 图片 OCR（markitdown）+ Wiki 双向链接 + 多模态智能路由

**三期** — Wiki lint + 飞书周报 + RSS / Reddit / Exa 语义搜索

## 目录结构

```
knowledge-bot/
├── app/
│   ├── main.py              FastAPI 入口
│   ├── config.py            多环境配置（APP_ENV 切换 local/ecs）
│   ├── feishu/              飞书 SDK（IM + 云盘镜像）
│   ├── vault/               Vault 写入 + git 同步 + ripgrep 检索
│   ├── parsers/             URL 多源抓取 + 文本解析
│   ├── llm/                 百炼 LLM
│   └── handlers/            投喂 / 检索业务流程
├── envs/                    多环境配置 + 密钥（.env.secrets.example 为模板）
├── scripts/
│   ├── deploy/              一键部署 / SSH 免密 / Vault 初始化
│   └── tests/               端到端验证脚本
├── docs/                    架构 / 搭建手册 / 待办
├── requirements.txt         一期依赖
└── requirements-phase2.txt  二期依赖（markitdown）

# ECS（不在 repo 内）
/opt/vault/                  工作副本：Raw/ + Wiki/ + SCHEMA.md + index.md + log.md
/opt/vault-bare.git/         中央 bare 仓库
```

## 快速开始

1. 参照 [docs/setup.md](docs/setup.md) 完成飞书、百炼、ECS Vault 配置
2. `cp envs/.env.secrets.example envs/.env.secrets` 并填入密钥
3. `pip install -r requirements.txt && uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload`
4. ECS 部署：`bash scripts/deploy/deploy_to_ecs.sh full`

## 技术栈

| 模块 | 选型 |
|------|------|
| Web 框架 | FastAPI |
| 飞书 SDK | lark-oapi（IM + 云盘 docx 镜像） |
| LLM | 阿里云百炼 · OpenAI 兼容协议 |
| 知识组织 | LLM Wiki 三层（Raw / Wiki / SCHEMA）+ 红绿灯原则 |
| 存储 | ECS 本地 Vault（md + git bare 仓库） |
| 检索 | ripgrep 本地扫 Wiki frontmatter + 正文 |
| URL 抓取 | Jina Reader（通用）/ 内置 httpx+BS4（微信）/ yt-dlp（视频）/ Twitter 降级 |
| 阅读端 | Obsidian + obsidian-git（桌面 SSH/HTTPS / Android HTTPS / iOS Working Copy SSH），详见 [docs/obsidian-git.md](docs/obsidian-git.md) |

架构设计见 [docs/architecture.md](docs/architecture.md)，知识整理方法论见 [docs/llm-wiki-method.md](docs/llm-wiki-method.md)，环境搭建见 [docs/setup.md](docs/setup.md)，Obsidian 同步见 [docs/obsidian-git.md](docs/obsidian-git.md)，待办见 [docs/todo.md](docs/todo.md)。
