# OptionX V49 — Integrated stopped-mode broker lifecycle worker

Owner confirms V48 AWS offline 33/33 PASS and asks to complete production trading worker + broker lifecycle integration. This release implements a **real integration test harness**, *not a broker-enabled worker*.

## Implemented and scoped
- `live_v7/lifecycle_worker_v49.py`: one-shot synthetic order worker integrating:
  - V47 persistent STOP/readiness control, never arms.
  - V43 SQLite durable intent reservation + uncertain-send seal committed BEFORE synthetic broker invocation.
  - V44 broker order/tradebook consistency checker: exact order ID, token, side, producttype, partial fills, cancelled/rejected/complete and unknown states.
  - explicit `mock_only=True` gateway contract; never imports or calls Angel order transport.
- `live_v7/test_lifecycle_worker_v49.py`: 20 offline tests including restart, duplicate, complete, partial, rejected, cancelled, unknown, simulated timeout, owner STOP, absence of live source unlock.
- All outcomes `canSubmitOrder=False`, `liveOrdersEnabled=False`, `brokerOrdersSent=0` (meaning **real** sends; synthetic gateway invocation count is tracked only by the mock). No automatic re-send on restored durable intent.

## Remaining before ANY real-money order
1. Real, independent PostgreSQL staging database and ACTUAL transaction/concurrency certification: V45 uses only in-memory fake DB tests and is NOT integrated into V49, which still relies on SQLite V43. Build audited production DB schema, credentials and backups; state remains STOPPED.
2. An independently reviewed, production broker order writer for exact broker account/contract/order type, under the actual registered static IP and broker algo authorization, with bounded one-lot owner-approved order.
3. Real broker API response/field schema verification and authenticated tradebook/orderbook lifecycle for this account; broker WRITE confirmation is not proven by read-only V41.
4. Proper ACK/timeout/partial-fill crash tests in broker-approved test environment, protective stop recovery (including SL-limit gaps/rejection), no automatic manual-position adoption and no OCO race.
5. Live authoritative kill-switch fencing, daily trade quota and charges/risk enforcement at write transaction time, manual exact-order confirmation.
6. The V48 Render-to-AWS HTTPS private relay and HMAC secrets are CODE ONLY; no TLS reverse proxy, staging service or deployment has been configured. Website dashboard does not control AWS worker yet.
7. Angel transport `live_v7/angel_execution_transport.py` unconditionally blocks real broker POST; DO NOT remove lock based on mocked tests.
8. Render plugin workspace remains unconfirmed for deployment; no deploy attempted. The existing live website and AWS service are unchanged.

## AWS offline validation (isolated worktree only)
```bash
bash <<'BASH'
set -e
echo "=== OPTIONX V49 MOCK BROKER LIFECYCLE TEST ==="
REPO=/opt/optionx-v7
DIR=/opt/optionx-v7-lifecycle-v49
sudo git -C "$REPO" fetch --no-tags origin refs/heads/optionx-v49-lifecycle-worker-integration-20261126
COMMIT=$(sudo git -C "$REPO" rev-parse FETCH_HEAD)
if [ ! -e "$DIR" ]; then
  sudo git -C "$REPO" worktree add --detach "$DIR" "$COMMIT"
else
  test -z "$(sudo git -C "$DIR" status --porcelain)" || { echo "BLOCKED_LOCAL_CHANGES"; exit 2; }
  sudo git -C "$DIR" checkout --detach "$COMMIT"
fi
cd "$DIR"
python3 -B -m unittest live_v7.test_lifecycle_worker_v49 -q
echo "=== V49_AWS_20_TESTS_COMPLETE ==="
BASH
```

No login, credentials, AWS/Render restart, production database migration or broker submit. Tests use temporary files and deterministic simulated book rows.
