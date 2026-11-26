# OptionX V43 — durable pre-send intent prototype

Date: 26 November 2026 IST.

## Confirmed prerequisites
Owner shared V42 AWS offline: 17/17 PASS. V41 authenticated Angel read-only: PASS, including positions, orderbook, manual 65-unit contract match and FULL quote freshness at the time. Angel approval email provided by owner asserts Technical/Compliance permission; real broker execution remains unproven. User accepts financial trading risk and requests live rollout, but has not approved a fresh, fully specified exact order.

## What this version actually implements
- `live_v7/durable_intent_v43.py` private SQLite (0700 directory, 0600 file, synchronous FULL, DELETE journal) durable *pre-send intent* prototype.
- Uniqueness: (hashed owner UUID, idempotency key). Strict fixed manual NIFTY draft: 65 SELL LIMIT 10.50. This is a TEST FIXTURE, never authority to sell the current manual position.
- State: RESERVED_UNSENT -> MAY_HAVE_SENT_RECONCILE. Sealing unknown before a hypothetical future send is irreversible via this API and survives restarts. No dispatch, no automatic retry, no cancel.
- Crash/reopen and idempotency tests, owner scope, file permissions, allowlisted fields. 16 local unit tests in `live_v7/test_durable_intent_v43.py`.

## Important limitations
- This is **NOT** a certified production journal or execution worker; no production database write, live broker route, secret storage, automated order or source-lock change.
- SQLite on one host is not a replacement for independently audited multi-worker PostgreSQL reservation/guard with backups, fenced worker ownership, broker order ACK/tradebook reconciliation, partial fills and monitored kill-switch.
- The real Supabase STOPPED guard and transport source lock remain intact. A real BUY/SELL cannot be sent via this version; no live permission claim or owner general risk acceptance overrides that.
- Historic V41 quote is not a current executable bid, and LIMIT 10.50 doesn't guarantee execution or bound realized loss.

## AWS offline validation
```bash
bash -c '
set -e
REPO=/opt/optionx-v7
DIR=/opt/optionx-v7-intent-v43
sudo git -C "$REPO" fetch --no-tags origin refs/heads/optionx-v43-durable-execution-intent-20261126
if [ ! -e "$DIR" ]; then sudo git -C "$REPO" worktree add --detach "$DIR" FETCH_HEAD; fi
test "$(sudo git -C "$DIR" rev-parse HEAD)" = "$(sudo git -C "$REPO" rev-parse FETCH_HEAD)"
cd "$DIR"
python3 -B -m unittest live_v7.test_durable_intent_v43 -q
echo V43_AWS_OFFLINE_TEST_COMPLETE
'
```
No broker login, real order, database migration, service change or restart.

## Specific next engineering steps toward live
1. Replace local fixture with validated immutable broker order intent tied to exact current verified position; prevent automated adoption of manual account exposure.
2. Build and review transactional PostgreSQL writer on dedicated least-privilege role in isolated staging (NOT current production DB); anti-duplicate/worker crash/network ACK reconciliation via broker confirmed IDs.
3. Independent integration tests for partial fills and stop/reject/unknown ACK on broker-approved mock or explicitly bounded safe environment.
4. Final exact-order authorization, quote, charges, LPP risk, live account permission and kill-switch signoff. Do not send even a passive SELL just for connectivity.
