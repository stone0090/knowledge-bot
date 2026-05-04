# 环境搭建

> 跑通前需手动完成以下配置，预计 30 分钟。架构详见 [architecture.md](architecture.md)。

## 1. 飞书自建应用

1. [飞书开放平台](https://open.feishu.cn/app) → 创建企业自建应用，记录 **App ID / App Secret**
2. 权限管理，勾选：
   - `im:message`、`im:message:send_as_bot`（消息收发）
   - `docx:document`、`drive:drive`、`drive:file`（云盘镜像）
   - `im:resource`（二期再勾，用于文件下载）
3. 事件订阅 → HTTP 回调 → 添加 `im.message.receive_v1`
4. 开启机器人能力 → 发布审核

## 2. 飞书云盘镜像目录

1. 云空间新建文件夹 `知识库-镜像/`
2. 获取 Folder Token：浏览器打开该文件夹，URL 中 `folder/` 后的字符串即为 Token
3. 填入 `envs/local.env` 或 `envs/ecs.env`：`FEISHU_MIRROR_FOLDER_TOKEN=xxx`
4. 给自建应用开通该文件夹的**编辑权限**

## 3. ECS Vault 初始化

### SSH 免密

```bash
bash scripts/deploy/setup_ssh_keyless.sh    # 配好别名 kb，SSH 端口 4500
```

### 一键初始化

```bash
cat scripts/deploy/ecs_bootstrap_vault.sh | ssh kb bash
```

脚本完成：装 git / ripgrep → 建 bare 仓库 → clone 工作副本 → 写入骨架 → 首次 commit。

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
| iOS | Working Copy + Obsidian | SSH | host `121.196.26.127` port `4500` → clone `/opt/vault-bare.git` |

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

不需内网穿透，直接 POST `http://localhost:8000/feishu/event` 手造事件自测。

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
| 9443 | HTTPS | 飞书 webhook 主入口（`https://bot.shisb.com:9443/feishu/event`） |
| 4580 | HTTP | Git over HTTP（Obsidian 备用，证书异常时使用） |
| 4581 | HTTPS | Git over HTTPS（Obsidian 推荐，见 [obsidian-git.md](obsidian-git.md)） |

其他关键配置：
- HTTPS 证书：acme.sh + ZeroSSL，`bot.shisb.com` 同时用于 9443（飞书）与 4581（Git）
- 代理：mihomo 访问海外服务
- systemd `Environment=APP_ENV=ecs`

## 8. 冒烟测试

1. 飞书私聊发纯文本 → 绿色卡片「已收录」
2. 发 URL → 绿色卡片
3. `/查 关键词` → 蓝色卡片
