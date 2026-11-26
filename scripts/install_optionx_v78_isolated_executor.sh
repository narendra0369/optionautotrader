#!/usr/bin/env bash
# V78: isolated deny-only executor staging. Does not alter existing workers,
# database roles, IAM role, credentials, broker orders or Owner STOP.
set -Eeuo pipefail
umask 077
fail(){ echo "BLOCK: $*" >&2; exit 1; }
[[ "$(id -u)" -eq 0 ]] || fail "Use sudo bash"
command -v useradd >/dev/null || fail "useradd missing"
command -v systemctl >/dev/null || fail "systemctl missing"
command -v python3 >/dev/null || fail "python3 missing"
for s in optionx-market-api optionx-owner-receiver optionx-paper-health-watchdog optionx-v54-paper-worker optionx-v58-recovery-observer; do
  systemctl is-active --quiet "$s" || fail "Existing service $s is not active"
done
if ! id optionx-executor >/dev/null 2>&1; then
  useradd --system --no-create-home --home-dir /nonexistent --shell /usr/sbin/nologin --user-group optionx-executor
  echo "CREATED: isolated optionx-executor account"
fi
[[ "$(id -un "$(id -u optionx-executor)")" == optionx-executor ]] || fail "Unexpected executor identity"
[[ "$(getent passwd optionx-executor | cut -d: -f7)" == "/usr/sbin/nologin" ]] || fail "Executor shell must be nologin"
[[ -z "$(id -nG optionx-executor | tr ' ' '\n' | grep -vx optionx-executor || true)" ]] || fail "Executor has unexpected group memberships"
install -d -o root -g root -m 0755 /opt/optionx-v78
cat >/opt/optionx-v78/deny_worker.py <<'PY'
import signal
import time
running=True
def stop(*_):
    global running
    running=False
signal.signal(signal.SIGTERM,stop)
signal.signal(signal.SIGINT,stop)
print("V78_ISOLATED_STAGING_RUNNING NO_DB NO_BROKER NO_ORDERS",flush=True)
while running: time.sleep(5)
print("V78_ISOLATED_STAGING_STOPPED",flush=True)
PY
chown root:root /opt/optionx-v78/deny_worker.py
chmod 0644 /opt/optionx-v78/deny_worker.py
python3 -m py_compile /opt/optionx-v78/deny_worker.py
unit=/etc/systemd/system/optionx-v78-executor-staging.service
if [[ -e "$unit" ]] && ! grep -Fxq '# OPTIONX_V78_ISOLATED_DENY_ONLY' "$unit"; then
 fail "An unrelated service file already exists; refusing to overwrite"
fi
cat >"$unit" <<'UNIT'
# OPTIONX_V78_ISOLATED_DENY_ONLY
[Unit]
Description=OptionX V78 isolated deny-only worker (NOT live trading)
After=local-fs.target
[Service]
Type=simple
User=optionx-executor
Group=optionx-executor
WorkingDirectory=/
ExecStart=/usr/bin/python3 -I -B /opt/optionx-v78/deny_worker.py
Restart=on-failure
RestartSec=5
UMask=0077
NoNewPrivileges=yes
PrivateNetwork=yes
IPAddressDeny=any
RestrictAddressFamilies=AF_UNIX
PrivateTmp=yes
PrivateDevices=yes
ProtectSystem=strict
ProtectHome=yes
ProtectKernelTunables=yes
ProtectKernelModules=yes
ProtectControlGroups=yes
RestrictSUIDSGID=yes
LockPersonality=yes
CapabilityBoundingSet=
AmbientCapabilities=
LimitNOFILE=128
MemoryMax=128M
[Install]
WantedBy=multi-user.target
UNIT
chmod 0644 "$unit"
systemctl daemon-reload
# Intentional: start only; DO NOT enable on boot before review.
systemctl start optionx-v78-executor-staging.service
systemctl is-active --quiet optionx-v78-executor-staging.service || fail "Isolated staging service failed"
echo "=== OPTIONX V78 STAGING RESULT ==="
systemctl show optionx-v78-executor-staging.service --no-pager -p ActiveState -p User -p Group -p PrivateNetwork -p IPAddressDeny -p RestrictAddressFamilies -p NoNewPrivileges -p ProtectSystem -p ProtectHome
for s in optionx-market-api optionx-owner-receiver optionx-paper-health-watchdog optionx-v54-paper-worker optionx-v58-recovery-observer; do
 systemctl is-active --quiet "$s" || fail "Existing service $s changed state unexpectedly"
done
echo "PASS: FIVE_EXISTING_SERVICES_STILL_ACTIVE"
echo "PASS: V78_ISOLATED_STAGING_STARTED"
echo "NOT_CERTIFIED: AWS_WORKLOAD_TO_DB_PRINCIPAL_BINDING"
echo "NO_BROKER_REQUESTS; NO_DB_WRITES; NO_LIVE_ORDERS"
echo "V78_ISOLATED_SETUP_COMPLETE"
