#!/usr/bin/env bash
# Install the public read-only OptionX research API only on 127.0.0.1.
# No brokers, no credential storage, no live orders, no firewall changes.
set -Eeuo pipefail
umask 027

REPO='https://github.com/narendra0369/optionautotrader.git'
BRANCH='optionx-aws-mumbai-bootstrap-20261124'
APP_DIR='/opt/optionx-v7'
UNIT='/etc/systemd/system/optionx-market-api.service'

fail() { echo "OPTIONX_BOOTSTRAP_BLOCKED: $*" >&2; exit 1; }
[[ "$(id -u)" == 0 ]] || fail 'Run with sudo on the existing Lightsail Ubuntu host'
[[ -f /etc/os-release ]] || fail 'Unknown Linux distribution'
. /etc/os-release
[[ "${ID:-}" == 'ubuntu' ]] || fail 'Only Ubuntu is supported'
[[ "$(uname -m)" == 'x86_64' || "$(uname -m)" == 'aarch64' ]] || fail 'Unexpected CPU architecture'
[[ ! -e "$APP_DIR" ]] || fail "$APP_DIR already exists; preserve existing deployment"
[[ ! -e "$UNIT" ]] || fail "$UNIT already exists; preserve existing systemd service"

if ! command -v git >/dev/null || ! command -v python3 >/dev/null || ! command -v curl >/dev/null; then
  apt-get update -qq
  DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends git python3 curl ca-certificates
fi

CANDIDATE=$(mktemp -d /opt/optionx-stage-XXXXXX)
trap 'if [[ -d "$CANDIDATE" ]]; then rm -rf -- "$CANDIDATE"; fi' EXIT

git clone --depth 1 --single-branch --branch "$BRANCH" "$REPO" "$CANDIDATE"
cd "$CANDIDATE"
python3 -m compileall -q market_api.py live_gateway.py angel_gateway.py live_v7 ops/aws_local_market_feed.py
python3 -m unittest -q live_v7.test_future_safety test_market_api
python3 - <<'PY'
from market_api import hard_block_order
body = hard_block_order()
assert body.get('error') == 'REAL_ORDERS_HARD_LOCKED', body
assert body.get('orderSent') is False, body
print('OPTIONX_PRECHECK_PASSED')
PY

if ! getent group optionx >/dev/null 2>&1; then
  groupadd --system optionx
fi
if ! id optionx >/dev/null 2>&1; then
  useradd --system --gid optionx --home-dir /nonexistent --shell /usr/sbin/nologin optionx
fi
mv -- "$CANDIDATE" "$APP_DIR"
chown -R root:root "$APP_DIR"
# mktemp creates mode 0700; the unprivileged service user needs directory traversal.
find "$APP_DIR" -type d -exec chmod 0755 {} +
find "$APP_DIR" -type f -exec chmod go-w {} +

cat > "$UNIT" <<'UNITFILE'
[Unit]
Description=OptionX local-only read-only research backend (real orders OFF)
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=optionx
Group=optionx
WorkingDirectory=/opt/optionx-v7
ExecStart=/usr/bin/python3 -B -m ops.aws_local_market_feed
Environment=PYTHONDONTWRITEBYTECODE=1
Environment=OPTIONX_V7_STAGING_CORS=0
Environment=OPTIONX_LIVE_ORDERS_ENABLED=0
Environment=OPTIONX_ENABLE_LIVE_TRADING=0
Restart=on-failure
RestartSec=5
NoNewPrivileges=true
PrivateTmp=true
ProtectHome=true
ProtectSystem=strict
RestrictAddressFamilies=AF_INET AF_INET6 AF_UNIX
MemoryMax=512M
TasksMax=60

[Install]
WantedBy=multi-user.target
UNITFILE
systemctl daemon-reload
systemctl enable --now optionx-market-api
sleep 2

python3 - <<'PY'
import json, urllib.request
with urllib.request.urlopen('http://127.0.0.1:10000/health', timeout=8) as reply:
    body = json.load(reply)
assert body['status'] == 'ok', body
assert body['paperOnly'] is True, body
assert body['liveOrdersEnabled'] is False, body
print('OPTIONX_LOCAL_HEALTH_PASSED; real orders remain OFF')
PY
printf '%s\n' 'OPTIONX_BOOTSTRAP_COMPLETE'
