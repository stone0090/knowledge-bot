# Obsidian Git 同步接入

> 在 PC / 手机上把 ECS Vault 同步进 Obsidian，走 **HTTPS + Basic Auth**。SSH 方案见 [setup.md](setup.md) 多端接入表。

## 前置信息

| 项 | 值 |
|---|---|
| Remote URL | `https://bot.shisb.com:4581/vault-bare.git` |
| Username | （向 ECS 管理员索取，下称 `<USER>`） |
| Token (PAT) | （同上，下称 `<TOKEN>`） |

- URL **必须用域名**，不要用 IP。证书 CN 为 `bot.shisb.com`，IP 访问会 SSL 校验失败。
- 服务端 nginx + git-http-backend + htpasswd 配置、安全组 4581 放行：见 ECS 运维文档。
- 仓库已强制 `.obsidian/` 不进 git（每台设备独立配置）。
- **Vault 布局推荐**：vault 根放 Obsidian 插件配置，子目录 `kb-vault/` 放 Git 仓库。这样 clone 不会覆盖 vault 根的 `.obsidian/`。Obsidian Git 设置里 `Custom base path (Git repository path)` 需设为 `kb-vault`（插件以此定位 `.git`）。

## PC 端

1. Obsidian → Settings → Community plugins → 搜 `Obsidian Git` → Install → Enable
2. Settings → Obsidian Git → **Advanced** → `Custom base path`: `kb-vault`（插件识别 `.git` 必填）
3. `Ctrl+P` → `Obsidian Git: Clone an existing remote repo`
4. 按提示依次填：
   - Remote URL: `https://bot.shisb.com:4581/vault-bare.git`
   - Depth: 留空回车
   - Directory: `kb-vault`
   - "Vault is not empty": **Yes**
5. Windows 凭据框弹出 → Username 填 `<USER>`，Password 填 `<TOKEN>`，勾选"记住"
6. Clone 完成后按 [推荐配置](#推荐配置) 补齐剩余字段

> PC 版调用系统 git，走 Windows / macOS 凭据管理器，**插件设置里无需填 Auth**。

## Android 端

1. 新建 vault `obsidian` 位置选 `/storage/emulated/0/Documents/`
2. Settings → Community plugins → 搜 `Obsidian Git` → Install → Enable
3. Settings → Obsidian Git 必填：
   - **Authentication/commit author**：
     - Username on your git server: `<USER>`
     - Password/Personal access token: `<TOKEN>`
   - **Advanced** → `Custom base path`: `kb-vault`（插件识别 `.git` 必填）
4. 返回 vault → 命令面板 → `Obsidian Git: Clone an existing remote repo`
5. 依次填：
   - Remote URL: `https://bot.shisb.com:4581/vault-bare.git`
   - Depth: 留空
   - Directory: `kb-vault`
   - "Vault is not empty": **Yes**
6. Clone 完成后按 [推荐配置](#推荐配置) 补齐剩余字段

> Android 版用 isomorphic-git（纯 JS），**凭据必须填在插件设置里**（URL 也可内嵌，但设置里填更稳）。

## 日常操作

| 操作 | 命令 |
|---|---|
| 拉取更新 | `Obsidian Git: Pull` |
| 一键备份 (commit + push) | `Obsidian Git: Create backup` |
| 查看历史 | `Obsidian Git: Show history view` |
| 查看变更 | `Obsidian Git: Open Source Control View` |

## 推荐配置

Settings → Obsidian Git：

| 字段 | 推荐值 | 说明 |
|---|---|---|
| Auto save interval | `5` | 停止编辑 5 分钟自动 commit |
| Auto push interval | `0` | 手动 push 更可控 |
| Pull before push | `true` | 多端同步防冲突 |
| Pull updates on startup | `true` | 打开 Obsidian 自动拉最新 |
| Sync method | `merge` | 不 rebase，保留多端历史 |
| Commit message | PC: `vault backup (PC): {{date}}`<br/>Android: `vault backup (mobile): {{date}}` | 多端区分来源；`{{date}}` 按 Commit date format 渲染 |
| Auto commit-and-sync message | 同 Commit message | 两者保持一致 |
| Commit date format | `YYYY-MM-DD HH:mm:ss` | 渲染 `{{date}}` 占位符 |
| List filenames affected by commit in the message body | `true` | commit body 列变更文件，history 可审查 |
| Custom base path | `kb-vault` | 给插件指示 `.git` 位置，与 clone 时 Directory 一致（**必填**） |
| Custom Git directory path | 留空 | 本地 `.git` 路径，**不是 Remote URL** |

## 常见坑

| 症状 | 原因 | 解法 |
|------|------|------|
| `fatal: unable to access … SSL certificate problem` | URL 用了 IP | 改用 `bot.shisb.com` 域名 |
| `To avoid conflicts, .obsidian needs to be deleted` | 远程历史曾包含 `.obsidian/` | ECS 端 `git rm -r --cached .obsidian/` + `.gitignore` 加 `.obsidian/` + push |
| Android "Git is not ready" 不消失 | Clone 未真正成功 | 从命令面板重跑 Clone，不要点工具栏的 push/pull（那是 clone 完之后才用的） |
| Android 设置里 `gitDir` 被误填成 URL | 字段含义误解 | 清空 Advanced → `Custom Git directory path` |
| Termux 里 `curl/git` 报 `ngtcp2_crypto_*` | libcurl 与依赖版本不匹配 | `pkg upgrade -y` 或 `pkg install --reinstall libcurl libngtcp2` |
| 401 Unauthorized | Token 错/过期/用户名错 | 重新索取凭据；Windows 凭据管理器删掉旧条目 `git:https://bot.shisb.com` |

## 相关文档

- 架构概览：[architecture.md](architecture.md)
- ECS Vault 初始化、飞书 / 百炼配置：[setup.md](setup.md)
