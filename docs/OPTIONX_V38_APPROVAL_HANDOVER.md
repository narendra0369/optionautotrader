# OptionX V38 — Approval provenance & expiration checkpoint
Date: 2026-11-26 IST

## Prior verified outputs
V36 mock reconciliation: 20/20 tests PASS on owner's AWS Ubuntu. V34/V35: 36/36 AWS PASS. Latest owner-supplied Angel One message states application details reviewed, but actual execution authorization is expressly conditional on technical AND compliance team final confirmation. Do NOT infer either team's final approval.

## New code
- `live_v7/approval_provenance_v38.py`: pure offline documentary evidence classifier for separately asserted technical approval, compliance approval, Trading API entitlement, retail algo undertaking, static-IP app approval.
- `live_v7/test_approval_provenance_v38.py`: 18 local tests covering CONDITIONAL, PENDING, REVOKED, expired, app-mismatched, unsupported source, missing dates, naive timezone, future dates and no-order invariants.
- Evidence is never independently authenticated by this local module, even if all 5 caller assertions say APPROVED.
- No order transport, no network, no database or live service deployment; cannot lift source lock or STOPPED guard. No real SELL, BUY, STOP, cancel or automatic LPP retry.
- Previous manual position is not adopted and remains the owner's. V30/V32 snapshots are historic, not live.

## AWS isolated worktree test
```bash
bash -c '
set -e
REPO=/opt/optionx-v7
DIR=/opt/optionx-v7-approval-v38
sudo git -C "$REPO" fetch --no-tags origin refs/heads/optionx-v38-approval-provenance-20261126
if [ ! -e "$DIR" ]; then
  sudo git -C "$REPO" worktree add --detach "$DIR" FETCH_HEAD
fi
test "$(sudo git -C "$DIR" rev-parse HEAD)" = "$(sudo git -C "$REPO" rev-parse FETCH_HEAD)"
cd "$DIR"
python3 -B -m unittest live_v7.test_approval_provenance_v38 -v
echo V38_AWS_OFFLINE_TEST_COMPLETE
'
```

## Outstanding live blockers
Final broker technical/compliance permission and account-specific Trading API entitlement, accurate F&O/producttype/undertaking and algo tagging, dynamic LPP uncertainty, actual broker fees, genuine durable production send journal and crash recovery certification, fresh owner-authenticated broker orders/trades/positions and new independent exact-order-specific owner authorization. None is solved by passing V38 mocks. Real orders stay OFF.
