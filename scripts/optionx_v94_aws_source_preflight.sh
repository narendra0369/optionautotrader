#!/usr/bin/env bash
# OPTIONX V94: run offline tests in the extracted GitHub source archive.
# NO service changes, NO broker calls, NO production-gate modifications.
set -Eeuo pipefail
umask 077
fail(){ printf 'BLOCK: %s\n' "$*" >&2; exit 1; }
command -v python3 >/dev/null || fail "PYTHON_REQUIRED"
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd -P)"
[[ -f "$ROOT/live_v7/angel_sl_guarded_worker_v93.py" ]] || fail "V93_WORKER_SOURCE_MISSING"
[[ -f "$ROOT/live_v7/angel_position_product_v94.py" ]] || fail "V94_PRODUCT_SOURCE_MISSING"
[[ -f "$ROOT/tests/test_optionx_v93_guarded_sl_worker.py" ]] || fail "V93_TEST_SOURCE_MISSING"
[[ -f "$ROOT/tests/test_optionx_v94_position_product.py" ]] || fail "V94_TEST_SOURCE_MISSING"
for s in optionx-market-api optionx-owner-receiver optionx-v78-executor-staging; do
 if command -v systemctl >/dev/null && systemctl is-active --quiet "$s"; then
  printf 'SERVICE_%s: ACTIVE\n' "$s"
 else
  printf 'SERVICE_%s: NOT_ACTIVE_OR_UNAVAILABLE\n' "$s"
 fi
done
cd "$ROOT"
PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s tests -p 'test_optionx_v93_guarded_sl_worker.py' -v
PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s tests -p 'test_optionx_v94_position_product.py' -v
PYTHONDONTWRITEBYTECODE=1 python3 - <<'PY'
from pathlib import Path
for name in (
    "live_v7/angel_sl_transport_v93.py",
    "live_v7/angel_sl_guarded_worker_v93.py",
    "live_v7/angel_position_product_v94.py",
):
    compile(Path(name).read_text(encoding="utf-8"),name,"exec")
print("WORKER_SOURCE_SYNTAX: PASS")
PY
printf '%s\n' 'V94_SOURCE_SAFETY_TESTS: PASS'
printf '%s\n' 'WORKER_INSTALLATION: NOT_ATTEMPTED'
printf '%s\n' 'PRODUCTION_GATE: NOT_MODIFIED'
printf '%s\n' 'BROKER_ORDER_SENT: NO'
printf '%s\n' 'V94_AWS_PREFLIGHT_COMPLETE'
