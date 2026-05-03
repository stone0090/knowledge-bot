#!/usr/bin/env bash
# ============================================================
# deploy_to_ecs.sh — 一键部署 knowledge-bot 到 ECS
#
# 用法（在本机项目根目录执行）：
#   bash scripts/deploy/deploy_to_ecs.sh          # 全量部署（首次）
#   bash scripts/deploy/deploy_to_ecs.sh update    # 仅同步代码+依赖+重启服务
#   bash scripts/deploy/deploy_to_ecs.sh restart   # 仅重启服务
#   bash scripts/deploy/deploy_to_ecs.sh status    # 查看服务状态+日志
#   bash scripts/deploy/deploy_to_ecs.sh logs      # 实时跟踪日志
#
# 前置条件：
#   1. SSH 免密已配好（ssh kb 能直连），见 setup_ssh_keyless.sh
#   2. .env.secrets 已填好密钥（见 .env.secrets.example）
#   3. ECS 上已通过 ecs_bootstrap_vault.sh 初始化过 Vault
# ============================================================
set -euo pipefail

# ---------- 配置区 ----------
REMOTE="kb"
REMOTE_APP_DIR="/opt/knowledge-bot"
PYTHON_BIN="/usr/local/bin/python3.10"
SERVICE_NAME="knowledge-bot"
NGINX_CONF="/etc/nginx/conf.d/${SERVICE_NAME}.conf"
# 项目根目录（脚本相对位置推断）
PROJECT_ROOT="$(cd "$(dirname "$0")/../.." && pwd)"

# ---------- 工具函数 ----------
log()  { printf "\n\033[1;32m>>>\033[0m %s\n" "$*"; }
warn() { printf "\033[1;33m[WARN]\033[0m %s\n" "$*"; }
err()  { printf "\033[1;31m[ERROR]\033[0m %s\n" "$*" >&2; exit 1; }

remote() { ssh "$REMOTE" "$@"; }

# ---------- 前置检查 ----------
preflight() {
    log "前置检查"
    # SSH 连通性
    ssh -o ConnectTimeout=5 "$REMOTE" 'echo "SSH ok"' \
        || err "无法连接 $REMOTE，请先运行 bash scripts/deploy/setup_ssh_keyless.sh"

    # .env.secrets 存在
    [ -f "$PROJECT_ROOT/envs/.env.secrets" ] || err "找不到 $PROJECT_ROOT/envs/.env.secrets，请先复制 .env.secrets.example 并填入密钥"

    # 远端 Python 3.10
    remote "$PYTHON_BIN --version" 2>/dev/null \
        || err "ECS 上找不到 $PYTHON_BIN，请先安装 Python 3.10（见 docs/feishu-setup.md）"

    echo "✅ 前置检查通过"
}

# ---------- 1. 同步代码 ----------
sync_code() {
    log "[1/5] 同步代码到 $REMOTE:$REMOTE_APP_DIR"
    remote "mkdir -p $REMOTE_APP_DIR"

    # 优先用 rsync（增量同步快），本机没装则 fallback 到 tar+scp
    if command -v rsync >/dev/null 2>&1; then
        rsync -avz --delete \
            --exclude '.env' \
            --exclude '.env.secrets' \
            --exclude '.venv/' \
            --exclude '__pycache__/' \
            --exclude '*.pyc' \
            --exclude '.git/' \
            --exclude '.qoder/' \
            --exclude 'scripts/tests/' \
            --exclude 'docs/' \
            -e "ssh" \
            "$PROJECT_ROOT/" "$REMOTE:$REMOTE_APP_DIR/"
    else
        echo "rsync 不可用，使用 tar+scp 方式..."
        local TMP_TAR
        TMP_TAR="$(mktemp -t kb-deploy-XXXX.tar.gz)"
        # 在项目根目录打 tar（排除不需要的目录）
        tar czf "$TMP_TAR" \
            --exclude='.env' \
            --exclude='.env.secrets' \
            --exclude='.venv' \
            --exclude='__pycache__' \
            --exclude='*.pyc' \
            --exclude='.git' \
            --exclude='.qoder' \
            --exclude='scripts/tests' \
            --exclude='docs' \
            -C "$PROJECT_ROOT" .
        scp "$TMP_TAR" "$REMOTE:/tmp/_kb_deploy.tar.gz"
        remote "cd $REMOTE_APP_DIR && tar xzf /tmp/_kb_deploy.tar.gz && rm -f /tmp/_kb_deploy.tar.gz"
        rm -f "$TMP_TAR"
    fi
    echo "✅ 代码同步完成"
}

# ---------- 2. 上传配置文件 ----------
sync_env() {
    log "[2/5] 上传环境配置 + 密钥"
    # envs/ecs.env 已随代码同步，只需上传密钥文件
    scp "$PROJECT_ROOT/envs/.env.secrets" "$REMOTE:$REMOTE_APP_DIR/envs/.env.secrets"
    remote "chmod 600 $REMOTE_APP_DIR/envs/.env.secrets"
    echo "✅ 密钥文件已上传并设置权限"
}

# ---------- 3. 虚拟环境 + 依赖 ----------
setup_venv() {
    log "[3/5] 创建虚拟环境 + 安装依赖"
    remote "bash -c '
        cd $REMOTE_APP_DIR
        if [ ! -d .venv ]; then
            echo \"创建 venv...\"
            $PYTHON_BIN -m venv .venv
        fi
        source .venv/bin/activate
        pip install --upgrade pip -q
        pip install -r requirements.txt -q
        echo "已安装的包:"
        pip list --format=columns 2>/dev/null | head -15 || true
    '"
    echo "✅ 依赖安装完成"
}

# ---------- 4. systemd 服务 ----------
setup_systemd() {
    log "[4/5] 配置 systemd 服务"
    remote "cat > /etc/systemd/system/${SERVICE_NAME}.service << 'UNIT'
[Unit]
Description=Knowledge Bot (FastAPI)
After=network.target

[Service]
Type=simple
WorkingDirectory=${REMOTE_APP_DIR}
Environment=APP_ENV=ecs
ExecStart=${REMOTE_APP_DIR}/.venv/bin/uvicorn app.main:app --host 127.0.0.1 --port 8000
Restart=always
RestartSec=3
StandardOutput=journal
StandardError=journal
SyslogIdentifier=${SERVICE_NAME}

[Install]
WantedBy=multi-user.target
UNIT

    systemctl daemon-reload
    systemctl enable ${SERVICE_NAME}
    "
    echo "✅ systemd 服务已配置"
}

# ---------- 5. Nginx 反代 ----------
setup_nginx() {
    log "[5/5] 配置 Nginx 反向代理"
    # 检查 Nginx 是否安装
    remote "command -v nginx" >/dev/null || {
        warn "Nginx 未安装，跳过反代配置。请手动安装后重新运行。"
        return 0
    }

    remote "cat > $NGINX_CONF << 'NGINX'
# knowledge-bot HTTP (9000) + HTTPS (9443)
server {
    listen 9000;
    server_name bot.shisb.com;

    location /healthz {
        proxy_pass http://127.0.0.1:8000/healthz;
    }

    location /feishu/ {
        proxy_pass http://127.0.0.1:8000/feishu/;
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto \$scheme;
        proxy_read_timeout 300s;
        client_max_body_size 50m;
    }
}

server {
    listen 9443 ssl;
    server_name bot.shisb.com;

    ssl_certificate     /etc/nginx/ssl/bot.shisb.com.pem;
    ssl_certificate_key /etc/nginx/ssl/bot.shisb.com.key;
    ssl_protocols       TLSv1.2 TLSv1.3;
    ssl_ciphers         HIGH:!aNULL:!MD5;

    location /healthz {
        proxy_pass http://127.0.0.1:8000/healthz;
    }

    location /feishu/ {
        proxy_pass http://127.0.0.1:8000/feishu/;
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto https;
        proxy_read_timeout 300s;
        client_max_body_size 50m;
    }
}
NGINX

    nginx -t 2>&1 && (systemctl is-active nginx >/dev/null 2>&1 && systemctl reload nginx || systemctl start nginx)
    "
    echo "✅ Nginx 反代已配置（HTTP 9000 + HTTPS 9443）"
}

# ---------- 启动/重启服务 ----------
restart_service() {
    log "启动服务"
    remote "systemctl restart ${SERVICE_NAME} && sleep 2 && systemctl is-active ${SERVICE_NAME}"
    # 健康检查
    if remote "curl -sf http://127.0.0.1:8000/healthz" >/dev/null 2>&1; then
        echo "✅ 服务运行中，健康检查通过"
    else
        warn "服务已启动但健康检查未通过，请查看日志："
        echo "  ssh kb 'journalctl -u ${SERVICE_NAME} -n 30 --no-pager'"
    fi
}

# ---------- 查看状态 ----------
show_status() {
    log "服务状态"
    remote "
        systemctl status ${SERVICE_NAME} --no-pager 2>&1 || true
        echo ''
        echo '--- 最近 20 行日志 ---'
        journalctl -u ${SERVICE_NAME} -n 20 --no-pager 2>&1 || true
    "
}

# ---------- 跟踪日志 ----------
follow_logs() {
    log "实时日志（Ctrl+C 退出）"
    ssh "$REMOTE" "journalctl -u ${SERVICE_NAME} -f --no-pager"
}

# ---------- 主流程 ----------
case "${1:-full}" in
    full)
        preflight
        sync_code
        sync_env
        setup_venv
        setup_systemd
        setup_nginx
        restart_service
        echo ""
        echo "========================================"
        echo "  ✅ knowledge-bot 部署完成"
        echo "========================================"
        echo "  应用目录: $REMOTE_APP_DIR"
        echo "  服务管理: systemctl {start|stop|restart} $SERVICE_NAME"
        echo "  查看日志: journalctl -u $SERVICE_NAME -f"
        echo "  健康检查: curl http://ECS_IP:9000/healthz"
        echo ""
        echo "  下一步："
        echo "  1) 配置 HTTPS 证书（飞书回调要求 HTTPS）"
        echo "  2) 在飞书开放平台填写回调地址 https://your-domain/feishu/event"
        echo "  3) 阿里云安全组放行 9000/9443 端口"
        echo "========================================"
        ;;
    update)
        preflight
        sync_code
        setup_venv
        restart_service
        echo "✅ 代码更新完成，服务已重启"
        ;;
    restart)
        restart_service
        ;;
    status)
        show_status
        ;;
    logs)
        follow_logs
        ;;
    *)
        echo "用法: $0 {full|update|restart|status|logs}"
        echo "  full     全量部署（首次使用）"
        echo "  update   同步代码+依赖+重启"
        echo "  restart  仅重启服务"
        echo "  status   查看服务状态与日志"
        echo "  logs     实时跟踪日志"
        exit 1
        ;;
esac
