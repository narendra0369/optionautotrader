# OPTIONX V36 Recovery Reconciliation — Handover (26 November 2026)

## Verified before V36
V30 authenticated AWS read-only manual position PASS; V31 18/18 AWS offline PASS; V32 19/19 AWS offline and authenticated FULL quote PASS; V33 evidence ledger drafted; V34/V35 combined 36 AWS offline tests PASS, according to owner-supplied AWS output. Angel One support reply provided by owner, but account Trading API entitlement, undertaking completion, fees and dynamic LPP remain unverified.

## V36 changes
- `live_v7/shadow_recovery_v36.py`: PURE offline shadow reconciliation of caller-supplied normalized positions/orders/trades, shadow lifecycle state, snapshot freshness and owner verification flags. ALWAYS blocks all order send, retry and cancel.
- `live_v7/test_shadow_recovery_v36.py`: 20 mock tests for duplicate IDs, conflicting SELL, stale/unknown orders, unknown simulated outcome, fake ACK, mismatched fills, position changes and manual isolation.
- These normalized mock rows are **not** independently authenticated broker data. V36 is not a live worker, production journal or broker certification. Existing Supabase engine STOPPED guard and source-locked execution transport remain unchanged.
- Existing manual NIFTY position must not be adopted from symbol matching; state reconciliation without broker-side confirmed identities is incomplete.

## AWS tests (isolated, no broker credentials or service restart)
Use SSH Ubuntu:
```bash
bash -c '
set -e
REPO=/opt/optionx-v7
DIR=/opt/optionx-v7-recovery-v36
sudo git -C "$REPO" fetch --no-tags origin refs/heads/optionx-v36-recovery-reconciliation-20261126
if [ ! -e "$DIR" ]; then sudo git -C "$REPO" worktree add --detach "$DIR" FETCH_HEAD; fi
test "$(sudo git -C "$DIR" rev-parse HEAD)" = "$(sudo git -C "$REPO" rev-parse FETCH_HEAD)"
cd "$DIR"
python3 -B -m unittest live_v7.test_shadow_recovery_v36 -v
echo V36_AWS_OFFLINE_TEST_COMPLETE
'
```

## What is still missing
This V36 test cannot authorize any live orders. Must independently certify the dedicated production persistent pre-send intent journal/role/schema, broker-owner reauthentication, known/unknown acknowledgement reconciliation against actual broker books, production crash recovery, account-specific entitlement, undertaking, dynamic LPP and fees. The current STOPPED guard and source lock must not be bypassed. The owner's separate final explicit approval must identify exact order type, contract, quantity, price, risk and relevant live position after all checks; no such approval exists.

No real BUY/SELL/STOP or cancel and no auto retry of LPP error 17070.
