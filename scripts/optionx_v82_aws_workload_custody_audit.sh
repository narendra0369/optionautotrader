#!/usr/bin/env bash
# V82 host read-only provenance inventory. Not an independent attestation.
set -u
echo "=== OPTIONX V82 AWS READ-ONLY WORKLOAD CUSTODY AUDIT ==="
bad=0
good(){ printf 'PASS: %s\n' "$1"; }
block(){ printf 'BLOCK: %s\n' "$1";bad=1; }
if id optionx-executor >/dev/null 2>&1;then
  shell="$(getent passwd optionx-executor|cut -d: -f7)"
  [[ "$shell" == /usr/sbin/nologin ]] && good EXECUTOR_NONLOGIN || block EXECUTOR_LOGIN_SHELL
  groups="$(id -nG optionx-executor)"
  [[ "$groups" == optionx-executor ]] && good EXECUTOR_SINGLE_GROUP || block EXECUTOR_UNEXPECTED_GROUPS
else block EXECUTOR_MISSING;fi
key=/etc/optionx-v79/worker_ed25519.key
pub=/etc/optionx-v79/worker_ed25519.public.pem
if [[ -f "$key" && ! -L "$key" ]]; then
  [[ "$(stat -c %U "$key")" == root ]] && good PRIVATE_KEY_ROOT_OWNED || block PRIVATE_KEY_NOT_ROOT_OWNED
  [[ "$(stat -c %a "$key")" == 600 ]] && good PRIVATE_KEY_SOURCE_MODE_600 || block PRIVATE_KEY_SOURCE_PERMISSIONS
  if [[ "$(id -u)" -eq 0 ]] && command -v runuser >/dev/null; then
    runuser -u optionx-executor -- test -r "$key" && block EXECUTOR_CAN_DIRECTLY_READ_SOURCE_KEY || good EXECUTOR_CANNOT_DIRECTLY_READ_SOURCE_KEY
    runuser -u optionx -- test -r "$key" && block ORIGINAL_SERVICE_USER_CAN_READ_PRIVATE_KEY || good ORIGINAL_SERVICE_USER_CANNOT_READ_PRIVATE_KEY
  else echo "INFO: SUDO_REQUIRED_FOR_NEGATIVE_READ_TEST";fi
else block PRIVATE_KEY_MISSING_OR_SYMLINK;fi
if [[ -f "$pub" && ! -L "$pub" ]]; then
 fp="$(openssl pkey -pubin -in "$pub" -outform DER 2>/dev/null|sha256sum|cut -d' ' -f1)"
 [[ "$fp" == 94fc2e18d81cd126b34a21261d542b06c918649f388cb553c1e051f4dcf1a4d6 ]] && good PUBLIC_KEY_FINGERPRINT_MATCH || block PUBLIC_KEY_FINGERPRINT_MISMATCH
else block PUBLIC_KEY_MISSING_OR_SYMLINK;fi
for svc in optionx-market-api optionx-owner-receiver optionx-paper-health-watchdog optionx-v54-paper-worker optionx-v58-recovery-observer optionx-v78-executor-staging; do
 if systemctl is-active --quiet "$svc";then good "ACTIVE_$svc"; else block "INACTIVE_$svc"; fi
done
for prop in User Group PrivateNetwork IPAddressDeny NoNewPrivileges ProtectSystem ProtectHome; do
 val="$(systemctl show optionx-v78-executor-staging -p "$prop" --value 2>/dev/null || true)"
 case "$prop" in
  User|Group) [[ "$val" == optionx-executor ]] && good "STAGING_$prop" || block "STAGING_$prop" ;;
  PrivateNetwork|NoNewPrivileges) [[ "$val" == yes ]] && good "STAGING_$prop" || block "STAGING_$prop" ;;
  ProtectSystem) [[ "$val" == strict ]] && good "STAGING_$prop" || block "STAGING_$prop" ;;
  ProtectHome) [[ "$val" == yes ]] && good "STAGING_$prop" || block "STAGING_$prop" ;;
  IPAddressDeny) [[ "$val" == *0.0.0.0/0* && "$val" == *::/0* ]] && good "STAGING_$prop" || block "STAGING_$prop" ;;
 esac
done
echo "INFO: LOCAL_SELF_REPORTED_AUDIT_NOT_INDEPENDENT_ATTESTATION"
echo "INFO: NO_RESTART_NO_SECRET_EXPORT_NO_DB_WRITES_NO_ORDERS"
if [[ "$bad" -eq 0 ]];then echo V82_HOST_READ_ONLY_AUDIT_PASS;else echo V82_HOST_READ_ONLY_AUDIT_BLOCKED;fi
exit "$bad"
