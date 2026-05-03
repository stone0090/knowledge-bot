#!/usr/bin/env bash
# ECS 一次性初始化脚本（CentOS 7 / 幂等）
# 功能：
#   1. 装 git + ripgrep（走 EPEL + copr，失败则 fallback 到官方 static binary）
#   2. 创建 bare 仓库 /opt/vault-bare.git
#   3. 克隆工作副本 /opt/vault 并设置 git 身份
#   4. 建立 Raw/ Wiki/ SCHEMA.md 骨架 + .gitignore
#   5. 首次 commit+push
#
# 用法（ECS 上 root 执行）：
#   bash ecs_bootstrap_vault.sh
#
# 二次执行安全：所有步骤都会检查是否已完成。

set -euo pipefail

VAULT_BARE=/opt/vault-bare.git
VAULT_WORK=/opt/vault
GIT_NAME="${VAULT_GIT_AUTHOR_NAME:-Knowledge Bot}"
GIT_EMAIL="${VAULT_GIT_AUTHOR_EMAIL:-bot@knowledge-bot.local}"
RG_VERSION="14.1.1"

log() { printf "\n\033[1;32m[%s]\033[0m %s\n" "$(date +%H:%M:%S)" "$*"; }
warn() { printf "\n\033[1;33m[WARN]\033[0m %s\n" "$*"; }

# ---------- 1. 依赖 ----------
log "[1/5] 安装 git / ripgrep"

if ! command -v git >/dev/null 2>&1; then
    yum install -y git
fi

if ! command -v rg >/dev/null 2>&1; then
    # 先试 EPEL（CentOS 7 官方源没有 ripgrep）
    yum install -y epel-release yum-utils || true
    if ! yum install -y ripgrep 2>/dev/null; then
        warn "EPEL 里没有 ripgrep，尝试 copr"
        yum-config-manager --add-repo=https://copr.fedorainfracloud.org/coprs/carlwgeorge/ripgrep/repo/epel-7/carlwgeorge-ripgrep-epel-7.repo || true
        if ! yum install -y ripgrep 2>/dev/null; then
            warn "copr 也失败，fallback 到 GitHub release 静态二进制"
            TMP=$(mktemp -d)
            curl -fL "https://github.com/BurntSushi/ripgrep/releases/download/${RG_VERSION}/ripgrep-${RG_VERSION}-x86_64-unknown-linux-musl.tar.gz" -o "$TMP/rg.tgz"
            tar -xzf "$TMP/rg.tgz" -C "$TMP"
            install -m 755 "$TMP/ripgrep-${RG_VERSION}-x86_64-unknown-linux-musl/rg" /usr/local/bin/rg
            rm -rf "$TMP"
        fi
    fi
fi

command -v git >/dev/null && git --version
command -v rg  >/dev/null && rg --version | head -1

# ---------- 2. bare 仓库 ----------
log "[2/5] 创建 bare 仓库: $VAULT_BARE"
if [ ! -d "$VAULT_BARE" ]; then
    mkdir -p "$VAULT_BARE"
    # git 1.8.x 不支持 -b 参数，后续用 symbolic-ref 统一制成 master
    git init --bare "$VAULT_BARE"
else
    echo "已存在，跳过"
fi
# 显式固定 bare 仓库 HEAD 为 master（免得不同 git 版本行为不一致）
git --git-dir="$VAULT_BARE" symbolic-ref HEAD refs/heads/master

# ---------- 3. 工作副本 ----------
log "[3/5] 克隆工作副本: $VAULT_WORK"
if [ ! -d "$VAULT_WORK/.git" ]; then
    git clone "$VAULT_BARE" "$VAULT_WORK"
else
    echo "已存在，跳过"
fi

cd "$VAULT_WORK"
git config user.name  "$GIT_NAME"
git config user.email "$GIT_EMAIL"

# ---------- 4. 骨架 ----------
log "[4/5] 建立 Raw / Wiki / SCHEMA 骨架"
mkdir -p Raw/articles Raw/notes Raw/files Raw/videos
mkdir -p Wiki/entities Wiki/concepts Wiki/comparisons Wiki/queries

[ -f Wiki/index.md ] || cat > Wiki/index.md <<'EOF'
# Wiki 索引

本目录由 knowledge-bot 自动维护。
- entities/     实体页（人物 / 工具 / 公司 / 项目）
- concepts/     概念页（方法论 / 原则）
- comparisons/  对比页（横向对照）
- queries/      检索结果固化页（/查 的答卷归档）

详见 docs/技术方案.md §三。
EOF

[ -f Wiki/log.md ] || cat > Wiki/log.md <<'EOF'
# 变更日志

每次 ingest / compile 自动 commit 到 git，详细历史 `git log` 查看。
本文件仅记录人工重大调整（SCHEMA 变更、重构、批量迁移等）。
EOF

[ -f SCHEMA.md ] || cat > SCHEMA.md <<'EOF'
# SCHEMA

Wiki 页面的 YAML frontmatter 字段约定：

## 通用字段
- title       必填  一句话标题
- area        必填  Concepts / Areas-AI / Areas-Product / Areas-Mgmt / Archives
- tags        必填  关键词数组（3-5 个）
- summary     必填  一句话摘要（≤80 字）
- source_ref  选填  原始来源 URL 或文件名
- created_at  必填  ISO 8601 时间戳

## 实体页 (entities/)
额外字段：aliases, born, org

## 概念页 (concepts/)
额外字段：domain, opposites

## 对比页 (comparisons/)
额外字段：axis（对比维度数组）

## 查询页 (queries/)
额外字段：question, answered_at, cited_refs
EOF

[ -f .gitignore ] || cat > .gitignore <<'EOF'
# Obsidian
.obsidian/workspace*
.obsidian/cache
.trash/

# 系统
.DS_Store
Thumbs.db
*.tmp
*.swp

# 大文件（超过 100MB 的用 git-lfs 或排除）
Raw/files/*.iso
Raw/files/*.zip
EOF

# ---------- 5. 首次 commit + push ----------
log "[5/5] 首次提交"
git add .
if git diff --cached --quiet; then
    echo "无新变更，跳过 commit"
else
    git commit -m "init: vault skeleton (Raw/Wiki/SCHEMA)"
fi

# 统一推到 master（与 bare HEAD 对齐）
git push origin HEAD:master 2>&1 | tail -5 || true

# ---------- 汇报 ----------
echo ""
echo "========================================"
echo "  ✅ ECS Vault 初始化完成"
echo "========================================"
echo "bare 仓库: $VAULT_BARE"
echo "工作副本: $VAULT_WORK"
echo "git 身份: $GIT_NAME <$GIT_EMAIL>"
echo ""
echo "git log --oneline:"
git -C "$VAULT_WORK" log --oneline | head -5 || echo "(尚无提交)"
echo ""
echo "目录结构:"
ls -la "$VAULT_WORK"
echo ""
echo "三端接入用的 SSH clone 地址（如 sshd 非默认端口请在 URL 里加 :PORT）："
SERVER_IP=$(curl -s --max-time 3 ifconfig.me 2>/dev/null || hostname -I | awk '{print $1}')
SSH_PORT="${SSH_PORT:-$(awk '/^Port /{print $2}' /etc/ssh/sshd_config 2>/dev/null | tail -1)}"
SSH_PORT="${SSH_PORT:-22}"
if [ "$SSH_PORT" = "22" ]; then
    echo "  ssh://root@${SERVER_IP}${VAULT_BARE}"
else
    echo "  ssh://root@${SERVER_IP}:${SSH_PORT}${VAULT_BARE}"
fi
echo ""
echo "下一步："
echo "  1) 在你本机：.env 里 VAULT_PATH=${VAULT_WORK}，VAULT_GIT_REMOTE=${VAULT_BARE}"
echo "  2) 桌面/手机 Obsidian: git clone ssh://root@${SERVER_IP}${VAULT_BARE} ~/vault"
echo "  3) 强烈建议：ECS 改为公钥登录、关闭 root 密码登录"
