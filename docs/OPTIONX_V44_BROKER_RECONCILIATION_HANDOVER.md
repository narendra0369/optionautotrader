# OptionX V44 broker reconciliation handover — 26 Nov 2026

Owner confirmed V43 AWS 16/16 PASS. V41 Angel owner-bound read-only books and quote PASS on their observation. Owner requests progress toward real orders. This module is a strict book reconciliation evaluator, NOT a live worker.

Files:
- `live_v7/broker_reconciliation_v44.py` matches exact broker order ID, symbol, token, side, producttype, order quantity, status, aggregate trade quantities and unique IDs.
- `live_v7/test_broker_reconciliation_v44.py` 18 isolated unit tests on complete, partial, duplicate, stale, rejected, cancelled and unknown states.

**Mandatory limitation:** Broker field mappings for `fillshares`, `fillprice`, `tradeid`, `filledshares` and statuses are strict expectations only, *not* yet demonstrated with real Angel raw response schema for the owner's account. A read-only live normalized schema comparison is needed before production, without leaking raw account/trade data.
No broker POST, secret loading, source-lock removal, Supabase writes, production service restart, or manual 65-unit position modification. All canSubmitOrder/canRetry/canCancel flags remain False.

## AWS offline only
```bash
bash <<'BASH'
set -e
REPO=/opt/optionx-v7
DIR=/opt/optionx-v7-reconcile-v44
sudo git -C "$REPO" fetch --no-tags origin refs/heads/optionx-v44-reconciliation-engine-20261126
if [ ! -e "$DIR" ]; then
 sudo git -C "$REPO" worktree add --detach "$DIR" FETCH_HEAD
else
 test -z "$(sudo git -C "$DIR" status --porcelain)" || { echo "BLOCKED_LOCAL_CHANGES"; exit 2; }
 sudo git -C "$DIR" checkout --detach "$(sudo git -C "$REPO" rev-parse FETCH_HEAD)"
fi
cd "$DIR"
python3 -B -m unittest live_v7.test_broker_reconciliation_v44 -q
echo V44_AWS_18_TESTS_COMPLETE
BASH
```

Then next production work should build reviewed PostgreSQL dedicated worker fencing and immutable pre-send journal, test crash/ambiguous acknowledgements with mocked gateway and independent normalized broker snapshot. Real order-specific consent must name order price, quantity, side, producttype and current contract and be collected only after new quote and position verification; user general risk acceptance alone does not fix these variables.
