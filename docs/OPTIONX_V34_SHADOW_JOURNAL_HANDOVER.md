# OPTIONX V34 — offline shadow journal checkpoint, 26 Nov 2026

## Prior evidence
V30 owner authenticated quote/position PASS; V31 AWS 18 tests PASS; V32 AWS 19 tests + FULL quote PASS; V33 evidence ledger committed. Angel One written order entitlement/LPP/fees request was sent by owner; response remains pending. Do not infer broker approval.

## V34 implementation
- `live_v7/shadow_journal_v34.py`: local **simulation-only** SQLite journal; no broker access, no Supabase, no API credentials, no live worker.
- `live_v7/test_shadow_journal_v34.py`: 18 offline mock tests.
- Owner scoped hashed UUID + idempotency key, immutable preapproved fixture draft; duplicate requests do not create new records.
- Strict simulated transitions DRAFT -> SIMULATED_SEND_UNKNOWN or SIMULATED_ACK or REVIEW_REQUIRED; unknown outcome cannot be retried; after process restart recovery requires independent reconciliation.
- This intentionally cannot simulate broker-confirmed fill, actual fees or exchange native stop. No real worker send path or certified production durable intent.
- Database may be created only by a test caller in an explicitly chosen local path. Does not touch the existing `optionx_private` Supabase tables or STOPPED guard.

## AWS test
AWS main checkout is root-owned and cannot be used with unsudoed Git. Use isolated worktree:
```bash
bash -c '
set -e
REPO=/opt/optionx-v7
DIR=/opt/optionx-v7-shadow-v34
sudo git -C "$REPO" fetch --no-tags origin refs/heads/optionx-v34-durable-shadow-journal-20261126
if [ ! -e "$DIR" ]; then
  sudo git -C "$REPO" worktree add --detach "$DIR" FETCH_HEAD
fi
test "$(sudo git -C "$DIR" rev-parse HEAD)" = "$(sudo git -C "$REPO" rev-parse FETCH_HEAD)"
cd "$DIR"
python3 -B -m unittest live_v7.test_shadow_journal_v34 -v
echo V34_AWS_OFFLINE_TEST_COMPLETE
'
```
No real broker login is needed and no real order can be submitted.

## Non-negotiable
No real SELL / STOP / BUY / CANCEL; manual position not adopted. Existing source lock in `angel_execution_transport.py` and production Supabase STOPPED engine guard retained. A separate broker authorization, complete recovery certification and **fresh exact-order user approval** are required before even considering separately reviewed live execution.
