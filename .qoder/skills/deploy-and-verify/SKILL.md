---
name: deploy-and-verify
description: End-to-end deployment verification workflow for knowledge-bot. Covers git commit, GitHub push, ECS deploy script, systemd health check, and Feishu smoke test. Use when the user asks to deploy, push to production, update ECS, or verify the service is running correctly after code changes.
---

# 部署验证闭环

代码改完后的完整部署 → 验证流程。与 `ecs-access` 的区别：`ecs-access` 是 SSH 操作手册，本 skill 是从本地代码到线上验证的端到端流程。

## 工作流（五步）

### 1. 提交代码

```bash
cd d:/stone/code/stone0090/knowledge-bot
git add -A
git diff --cached --stat          # 确认变更范围
git commit -m "<type>: <中文描述>"
```

**commit message 规范**：
- `feat:` 新功能 / `fix:` 修复 / `refactor:` 重构 / `docs:` 文档 / `chore:` 杂务
- 描述用中文，简洁概括改了什么

### 2. 推送到 GitHub

```bash
git push
```

如果超时（本地网络限制），启用代理：

```bash
git config http.proxy http://127.0.0.1:7890
git push
git config --unset http.proxy
```

### 3. 部署到 ECS

```bash
bash scripts/deploy/deploy_to_ecs.sh update    # 常规更新：代码 + 依赖 + 重启
bash scripts/deploy/deploy_to_ecs.sh full      # 首次或大改：含 systemd 配置 + Nginx
```

脚本自动完成：rsync 代码 → scp 密钥 → pip install → systemctl restart。

**前置条件**：
- SSH 别名 `kb` 已配置（`ssh kb` 能直连）
- `envs/.env.secrets` 已填写

### 4. 健康检查

部署脚本结束后验证服务状态：

```bash
# 方式 A：脚本内置
bash scripts/deploy/deploy_to_ecs.sh status

# 方式 B：手动
ssh kb 'systemctl status knowledge-bot'
ssh kb 'journalctl -u knowledge-bot --no-pager -n 30'
```

**检查项**：
- [ ] systemd 状态为 `active (running)`
- [ ] 日志无 `ImportError` / `ModuleNotFoundError`（缺依赖）
- [ ] 日志无 `KeyError` / `ValidationError`（缺环境变量）
- [ ] 监听端口正常：`ssh kb 'ss -tlnp | grep 8000'`

### 5. 飞书冒烟测试

在飞书与机器人私聊，按改动范围选测：

| 测试项 | 发送内容 | 期望 |
|--------|---------|------|
| 纯文本投喂 | 一段文字 | 绿色卡片「已收录」 |
| URL 投喂 | 一个网页链接 | 绿色卡片（标题 + 摘要） |
| 微信文章 | 公众号永久链 | 绿色卡片（提取正文） |
| 检索 | `/查 关键词` | 蓝色卡片（答案 + 引用） |

失败时查日志：`bash scripts/deploy/deploy_to_ecs.sh logs`

## 快速命令速查

```bash
# 一键走完 1-3 步（提交 + 推送 + 部署）
git add -A && git commit -m "feat: xxx" && git push && bash scripts/deploy/deploy_to_ecs.sh update

# 只看日志
bash scripts/deploy/deploy_to_ecs.sh logs

# 只重启（不更新代码）
bash scripts/deploy/deploy_to_ecs.sh restart
```

## 常见问题

| 现象 | 原因 | 解决 |
|------|------|------|
| `git push` 超时 | 本地网络无法直连 GitHub | 加 `http.proxy` 代理 |
| deploy 脚本报 `找不到 .env.secrets` | 密钥文件路径 | 确保 `envs/.env.secrets` 存在 |
| systemd 启动失败 | 新依赖未安装 | `ssh kb '/opt/knowledge-bot/.venv/bin/pip install -r /opt/knowledge-bot/requirements.txt'` |
| 飞书回调无响应 | Nginx / 端口 / 证书 | 检查 `ssh kb 'nginx -t && ss -tlnp \| grep -E "9000\|9443"'` |
| 日志报 `DASHSCOPE_API_KEY` 为空 | ECS 上密钥未更新 | 重新 `scp envs/.env.secrets kb:/opt/knowledge-bot/envs/` |

## 反模式

- ❌ 改完代码不提交直接部署（ECS 拿不到最新代码，rsync 走的是本地文件但 deploy 脚本依赖 git 状态）
- ❌ 部署后不看 systemd 状态就宣布完成
- ❌ 只看 `status` 不做飞书冒烟测试（进程活着不代表业务正常）
- ❌ 在 ECS 上直接 `vim` 改代码（下次部署会被覆盖）
