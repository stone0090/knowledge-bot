# 飞书 / 百炼 / Vault 环境准备手册

> 代码已就绪，跑通之前需手动完成下列配置。预计耗时 30 分钟。
>
> 文档范围：飞书应用（仅 IM + 云盘镜像）+ ECS Vault 与 Git 中央仓库 + 百炼模型 + 本地联调 + ECS 部署。未完成事项见 [todo.md](todo.md)。
>
> **架构提醒**：知识资产的真相源是 ECS 的 `/opt/vault/`（md 文件 + git），飞书仅充当「IM 入口」+「云盘只读镜像」。详见 [技术方案.md §一](技术方案.md)。

## 1. 飞书自建应用

1. 打开 [飞书开放平台](https://open.feishu.cn/app) → 「创建企业自建应用」。
2. 记录下 **App ID** 和 **App Secret**，填入 `envs/.env.secrets`：
   ```
   FEISHU_APP_ID=cli_xxxx
   FEISHU_APP_SECRET=xxxx
   ```
3. 左侧 **权限管理**，勾选以下权限（全部加上再发布，否则会频繁回退）：

   机器人与消息
   - `im:message`
   - `im:message:send_as_bot`
   - `im:resource`（下载文件/图片，**二期再勾**）

   云文档（仅用于云盘镜像写 docx）
   - `docx:document`
   - `drive:drive`
   - `drive:file`

   > “bitable:app”权限已**不再需要**（索引表随 M15 下线，见 [todo.md](todo.md)）。

4. 左侧 **事件与回调 → 事件订阅**：
   - 模式选 **「HTTP 回调」**（本项目走 HTTP，不用长连接）。
   - 请求地址填 `https://<你的域名>/feishu/event`；**本地联调不需要内网穿透**（走接口自测，见 §5.1），只有 ECS 上线后才填真实回调。
   - 添加事件：`im.message.receive_v1`。
5. 左侧 **应用能力 → 机器人**：开启机器人能力，设置头像与名称。
6. **版本管理与发布** → 创建版本 → 提交审核（个人开发者自审通过即可）。

## 2. 飞书云盘：仅一个「知识库-镜像」目录（只读阅读端）

> 从 M13 起，飞书云盘退化为只读镜像，仅镜像 Wiki 编译产物（Raw / SCHEMA 不镜像）；完整架构见 [技术方案.md §二](技术方案.md)。**不要在飞书上编辑**——修改只在本地 Obsidian / VS Code 进行，否则下次 ingest 镜像会覆盖你的修改。

1. 在飞书「云空间」里新建一个文件夹：`知识库-镜像/`
2. 获取**目录 Token**（新版飞书的右键菜单已无「查看更多 → 复制目录 Token」入口，改用下述任一方式）：
   - **方式 A（推荐）从 URL 截取**：在客户端点文件夹右上角「…」→「在浏览器中打开」，或直接在网页版打开该文件夹。地址栏形如 `https://xxx.feishu.cn/drive/folder/XXXXXXXX`，`folder/` 后的那一段即为 Folder Token。
   - **方式 B 从分享链接截取**：右键目录 →「分享」→「复制链接」，粘贴后同样取 `folder/` 后的那段字符串。
   > 注：新版 Token 不一定以 `fldcn` 开头，可能是 `fldb` / `fodcn` 或纯字母数字串，原样复制即可。
3. 填入 `envs/local.env`（本机）或 `envs/ecs.env`（生产）：
   ```
   FEISHU_MIRROR_FOLDER_TOKEN=xxxxxxxxxxxxxxxx   # 指向 知识库-镜像/ 根目录
   ```
   > **已废弃**：`FEISHU_RAW_FOLDER_TOKEN` 与 `FEISHU_WIKI_INBOX_FOLDER_TOKEN`（随 M13/M14 退休，见 [todo.md](todo.md)）。
4. 在飞书「文档分享设置」中，给你的自建应用开通**编辑权限**（否则镜像写不进）。

## 2b. ECS Vault 与 Git 中央仓库（**真相源**）

所有 md 知识资产落到 `/opt/vault/`，不经任何第三方 SaaS；中央节点是同一台 ECS 上的 bare 仓库。

### 2b.1 ECS 一次性初始化（一键脚本）

仓库提供了 [`scripts/deploy/ecs_bootstrap_vault.sh`](../scripts/deploy/ecs_bootstrap_vault.sh)，在本机一条命令搞定（覆盖：装 git / ripgrep → 建 bare → clone 工作副本 → 写入骨架 → 首次 commit+push）：

```bash
# 前置：先配好 SSH 免密登录 + 别名 kb（见 2b.2）
cat scripts/deploy/ecs_bootstrap_vault.sh | ssh kb bash
```

脚本内已兼容 CentOS 7.6 的两个历史包袱：

- **git 1.8.3.1 不识别 `git init --bare -b <branch>`**：改为先 `git init --bare` 再 `git symbolic-ref HEAD refs/heads/master`
- **ripgrep 无官方 yum 包**：EPEL / Copr 均失败，改为拉 [GitHub 静态 musl 二进制](https://github.com/BurntSushi/ripgrep/releases) 到 `/usr/local/bin/rg`

最终布局：

| 路径 | 角色 |
|---|---|
| `/opt/vault-bare.git` | 中央裸仓库（真相源），默认分支 `master` |
| `/opt/vault` | 服务端工作副本（FastAPI 写这里，git push 到 bare） |
| `/usr/local/bin/rg` | ripgrep（`query.py` 检索走它） |

### 2b.2 本机 / 手机接入

**前置一次性**：本机用 [`scripts/deploy/setup_ssh_keyless.sh`](../scripts/deploy/setup_ssh_keyless.sh) 配好 SSH 免密 + 别名 `kb`（SSH 端口为 4500，非默认 22）：

```bash
bash scripts/deploy/setup_ssh_keyless.sh    # 输一次密码，以后 ssh kb 直连
```

配好之后的三端接入方式：

| 端 | 工具 | 用法 |
|----|------|------|
| 本机桌面 | VS Code / Obsidian + **obsidian-git** 插件 | `git clone kb:/opt/vault-bare.git D:/vault`（Windows）或 `~/vault`（macOS/Linux） → Obsidian 打开此目录，插件自动 pull/push |
| 其他电脑 | 同上 | 先把本机 `~/.ssh/id_ed25519.pub` 内容追加到 ECS 的 `~/.ssh/authorized_keys`，再 `git clone ssh://root@121.196.26.127:4500/opt/vault-bare.git ~/vault` |
| iOS | **Working Copy** + Obsidian 移动端 | Working Copy 添加主机：host `121.196.26.127`、port `4500`、user `root`、auth 用 SSH Key（导入 ed25519 私钥）→ clone `/opt/vault-bare.git` → Obsidian 指向同一目录 |
| Android | **MGit** + Obsidian 移动端 | MGit 新建 SSH 连接 `ssh://root@121.196.26.127:4500`，导入私钥 → clone `/opt/vault-bare.git` → Obsidian 打开 |

### 2b.3 环境配置

项目采用多文件配置，通过 `APP_ENV` 环境变量切换：

| 文件 | 用途 | 提交 Git |
|------|------|--------|
| `envs/local.env` | 本机开发配置（`VAULT_PATH=D:/vault`） | ✅ |
| `envs/ecs.env` | ECS 生产配置（`VAULT_PATH=/opt/vault`，含代理） | ✅ |
| `envs/.env.secrets` | 密钥（AppID/Secret/API Key） | ❌ |
| `.env` | 本地临时覆盖（可选） | ❌ |

加载优先级（后者覆盖前者）：`envs/{APP_ENV}.env` → `envs/.env.secrets` → `.env`

### 2b.4 离线 / 导出 / 迁移

- **离线阅读**：每个设备 clone 后即具备完整副本，断网照读照写
- **手动导出**：`tar czf vault-$(date +%Y%m%d).tar.gz /opt/vault-bare.git` 即完整历史可携
- **迁移**：bare 仓库拷到新机器 → 其它端 `git remote set-url origin <新路径>` 即可，无需导出导入

## 4. 阿里云百炼

1. 到 [百炼控制台](https://bailian.console.aliyun.com/) 生成 API Key。
2. 填入 `envs/.env.secrets`：
   ```
   DASHSCOPE_API_KEY=sk-xxxx
   ```
3. **模型选型**（按场景路由，不再仅分 COMPILE/QUERY 两档）。

   > ⚠️ **当前进度**：[ingest.py](../app/handlers/ingest.py) / [query.py](../app/handlers/query.py) 目前只读 `DASHSCOPE_MODEL_COMPILE` 与 `DASHSCOPE_MODEL_QUERY` 两个 **兜底变量**；下文的 `*_TEXT / *_LONG / *_VISION / *_CODE / *_DEEP / *_FAST` 属预留的路由钩子，需 M8 落地后生效（见 [todo.md M8](todo.md)）。先跳到步骤 4 写 `.env` 即可跑通一期。

   **兜底 fallback（一期必填，场景判断不命中时走这两个）**：

   | 变量 | 默认值 | 说明 |
   |------|-------|------|
   | `DASHSCOPE_MODEL_COMPILE` | `qwen3.5-plus` | 投喂兜底 |
   | `DASHSCOPE_MODEL_QUERY` | `qwen3.5-plus` | 检索兜底 |

   **投喂侧 (Compile) · 按内容形态选型**（M8 预留）：

   | 场景 | 触发条件 | 推荐模型 | 环境变量 |
   |------|---------|---------|---------|
   | 短文 / URL 摘要 | `source_type ∈ {text, url}` 且字数 < 5k | `qwen3.5-plus` / `glm-4.7` | `DASHSCOPE_MODEL_COMPILE_TEXT` |
   | 长文档 | 字数 ≥ 5k | `kimi-k2.5` | `DASHSCOPE_MODEL_COMPILE_LONG` |
   | 含图内容 | PDF/PPT/图片 或 URL 含大量截图 | `qwen3.6-plus` / `kimi-k2.5` | `DASHSCOPE_MODEL_COMPILE_VISION` |
   | 代码/技术文档 | 后缀 `.py/.ts/.java/.md` 含大量代码块 | `qwen3-coder-plus` | `DASHSCOPE_MODEL_COMPILE_CODE` |
   | 深度归纳 | 用户显式深挖（如 `/深投`） | `qwen3-max-2026-01-23` | `DASHSCOPE_MODEL_COMPILE_DEEP` |

   **检索侧 (Query) · 按问题性质选型**（M8 预留）：

   | 场景 | 触发条件 | 推荐模型 | 环境变量 |
   |------|---------|---------|---------|
   | 快问快答 | 上下文 < 10k、问题短 | `qwen3.5-plus` / `glm-4.7` | `DASHSCOPE_MODEL_QUERY_FAST` |
   | 深度推理 | 含「为什么/对比/设计」等关键词 | `qwen3-max-2026-01-23` / `qwen3.6-plus` | `DASHSCOPE_MODEL_QUERY_DEEP` |
   | 长上下文 | 命中跨多篇 Wiki串联，上下文 ≥ 10k | `kimi-k2.5` | `DASHSCOPE_MODEL_QUERY_LONG` |
   | 含图问答 | 问题涉及截图 / 图表 | `qwen3.6-plus` / `kimi-k2.5` | `DASHSCOPE_MODEL_QUERY_VISION` |

   **模型能力速查**：

   | 模型 | 文本 | 深度思考 | 视觉 | 长上下文 | 定位 |
   |------|:-:|:-:|:-:|:-:|------|
   | `qwen3-max-2026-01-23` | ✅ | ✅ | ❌ | 中 | 推理最强，深度场景 |
   | `qwen3.6-plus` | ✅ | ✅ | ✅ | 中 | 全能均衡 |
   | `qwen3.5-plus` | ✅ | ✅ | ✅ | 中 | 性价比主力 |
   | `kimi-k2.5` | ✅ | ✅ | ✅ | **长** | 长文档 / 含图 PDF |
   | `glm-5` / `glm-4.7` | ✅ | ✅ | ❌ | 中 | 低成本备选 |
   | `MiniMax-M2.5` | ✅ | ✅ | ❌ | 中 | 低成本备选 |
   | `qwen3-coder-plus` / `qwen3-coder-next` | ✅ | ❌ | ❌ | 中 | 代码专项 |

4. 推荐 `.env` 配置（第一段当前生效，后两段预留 M8 路由钩子）：
   ```
   # ——当前生效的 fallback
   DASHSCOPE_MODEL_COMPILE=qwen3.5-plus
   DASHSCOPE_MODEL_QUERY=qwen3.5-plus

   # ——预留：投喂侧场景路由
   DASHSCOPE_MODEL_COMPILE_TEXT=qwen3.5-plus
   DASHSCOPE_MODEL_COMPILE_LONG=kimi-k2.5
   DASHSCOPE_MODEL_COMPILE_VISION=qwen3.6-plus
   DASHSCOPE_MODEL_COMPILE_CODE=qwen3-coder-plus
   DASHSCOPE_MODEL_COMPILE_DEEP=qwen3-max-2026-01-23

   # ——预留：检索侧场景路由
   DASHSCOPE_MODEL_QUERY_FAST=qwen3.5-plus
   DASHSCOPE_MODEL_QUERY_DEEP=qwen3-max-2026-01-23
   DASHSCOPE_MODEL_QUERY_LONG=kimi-k2.5
   DASHSCOPE_MODEL_QUERY_VISION=qwen3.6-plus
   ```
   想压成本可把 `*_FAST` / `*_TEXT` 换成 `glm-4.7` 或 `MiniMax-M2.5`；视觉场景不起皮时用 `kimi-k2.5`。

> 不建议把 `qwen3-coder-*` 用于归纳——它们擅长代码生成，但结构化 JSON 指令遵循不如通用大模型稳定。

## 5. 本地联调 & ECS 部署

### 5.1 本地联调（不需内网穿透）

```bash
pip install -r requirements.txt
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

本地阶段不接飞书事件回调，用以下两种方式验证：

- **接口自测**：直接调用 `POST http://localhost:8000/feishu/event`，手造一份 `im.message.receive_v1` 事件负载跳过飞书验证。
- **逻辑点调试**：uvicorn `--reload` 热重载下，直接以单元调用 `app.handlers.ingest.ingest()` / `app.handlers.query.query()` 验证全链路（需保证 `.env` 已填好飞书及百炼凭据）。

> 如果中途想连真实飞书那边联调，再临时拉个 `cloudflared tunnel --url http://localhost:8000` 即可，不是必选项。

### 5.2 阿里云 ECS 部署

项目提供一键部署脚本：

```bash
# 前置：配好 SSH 免密 + 别名 kb，确保 envs/.env.secrets 已填写
bash scripts/deploy/deploy_to_ecs.sh full    # 全量部署
bash scripts/deploy/deploy_to_ecs.sh update  # 仅更新代码
```

脚本自动完成：代码同步 → 密钥上传 → 依赖安装 → systemd 服务配置 → Nginx 反代（HTTP 9000 + HTTPS 9443）。

**关键配置**：

1. **ECS 选型**：1核2G 已足够；二期 markitdown 后建议 2核4G。
2. **安全组**：放行 9000（HTTP）、9443（HTTPS）、4500（SSH）。
3. **HTTPS**：acme.sh DNS-01 验证 + ZeroSSL 证书，自动续签。
4. **代理**：ECS 通过 mihomo (Clash Meta) 访问 Jina Reader / YouTube 等海外服务。
5. **飞书事件回调**：在开放平台填 `https://bot.shisb.com:9443/feishu/event`。
6. **环境切换**：systemd 设置 `Environment=APP_ENV=ecs`，自动加载 `envs/ecs.env`。

### 5.3 本地 vs ECS 差异速查

| 项 | 本地 | ECS |
|----|------|-----|
| 启动方式 | `uvicorn --reload` | `systemd` 托管 |
| 监听地址 | `0.0.0.0:8000` | `127.0.0.1:8000` + Nginx 9000/9443 |
| 飞书回调 | 不接，接口自测 | `https://bot.shisb.com:9443/feishu/event` |
| 配置 | `envs/local.env` + `envs/.env.secrets` | `envs/ecs.env` + `envs/.env.secrets`（`APP_ENV=ecs`） |
| Vault 路径 | `D:/vault`（git clone 的本地副本） | `/opt/vault` → `/opt/vault-bare.git` |
| 飞书镜像 | 可关闭（留空 token） | best-effort，失败仅告警 |
| 代理 | 无需 | mihomo `http://127.0.0.1:7890` |

## 6. 冒烟测试

**一期范围**：

1. 飞书里与机器人私聊，发一段纯文本 —— 期望收到「收到，正在整理…」→ 绿色卡片「已收录」。
2. 再发一个 URL（如知乎文章）—— 期望同样收到卡片。
3. 发 `/查 LLM` —— 期望收到蓝色「检索」卡片，内含答案。

**二期才需验证**：

4. 发一个 PDF —— 期望先收到「收到 xx.pdf」→ 再收到卡片（需二期启用 `markitdown` 依赖与 `im:resource` 权限）。

若失败，看 `uvicorn` 日志排查（loguru 默认打印到 stderr）。
