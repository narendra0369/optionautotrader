#!/usr/bin/env bash
# OPTIONX V77 - AWS read-only identity and stop-guard preflight.
# Run on original Lightsail Ubuntu host. No environment contents, no secrets,
# broker requests, database writes or production restarts.
set +e
printf '%s\n' '=== OPTIONX V77 REAL AWS IDENTITY PREFLIGHT ==='
if id optionx >/dev/null 2>&1; then
 printf 'PASS: SERVICE_ACCOUNT_EXISTS\n'
 id -u optionx | awk '{printf "SERVICE_ACCOUNT_UID: %s\n",$0}'
else printf 'BLOCK: SERVICE_ACCOUNT_MISSING\n'; fi
for svc in optionx-market-api optionx-owner-receiver optionx-paper-health-watchdog optionx-v54-paper-worker optionx-v58-recovery-observer; do
 printf '--- SERVICE: %s ---\n' "$svc"
 systemctl show "$svc" --no-pager --property=LoadState,ActiveState,User,Group,MainPID,NoNewPrivileges,ProtectSystem,PrivateTmp,RestrictSUIDSGID 2>/dev/null |
   sed -E '/^(Environment|ExecStart|FragmentPath|DropInPaths|EnvironmentFiles)=/d'
done
printf '%s\n' '--- CURRENT INSTANCE IAM ---'
if command -v aws >/dev/null 2>&1; then
 aws sts get-caller-identity --query 'Arn' --output text 2>/dev/null |
   sed -E 's#arn:aws:sts::[0-9]+:assumed-role/([^/]+)/.*#INSTANCE_ROLE_NAME: \1#'
else printf '%s\n' 'INFO: AWS_CLI_NOT_INSTALLED'; fi
printf '%s\n' '--- REQUIRED TRUST PROPERTIES ---'
printf '%s\n' 'NO_PROOF_YET: instance IAM role is not independent optionx process attestation'
printf '%s\n' 'NO_PROOF_YET: worker-to-PostgreSQL authenticated principal binding'
printf '%s\n' 'NO_PROOF_YET: worker secret vault/rotation and explicit operator-approved grants'
printf '%s\n' 'REQUIRED: maintain PostgreSQL optionx_execution_worker NOLOGIN until independent review'
printf '%s\n' 'REQUIRED: maintain STOP, real broker write/cancel disabled'
printf '%s\n' 'NO_DB_WRITES; NO_BROKER_REQUESTS; NO_SERVICE_RESTARTS'
printf '%s\n' 'V77_AWS_READ_ONLY_PREFLIGHT_COMPLETE'
