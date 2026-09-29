# 环境搭建

> 跑通前需手动完成以下配置，预计 30 分钟。架构详见 [architecture.md](architecture.md)。

## 1. 飞书自建应用

1. [飞书开放平台](https://open.feishu.cn/app) → 创建企业自建应用，记录 **App ID / App Secret**
2. 权限管理，勾选：
   - `im:message`、`im:message:send_as_bot`（消息收发）
   - `im:resource`（文件下载）
3. 事件订阅 → HTTP 回调 → 添加 `im.message.receive_v1`
4. 开启机器人能力 → 发布审核

## 2. 回调与预览

机器人直接回复预览卡片，不再创建云盘或飞书知识库文档；无需镜像目录。
将飞书事件订阅的 Verification Token 写入服务器 `FEISHU_VERIFICATION_TOKEN`，用于验证回调。当前实现接收未加密事件，不支持配置 Encrypt Key 后的加密载荷。可用 `FEISHU_ALLOWED_OPEN_IDS` 限定发送者（逗号分隔）。

## 3. ECS Vault 初始化

### SSH 免密

```bash
bash scripts/deploy/setup_ssh_keyless.sh    # 配好别名 kb，SSH 端口 4500
```

### 一键初始化

```bash
cat scripts/deploy/ecs_bootstrap_vault.sh | ssh kb bash
```

脚本完成：装 git / ripgrep → 建 bare 仓库 → clone 工作副本 → 写入骨架 → 首次 commit。该旧脚本会创建历史导航；新服务不会继续维护这些导航。

| 路径 | 角色 |
|------|------|
| `/opt/vault-bare.git` | 中央裸仓库（真相源） |
| `/opt/vault` | 服务端工作副本 |
| `/usr/local/bin/rg` | ripgrep 检索 |

### 多端接入

| 端 | 工具 | 推荐协议 | 接入方式 |
|----|------|---------|---------|
| 桌面（Linux / macOS / Windows）| Obsidian + obsidian-git | SSH 或 HTTPS | SSH：`git clone kb:/opt/vault-bare.git ~/vault`；HTTPS 详见 [obsidian-git.md](obsidian-git.md) |
| Android | Obsidian + obsidian-git | HTTPS | 详见 [obsidian-git.md](obsidian-git.md) |
| iOS | Working Copy + Obsidian | SSH | host `203.0.113.10` port `4500` → clone `/opt/vault-bare.git` |

## 4. 百炼 API

1. [百炼控制台](https://bailian.console.aliyun.com/) 生成 API Key
2. 填入 `envs/.env.secrets`：`DASHSCOPE_API_KEY=sk-xxxx`
3. 模型配置（当前仅兜底两个变量生效，M8 落地后支持按场景路由）：
   ```
   DASHSCOPE_MODEL_COMPILE=qwen3.5-plus
   DASHSCOPE_MODEL_QUERY=qwen3.5-plus
   ```

## 5. 环境配置

| 文件 | 用途 | 提交 Git |
|------|------|--------|
| `envs/local.env` | 本机开发 | ✅ |
| `envs/ecs.env` | ECS 生产 | ✅ |
| `envs/.env.secrets` | 密钥 | ❌ |

加载优先级：`envs/{APP_ENV}.env` → `envs/.env.secrets` → `.env`

## 6. 本地联调

```bash
pip install -r requirements.txt
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

离线回归使用 `python -m unittest scripts.tests.test_simplified -v`，不会发送真实消息。不要向生产回调投递伪造的消息 ID。

## 7. ECS 部署

```bash
bash scripts/deploy/deploy_to_ecs.sh full    # 全量
bash scripts/deploy/deploy_to_ecs.sh update  # 仅更新代码
```

端口清单（均需在阿里云安全组放行）：

| 端口 | 协议 | 用途 |
|------|------|------|
| 4500 | SSH | 服务器管理 + Git over SSH（`kb:/opt/vault-bare.git`） |
| 9000 | HTTP | 飞书 webhook fallback |
| 9443 | HTTPS | 飞书 webhook 主入口（`https://bot.example.com:9443/feishu/event`） |
| 4580 | HTTP | Git over HTTP（Obsidian 备用，证书异常时使用） |
| 4581 | HTTPS | Git over HTTPS（Obsidian 推荐，见 [obsidian-git.md](obsidian-git.md)） |

其他关键配置：
- HTTPS 证书：acme.sh + ZeroSSL，`bot.example.com` 同时用于 9443（飞书）与 4581（Git）
- 代理：mihomo 访问海外服务
- systemd `Environment=APP_ENV=ecs`

## 8. 冒烟测试

1. 飞书私聊发纯文本 → 预览卡片，显示 Git 同步状态
2. 发 URL → 绿色卡片
3. `/查 关键词` → 蓝色卡片

## 9. 升级与历史笔记

`update` 只更新代码，保留服务器 `envs/` 和 `.env`；不要用本机密钥覆盖服务器正在使用的配置。服务必须只运行一个 worker。

运行状态保存在 `STATE_PATH`（默认 `/opt/knowledge-bot-state`），必须位于 Vault 外。包含任务队列、解析缓存和收到的附件原文件，需要与 Vault 一起纳入服务器备份，不进入 Obsidian/Git。

迁移前停止服务、同步 Git 并保留备份。先预览，再执行：

```bash
python scripts/migrate_collection.py --vault /opt/vault --backup /opt/backups/vault-before-migration
# 确认预览后，在上述命令末尾增加 --apply
```

迁移保留正文，将旧类型目录摊平到 Wiki，将历史查询和导航移至 `_archive`，并修正可解析的本地链接。备份包含迁移前文件及映射清单。迁移后提交并推送，再启动服务。
