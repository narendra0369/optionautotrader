#!/usr/bin/env bash
# V94 AWS source/test/deployment readiness, NO live order execution.
set -Eeuo pipefail
umask 077
REPO="${OPTIONX_REPO:-/opt/optionx-v52}"
BRANCH=optionx-v94-aws-gate-preflight-20261127
fail(){ printf 'BLOCK: %s\n' "$*" >&2; exit 1; }
[[ -d "$REPO/.git" ]] || fail "SOURCE_REPOSITORY_NOT_FOUND"
command -v git >/dev/null || fail "GIT_REQUIRED"
command -v python3 >/dev/null || fail "PYTHON_REQUIRED"
for s in optionx-market-api optionx-owner-receiver optionx-v78-executor-staging; do
 if systemctl is-active --quiet "$s"; then
  printf 'SERVICE_%s: ACTIVE\n' "$s"
 else
  printf 'SERVICE_%s: NOT_ACTIVE\n' "$s"
 fi
done
tmp=$(mktemp -d)
trap 'rm -rf "$tmp"' EXIT
sudo git -c safe.directory="$REPO" -C "$REPO" fetch --no-tags origin "$BRANCH"
sudo git -c safe.directory="$REPO" -C "$REPO" archive FETCH_HEAD | tar -x -C "$tmp"
cd "$tmp"
python3 -m unittest discover -s tests -p 'test_optionx_v93_guarded_sl_worker.py' -v
python3 -m unittest discover -s tests -p 'test_optionx_v94_position_product.py' -v
python3 -m py_compile live_v7/angel_sl_transport_v93.py live_v7/angel_sl_guarded_worker_v93.py live_v7/angel_position_product_v94.py
printf '%s\n' 'V94_SOURCE_SAFETY_TESTS: PASS'
printf '%s\n' 'WORKER_INSTALLATION: NOT_ATTEMPTED'
printf '%s\n' 'PRODUCTION_GATE: NOT_MODIFIED'
printf '%s\n' 'BROKER_ORDER_SENT: NO'
printf '%s\n' 'V94_AWS_PREFLIGHT_COMPLETE'
