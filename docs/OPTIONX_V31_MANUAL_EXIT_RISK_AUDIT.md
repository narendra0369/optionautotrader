# OptionX V31 manual exit evidence audit — 26 Nov 2026

Source branch: `optionx-v31-broker-risk-audit-20261126`, branched from V30 `optionx-v30-manual-exit-worker-20261126`.

## Latest user-supplied AWS evidence
- V30 offline tests: 15 PASS
- V30 owner-authenticated read-only check: PASS, exit 0
- Contract NIFTY29DEC2629000CE / token 38158 / net quantity 65
- Proposed SELL LIMIT 10.50; owner-declared average entry 12.92; LTP snapshot 10.80
- Gross premium loss at limit excluding costs: INR 157.30
- V30 reported feed exchange timestamp and live bid NOT verified
- Order-write permission and fees NOT verified
- No real order submitted; REAL ORDERS OFF

This is historical evidence, never a current trade authorization. Limit SELL is **not** protective SL. Stop-limit is a different order type and can remain unfilled.

## New V31 modules
- `live_v7/manual_exit_risk_audit_v31.py`: pure risk/evidence calculator, no broker credentials, network, order calls, or order routes.
- `live_v7/test_manual_exit_risk_audit_v31.py`: 18 mock-only tests.
- It blocks on missing proof of current owner/position/orderbook, exchange feed timestamp, bid/ask, official tick and LPP, broker SELL LIMIT entitlement/fields, fees, live session, product type, journal/recovery and order-specific consent.
- Even all mocked green evidence keeps `canSubmitOrder=False` and `realOrdersEnabled=False` by design.
- V31 does **not** certify native STOPLOSS_LIMIT and does not enable automatic execution. Never interpret LTP alone as executable best bid or exchange tick/LPP.

## AWS verification (offline only)
Existing AWS Git main checkout is owned by root: use sudo for git and DO NOT change repo ownership, reset branches or restart services.

```bash
echo "=== OPTIONX V31 OFFLINE ONLY ==="
REPO=/opt/optionx-v7
DIR=/opt/optionx-v7-risk-v31
sudo git -C "$REPO" fetch --no-tags origin refs/heads/optionx-v31-broker-risk-audit-20261126 || return 1
if [ ! -e "$DIR" ]; then
  sudo git -C "$REPO" worktree add --detach "$DIR" FETCH_HEAD || return 1
fi
sudo git -C "$DIR" rev-parse HEAD
cd "$DIR" || return 1
python3 -B -m unittest live_v7.test_manual_exit_risk_audit_v31 -v
echo "V31_AWS_OFFLINE_TEST_COMPLETE"
```

After tests, obtain any broker/exchange entitlement, LPP, tick or live bid/ask evidence only via an independently reviewed read-only source; no source-lock removal or order send/cancel. V31 does not independently retrieve missing broker evidence.

## Non-negotiable
V30 manual position is not OptionX owned. Never auto-adopt, modify, cancel, or sell it. Existing `angel_execution_transport.py` source lock and database STOPPED guard must remain unchanged. An exact, order-specific fresh final user authorization is required **in addition to** full broker/write, risk, recovery and compliance certification. No old generic approval counts.
