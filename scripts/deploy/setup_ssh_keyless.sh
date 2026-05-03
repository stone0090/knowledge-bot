#!/usr/bin/env bash
# 本机（Windows Git Bash）一次性：给 ECS 配 SSH 公钥免密登录 + 起别名
#
# 用法（在 Git Bash 里，本项目根目录）：
#   bash scripts/setup_ssh_keyless.sh
#
# 跑完以后：
#   ssh kb                                   # 一键登录（替代 ssh -p 4500 root@121.196.26.127）
#   git clone kb:/opt/vault-bare.git ~/vault
#
# 可通过环境变量覆盖（都有默认值）：
#   ECS_HOST / ECS_PORT / ECS_USER / SSH_ALIAS

set -euo pipefail

ECS_HOST="${ECS_HOST:-121.196.26.127}"
ECS_PORT="${ECS_PORT:-4500}"
ECS_USER="${ECS_USER:-root}"
SSH_ALIAS="${SSH_ALIAS:-kb}"
KEY_PATH="$HOME/.ssh/id_ed25519"
CONFIG_PATH="$HOME/.ssh/config"

log()  { printf "\n\033[1;32m[*]\033[0m %s\n" "$*"; }
warn() { printf "\n\033[1;33m[!]\033[0m %s\n" "$*"; }

# ---------- 1. ~/.ssh 目录 ----------
log "[1/5] 确保 ~/.ssh 目录存在"
mkdir -p "$HOME/.ssh"
chmod 700 "$HOME/.ssh" 2>/dev/null || true

# ---------- 2. 生成密钥 ----------
if [ -f "$KEY_PATH" ]; then
    log "[2/5] 已存在 $KEY_PATH，跳过生成"
else
    log "[2/5] 生成 ed25519 密钥对（无 passphrase）"
    ssh-keygen -t ed25519 -C "$(whoami)@knowledge-bot-$(date +%Y%m%d)" -f "$KEY_PATH" -N ""
fi
chmod 600 "$KEY_PATH" 2>/dev/null || true
chmod 644 "${KEY_PATH}.pub" 2>/dev/null || true

# ---------- 3. 推公钥到 ECS（需要输一次密码） ----------
log "[3/5] 推送公钥到 ${ECS_USER}@${ECS_HOST}:${ECS_PORT}（将要求输入一次密码）"
PUBKEY=$(cat "${KEY_PATH}.pub")

ssh -p "$ECS_PORT" -o StrictHostKeyChecking=accept-new "$ECS_USER@$ECS_HOST" "
  mkdir -p ~/.ssh && chmod 700 ~/.ssh
  touch ~/.ssh/authorized_keys && chmod 600 ~/.ssh/authorized_keys
  if grep -qxF '$PUBKEY' ~/.ssh/authorized_keys; then
    echo '公钥已存在，跳过追加'
  else
    echo '$PUBKEY' >> ~/.ssh/authorized_keys
    echo '公钥已追加'
  fi
"

# ---------- 4. 写 ~/.ssh/config ----------
log "[4/5] 写入 SSH Host 别名：$SSH_ALIAS"
touch "$CONFIG_PATH"
chmod 600 "$CONFIG_PATH" 2>/dev/null || true

if grep -qE "^Host[[:space:]]+$SSH_ALIAS([[:space:]]|\$)" "$CONFIG_PATH" 2>/dev/null; then
    warn "$SSH_ALIAS 别名已存在，跳过写入 config（如需更新请手动编辑 $CONFIG_PATH）"
else
    cat >> "$CONFIG_PATH" <<EOF

Host $SSH_ALIAS
    HostName $ECS_HOST
    Port $ECS_PORT
    User $ECS_USER
    IdentityFile ~/.ssh/id_ed25519
    IdentitiesOnly yes
    ServerAliveInterval 60
EOF
    echo "已写入别名 $SSH_ALIAS -> $ECS_USER@$ECS_HOST:$ECS_PORT"
fi

# ---------- 5. 验证 ----------
log "[5/5] 验证免密登录"
if ssh -o BatchMode=yes "$SSH_ALIAS" 'echo "=== 免密验证成功 ==="; hostname; uname -a' 2>&1; then
    echo ""
    echo "========================================"
    echo "  ✅ SSH 免密登录已配置"
    echo "========================================"
    echo ""
    echo "以后可以直接用："
    echo "  ssh $SSH_ALIAS"
    echo "  git clone $SSH_ALIAS:/opt/vault-bare.git ~/vault"
    echo ""
    echo "【强烈建议现在做完两件事】"
    echo "  1. ssh $SSH_ALIAS 'passwd'                     # 改 root 密码（对话里那个已泄露）"
    echo "  2. 关闭密码登录，只允许公钥（更安全）："
    echo "     ssh $SSH_ALIAS \"sed -i 's/^#*PasswordAuthentication.*/PasswordAuthentication no/' /etc/ssh/sshd_config && systemctl restart sshd\""
else
    warn "免密验证失败"
    echo "调试命令：ssh -v $SSH_ALIAS"
    exit 1
fi
