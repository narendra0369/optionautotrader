#!/usr/bin/env bash
set -Eeuo pipefail
fail(){ echo "BLOCKED: $*" >&2; exit 1; }
[[ "$(id -u)" == 0 ]] || fail "sudo required"
DOMAIN="$(printf '%s' "$1" | tr '[:upper:]' '[:lower:]')"
[[ "$DOMAIN" =~ ^[a-z0-9]([a-z0-9.-]*[a-z0-9])?$ && "$DOMAIN" == *.* ]] || fail "Public FQDN required"
[[ "$DOMAIN" != *..* ]] || fail "Invalid hostname"
for c in caddy curl getent python3 systemctl ss; do command -v "$c" >/dev/null || fail "$c missing"; done
systemctl is-active --quiet optionx-owner-receiver.service || fail "AWS receiver not active"
if [[ -e /etc/caddy/Caddyfile ]] && ! grep -q '^# OPTIONX_OWNER_DEDICATED_CADDYFILE_V52$' /etc/caddy/Caddyfile; then
  fail "Existing /etc/caddy/Caddyfile is not ours; refusing to overwrite"
fi
if ss -H -lntp | grep -E ':(80|443)[[:space:]]' | grep -v 'caddy' >/dev/null; then
  fail "Port 80/443 already occupied by another service"
fi
ip="$(curl -4fsS --max-time 10 https://checkip.amazonaws.com | tr -d '[:space:]')" || fail "Cannot verify public IP"
python3 - "$ip" <<'PY' || fail "Invalid public IPv4"
import ipaddress,sys
i=ipaddress.ip_address(sys.argv[1])
if i.version!=4 or not i.is_global:raise SystemExit(1)
PY
if ! getent ahostsv4 "$DOMAIN" | awk '{print $1}' | grep -Fxq "$ip"; then
  echo "PUBLIC_IP=$ip"
  fail "Domain DNS A does not point to instance public IPv4"
fi
install -d -m 0755 /etc/caddy
tmp="$(mktemp /etc/caddy/.optionx.XXXXXXXX)"
trap 'rm -f "$tmp"' EXIT
cat >"$tmp" <<EOF
# OPTIONX_OWNER_DEDICATED_CADDYFILE_V52
$DOMAIN {
    @ownercontrol {
        method POST
        path /v48/owner/control
    }
    handle @ownercontrol {
        reverse_proxy 127.0.0.1:8766
    }
    handle {
        respond "Not Found" 404
    }
}
EOF
caddy validate --config "$tmp" --adapter caddyfile >/dev/null || fail "Caddyfile invalid"
if [[ -f /etc/caddy/Caddyfile ]]; then
  cp -a /etc/caddy/Caddyfile "/etc/caddy/Caddyfile.bak.$(date -u +%Y%m%d%H%M%S)"
fi
install -m 0644 "$tmp" /etc/caddy/Caddyfile
rm -f "$tmp"
trap - EXIT
systemctl enable --now caddy
systemctl reload caddy
echo "CADDY_SERVICE=$(systemctl is-active caddy)"
echo "RECEIVER_SERVICE=$(systemctl is-active optionx-owner-receiver.service)"
echo "AWS_HTTPS_URL=https://$DOMAIN/v48/owner/control"
echo "SIGNING_KEY_WAS_NOT_PRINTED"
echo "REAL_ANGEL_ORDERS=OFF"
echo "NOTE: ACME TLS needs inbound 80/443 and publicly resolving DNS"
