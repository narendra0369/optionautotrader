#!/usr/bin/env bash
# OptionX owner control receiver installer. No Angel order permissions.
set -Eeuo pipefail
umask 077
REPO=/opt/optionx-v52
CONF_DIR=/etc/optionx-v52
CONF_FILE="$CONF_DIR/receiver.env"
KEY_FILE="$CONF_DIR/owner-relay-hmac.key"
UNIT=/etc/systemd/system/optionx-owner-receiver.service
SERVICE=optionx-owner-receiver.service

fail() { printf 'BLOCKED: %s\n' "$*" >&2; exit 1; }
[[ "$(id -u)" == 0 ]] || fail "Run with sudo bash"
id optionx >/dev/null 2>&1 || fail "Existing optionx OS user required"
[[ -f "$REPO/live_v7/aws_control_receiver_v48.py" ]] || fail "V52 receiver source missing"
[[ -f "$REPO/live_v7/owner_receiver_systemd_v52.py" ]] || fail "V52 launcher missing: update worktree"
command -v python3 >/dev/null || fail "python3 missing"
command -v openssl >/dev/null || fail "openssl missing"
command -v curl >/dev/null || fail "curl missing"

OWNER_ID="$(printenv OPTIONX_OWNER_USER_ID || true)"
if [[ -z "$OWNER_ID" && -s "$CONF_FILE" ]]; then
  OWNER_ID="$(sed -n 's/^OPTIONX_OWNER_USER_ID=//p' "$CONF_FILE" | tail -n 1)"
fi
if [[ -z "$OWNER_ID" && -s /opt/optionx-v7/.env ]]; then
  OWNER_ID="$(sed -n 's/^OPTIONX_OWNER_USER_ID=//p' /opt/optionx-v7/.env | tail -n 1 | tr -d "\"'")"
fi
if [[ -z "$OWNER_ID" ]]; then
  printf 'Enter OptionX account owner UUID (NOT Angel client ID): '
  IFS= read -r OWNER_ID || fail "Owner UUID required"
fi
OWNER_ID="$(python3 - "$OWNER_ID" <<'PY'
import sys
from uuid import UUID
try:
    raw=sys.argv[1].strip()
    owner=str(UUID(raw))
    if raw!=owner:raise ValueError('canonical UUID required')
    print(owner)
except (ValueError, IndexError):
    sys.exit(2)
PY
)" || fail "Invalid owner UUID; no service changes made"

install -d -o root -g root -m 0700 "$CONF_DIR"
if [[ ! -e "$KEY_FILE" ]]; then
  tmp="$(mktemp "$CONF_DIR/.hmac.XXXXXXXX")"
  trap 'rm -f "$tmp"' EXIT
  openssl rand -hex 48 > "$tmp"
  install -o root -g root -m 0600 "$tmp" "$KEY_FILE"
  rm -f "$tmp"
  trap - EXIT
  echo "CREATED: private 384-bit owner-control signing key"
else
  [[ -f "$KEY_FILE" && ! -L "$KEY_FILE" ]] || fail "Existing key is unsafe"
  [[ "$(stat -c %a "$KEY_FILE")" == 600 ]] || fail "Key must have chmod 600"
  echo "REUSED: existing private signing key"
fi
tmp="$(mktemp "$CONF_DIR/.env.XXXXXXXX")"
trap 'rm -f "$tmp"' EXIT
printf 'OPTIONX_OWNER_USER_ID=%s\n' "$OWNER_ID" > "$tmp"
install -o root -g root -m 0600 "$tmp" "$CONF_FILE"
rm -f "$tmp"
trap - EXIT
cat > "$UNIT" <<'UNIT'
[Unit]
Description=OptionX Private Owner Command Receiver (not a trading worker)
After=network.target

[Service]
Type=simple
User=optionx
Group=optionx
WorkingDirectory=/opt/optionx-v52
EnvironmentFile=/etc/optionx-v52/receiver.env
LoadCredential=relay_key:/etc/optionx-v52/owner-relay-hmac.key
StateDirectory=optionx-v52-control
StateDirectoryMode=0700
UMask=0077
ExecStart=/usr/bin/python3 -B -m live_v7.owner_receiver_systemd_v52
Restart=on-failure
RestartSec=4
NoNewPrivileges=yes
PrivateTmp=yes
PrivateDevices=yes
ProtectSystem=strict
ProtectHome=yes
ProtectKernelTunables=yes
ProtectKernelModules=yes
ProtectControlGroups=yes
RestrictSUIDSGID=yes
RestrictAddressFamilies=AF_UNIX AF_INET AF_INET6
IPAddressDeny=any
IPAddressAllow=localhost
CapabilityBoundingSet=
LockPersonality=yes

[Install]
WantedBy=multi-user.target
UNIT
chmod 0644 "$UNIT"
python3 -B -m py_compile "$REPO/live_v7/owner_receiver_systemd_v52.py"
systemctl daemon-reload
systemctl enable --now "$SERVICE"
sleep 1
systemctl is-active --quiet "$SERVICE" || {
  systemctl status "$SERVICE" --no-pager -l || true
  fail "Receiver service did not start"
}
code="$(curl --connect-timeout 2 -m 5 -sS -o /dev/null -w '%{http_code}' http://127.0.0.1:8766/v48/owner/control)" || fail "Loopback receiver unavailable"
[[ "$code" == 404 ]] || fail "Unexpected GET response HTTP $code"
echo "PASS: optionx-owner-receiver.service ACTIVE"
echo "PASS: only localhost port 8766; GET intentionally returns 404"
echo "PASS: signing key is private; not printed"
echo "REAL_ANGEL_ORDERS: OFF"
echo "PENDING: HTTPS proxy and Render signing-key provisioning"
