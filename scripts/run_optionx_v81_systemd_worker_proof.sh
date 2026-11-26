#!/usr/bin/env bash
# OPTIONX V81: non-invasive one-shot signed proof running AS optionx-executor.
# Requires this file and optionx_v81_unprivileged_systemd_signed_proof.py
# from a trusted GitHub checkout. Never enables or restarts existing units.
set -Eeuo pipefail
umask 077
die(){ echo "V81_BLOCK: $*" >&2; exit 1; }
[[ "$(id -u)" -eq 0 ]] || die "sudo bash required"
command -v systemd-run >/dev/null || die "systemd-run unavailable"
command -v openssl >/dev/null || die "openssl unavailable"
id optionx-executor >/dev/null || die "Isolated V78 account missing"
[[ "$(getent passwd optionx-executor|cut -d: -f7)" == "/usr/sbin/nologin" ]] || die "Executor login must be disabled"
source_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source_py="$source_dir/optionx_v81_unprivileged_systemd_signed_proof.py"
[[ -f "$source_py" && ! -L "$source_py" ]] || die "V81 source script missing"
for s in optionx-market-api optionx-owner-receiver optionx-paper-health-watchdog optionx-v54-paper-worker optionx-v58-recovery-observer optionx-v78-executor-staging; do
 systemctl is-active --quiet "$s" || die "Expected service inactive: $s"
done
private="/etc/optionx-v79/worker_ed25519.key"
public="/etc/optionx-v79/worker_ed25519.public.pem"
worker="/etc/optionx-v79/worker_id"
owner_env="/etc/optionx-v52/receiver.env"
for file in "$private" "$public" "$worker" "$owner_env"; do
 [[ -f "$file" && ! -L "$file" ]] || die "Missing or unsafe existing file"
done
[[ "$(stat -c %U "$private")" == root && "$(stat -c %a "$private")" == 600 ]] || die "Original private key permissions fail"
fp="$(openssl pkey -pubin -in "$public" -outform DER 2>/dev/null|sha256sum|cut -d' ' -f1)"
[[ "$fp" == 94fc2e18d81cd126b34a21261d542b06c918649f388cb553c1e051f4dcf1a4d6 ]] || die "Key fingerprint mismatch"
install -d -o root -g root -m 0755 /opt/optionx-v81
install -d -o root -g root -m 0700 /etc/optionx-v81
owner_uuid="$(sed -n 's/^OPTIONX_OWNER_USER_ID=//p' "$owner_env" | head -1 | tr -d '"\047')"
[[ "$owner_uuid" =~ ^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$ ]] || die "Owner UUID binding invalid"
temp_owner="$(mktemp /etc/optionx-v81/.owner.XXXXXXXX)"
trap 'rm -f "$temp_owner"' EXIT
printf '%s\n' "$owner_uuid" > "$temp_owner"
install -o root -g root -m 0600 "$temp_owner" /etc/optionx-v81/owner_uuid
rm -f "$temp_owner"
trap - EXIT
# Only install expected source. Never copy original private key or expose it.
install -o root -g root -m 0644 "$source_py" /opt/optionx-v81/worker_proof.py
python3 -B -m py_compile /opt/optionx-v81/worker_proof.py
echo "=== OPTIONX V81 SYSTEMD ONE-SHOT SIGNED WORKLOAD PROOF ==="
systemd-run --wait --collect --pipe --unit="optionx-v81-proof-$$" \
 --property="User=optionx-executor" \
 --property="Group=optionx-executor" \
 --property="Environment=OPTIONX_EXPECTED_EXECUTOR_UID=$(id -u optionx-executor)" \
 --property="LoadCredential=worker_ed25519:$private" \
 --property="LoadCredential=owner_uuid:/etc/optionx-v81/owner_uuid" \
 --property=NoNewPrivileges=yes \
 --property=PrivateTmp=yes \
 --property=PrivateDevices=yes \
 --property=ProtectSystem=strict \
 --property=ProtectHome=yes \
 --property=ProtectKernelTunables=yes \
 --property=ProtectKernelModules=yes \
 --property=ProtectControlGroups=yes \
 --property=CapabilityBoundingSet= \
 --property=RestrictSUIDSGID=yes \
 --property="RestrictAddressFamilies=AF_UNIX AF_INET AF_INET6" \
 /usr/bin/python3 -I -B /opt/optionx-v81/worker_proof.py
for s in optionx-market-api optionx-owner-receiver optionx-paper-health-watchdog optionx-v54-paper-worker optionx-v58-recovery-observer optionx-v78-executor-staging; do
 systemctl is-active --quiet "$s" || die "Service changed state: $s"
done
echo "V81_ALL_SIX_EXISTING_SERVICES_REMAIN_ACTIVE"
echo "WORKER_REGISTRATION_PENDING; NO_POSTGRES_LOGIN; LIVE_ORDERS_OFF"
