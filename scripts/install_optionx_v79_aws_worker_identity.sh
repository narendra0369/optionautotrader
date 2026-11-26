#!/usr/bin/env bash
# OPTIONX V79: independently generated Ed25519 identity on original AWS host.
# This is an isolated host credential, NOT authenticated PostgreSQL binding.
# Safe for re-run: never overwrite an existing private key.
set -Eeuo pipefail
umask 077
die(){ printf 'BLOCK: %s\n' "$*" >&2; exit 1; }
[[ "$(id -u)" = 0 ]] || die "sudo bash required"
command -v openssl >/dev/null || die "OpenSSL is required"
command -v systemd-run >/dev/null || die "systemd-run is required"
id optionx-executor >/dev/null 2>&1 || die "V78 account missing"
[[ "$(getent passwd optionx-executor | cut -d: -f7)" = /usr/sbin/nologin ]] || die "Executor interactive login must be disabled"
for s in optionx-market-api optionx-owner-receiver optionx-paper-health-watchdog optionx-v54-paper-worker optionx-v58-recovery-observer; do
 systemctl is-active --quiet "$s" || die "Production service not active: $s"
done
dir=/etc/optionx-v79
private="$dir/worker_ed25519.key"
public="$dir/worker_ed25519.public.pem"
probe=/opt/optionx-v79/worker_key_probe.py
install -d -o root -g root -m 0755 "$dir"
install -d -o root -g root -m 0755 /opt/optionx-v79
if [[ -L "$private" || -L "$public" ]]; then die "Symlink key path forbidden"; fi
if [[ ! -e "$private" ]]; then
 tmp="$(mktemp "$dir/.private.XXXXXXXX")"
 trap 'rm -f "$tmp"' EXIT
 openssl genpkey -algorithm ED25519 -out "$tmp" >/dev/null 2>&1 || die "Unable to generate worker key"
 install -o root -g root -m 0600 "$tmp" "$private"
 rm -f "$tmp"
 trap - EXIT
 echo "CREATED: private Ed25519 key on AWS only"
else
 [[ -f "$private" && "$(stat -c %a "$private")" = 600 && "$(stat -c %U "$private")" = root ]] || die "Existing key permissions unacceptable"
 echo "REUSED: existing AWS-only private key"
fi
# Public half is exportable; never print the private PEM.
[[ -f "$public" ]] || openssl pkey -in "$private" -pubout -out "$public" >/dev/null 2>&1
chown root:root "$public"
chmod 0644 "$public"
openssl pkey -pubin -in "$public" -text -noout >/dev/null 2>&1 || die "Invalid public key"
worker_id_file="$dir/worker_id"
if [[ -L "$worker_id_file" ]]; then die "Worker identity must not be symlink"; fi
if [[ ! -e "$worker_id_file" ]]; then
 tmpid="$(mktemp "$dir/.worker-id.XXXXXXXX")"
 trap 'rm -f "$tmpid"' EXIT
 python3 -c 'import uuid;print(uuid.uuid4())' >"$tmpid"
 install -o root -g root -m 0644 "$tmpid" "$worker_id_file"
 rm -f "$tmpid"
 trap - EXIT
fi
python3 - "$worker_id_file" <<'PY'
from uuid import UUID
import sys
raw=open(sys.argv[1],encoding="ascii").read().strip()
assert str(UUID(raw))==raw, "Invalid stable worker_id"
PY
echo "PUBLIC_WORKER_ID: $(cat "$worker_id_file")"

# The installer is not permitted to overwrite an unknown probe script.
if [[ -e "$probe" ]] && ! grep -Fq 'Proof of isolated worker-owned systemd credential' "$probe"; then
 die "Existing unrelated probe file; refusing to overwrite"
fi
cat >"$probe" <<'PY'
"""Proof of isolated worker-owned systemd credential. Never prints secrets."""
import os, subprocess, tempfile
from pathlib import Path
cred_dir=os.environ.get("CREDENTIALS_DIRECTORY","")
if not cred_dir: raise SystemExit("BLOCK: SYSTEMD_CREDENTIALS_DIRECTORY_MISSING")
private=Path(cred_dir)/"worker_ed25519"
public=Path("/etc/optionx-v79/worker_ed25519.public.pem")
if not private.is_file() or not public.is_file(): raise SystemExit("BLOCK: SYSTEMD_CREDENTIAL_NOT_MOUNTED")
if os.geteuid()==0: raise SystemExit("BLOCK: EXECUTOR_ROOT_NOT_ALLOWED")
with tempfile.TemporaryDirectory(prefix="optionx-v79-") as d:
 challenge=Path(d)/"challenge"
 signature=Path(d)/"signature"
 challenge.write_bytes(os.urandom(32))
 sign=subprocess.run(["/usr/bin/openssl","pkeyutl","-sign","-rawin","-inkey",str(private),"-in",str(challenge),"-out",str(signature)],capture_output=True)
 if sign.returncode: raise SystemExit("BLOCK: ED25519_SIGN_FAILED")
 check=subprocess.run(["/usr/bin/openssl","pkeyutl","-verify","-rawin","-pubin","-inkey",str(public),"-in",str(challenge),"-sigfile",str(signature)],capture_output=True)
 if check.returncode: raise SystemExit("BLOCK: ED25519_VERIFY_FAILED")
print("PASS: V79_ISOLATED_WORKER_ED25519_SIGN_VERIFY")
print("PRIVATE_KEY_NOT_PRINTED OR_EXPORTED")
print("NO_BROKER_NO_DB_NO_ORDERS")
PY
chown root:root "$probe"
chmod 0644 "$probe"
python3 -B -m py_compile "$probe"
unit="optionx-v79-sign-probe-$$"
systemd-run --wait --collect --pipe --unit="$unit" \
 --property=User=optionx-executor \
 --property=Group=optionx-executor \
 --property=LoadCredential="worker_ed25519:$private" \
 --property=PrivateNetwork=yes \
 --property=IPAddressDeny=any \
 --property=NoNewPrivileges=yes \
 --property=PrivateTmp=yes \
 --property=PrivateDevices=yes \
 --property=ProtectSystem=strict \
 --property=ProtectHome=yes \
 --property=CapabilityBoundingSet= \
 /usr/bin/python3 -I -B "$probe" || die "Systemd credential proof failed"
for s in optionx-market-api optionx-owner-receiver optionx-paper-health-watchdog optionx-v54-paper-worker optionx-v58-recovery-observer; do
 systemctl is-active --quiet "$s" || die "Production service changed state"
done
echo "PASS: FIVE_ORIGINAL_SERVICES_STILL_ACTIVE"
echo "PASS: ISOLATED_WORKER_CREDENTIALS_PRESENT_ON_AWS"
echo "POSTGRES_ROLE_REMAINS_NOLOGIN; WORKER_DB_BINDING_NOT_YET_APPROVED"
echo "PUBLIC_KEY_FINGERPRINT_SHA256:"
openssl pkey -pubin -in "$public" -outform DER 2>/dev/null | sha256sum | cut -d' ' -f1
echo "V79_AWS_ED25519_IDENTITY_PREP_COMPLETE"
