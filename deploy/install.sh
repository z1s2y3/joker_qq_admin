#!/usr/bin/env bash
set -euo pipefail

APP_DIR="${JOKER_QQ_ADMIN_DIR:-/www/wwwroot/joker_qq_admin}"
SERVICE_USER="${JOKER_QQ_ADMIN_USER:-joker-qq-admin}"
SERVICE_NAME="joker-qq-admin"
SOURCE_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

if [[ "$(id -u)" -ne 0 ]]; then
  echo "请使用 root 执行此脚本。" >&2
  exit 1
fi

command -v python3 >/dev/null || {
  echo "未找到 python3，请先安装 Python 3.10 或更高版本。" >&2
  exit 1
}

python3 -c 'import sys; raise SystemExit(0 if sys.version_info >= (3, 10) else 1)' || {
  echo "python3 版本低于 3.10，请先升级。" >&2
  exit 1
}

id "$SERVICE_USER" >/dev/null 2>&1 || useradd --system --home-dir "$APP_DIR" --shell /usr/sbin/nologin "$SERVICE_USER"
install -d -o "$SERVICE_USER" -g "$SERVICE_USER" "$APP_DIR" /etc/joker_qq_admin
install -d -o "$SERVICE_USER" -g "$SERVICE_USER" /var/lib/joker_qq_admin
# 只复制程序和部署配置，不复制旧数据、数据库、浏览器缓存或 Git 元数据。
if [[ "$SOURCE_DIR" != "$APP_DIR" ]]; then
  PROGRAM_ITEMS=(README.md CHANGELOG.md .env.example .gitignore requirements.txt run.py api.py app.py config.py dashboard.py dashboard_overlays.py dashboard_pages.py group_dashboard_page.py gateway.py storage.py webhook.py features deploy)
  # 先替换整套程序文件，避免新旧文件混用导致缺少模块或保留已删除的测试代码。
  for item in "${PROGRAM_ITEMS[@]}"; do
    rm -rf "$APP_DIR/$item"
  done
  for item in "${PROGRAM_ITEMS[@]}"; do
    if [[ -d "$SOURCE_DIR/$item" ]]; then
      cp -R "$SOURCE_DIR/$item" "$APP_DIR/"
    else
      cp "$SOURCE_DIR/$item" "$APP_DIR/"
    fi
  done
fi
find "$APP_DIR" -type d -name __pycache__ -prune -exec rm -rf {} +
find "$APP_DIR" -type f \( -name '*.pyc' -o -name '*.pyo' \) -delete
find "$APP_DIR" -mindepth 1 ! -path "$APP_DIR/.user.ini" -exec chown "$SERVICE_USER:$SERVICE_USER" {} +

python3 -m venv "$APP_DIR/.venv"
"$APP_DIR/.venv/bin/python" -m pip install --upgrade pip
"$APP_DIR/.venv/bin/python" -m pip install -r "$APP_DIR/requirements.txt"

if [[ ! -f /etc/joker_qq_admin/joker_qq_admin.env ]]; then
  install -o "$SERVICE_USER" -g "$SERVICE_USER" -m 600 /dev/null /etc/joker_qq_admin/joker_qq_admin.env
  cat >&2 <<'EOF'
已创建 /etc/joker_qq_admin/joker_qq_admin.env，请写入 AppID 和 AppSecret 后再启动服务。
EOF
fi

sed \
  -e "s|__APP_DIR__|$APP_DIR|g" \
  -e "s|__SERVICE_USER__|$SERVICE_USER|g" \
  "$SOURCE_DIR/deploy/joker-qq-admin.service" \
  > /etc/systemd/system/joker-qq-admin.service
chmod 644 /etc/systemd/system/joker-qq-admin.service
systemctl daemon-reload
systemctl enable "$SERVICE_NAME"

if ! grep -qE '^QQBOT_APP_ID=.+$' /etc/joker_qq_admin/joker_qq_admin.env || \
   ! grep -qE '^QQBOT_APP_SECRET=.+$' /etc/joker_qq_admin/joker_qq_admin.env; then
  systemctl stop "$SERVICE_NAME" >/dev/null 2>&1 || true
  cat >&2 <<'EOF'
程序已安装，但环境文件还没有 AppSecret，服务暂不启动。
请编辑 /etc/joker_qq_admin/joker_qq_admin.env 后重新执行本脚本。
EOF
  exit 0
fi

systemctl restart "$SERVICE_NAME"
systemctl --no-pager --full status "$SERVICE_NAME" || true

