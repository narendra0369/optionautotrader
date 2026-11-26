# OptionX V35 — Angel One response review and execution blockers
Date: 26 Nov 2026 IST

## Source supplied by owner
The owner pasted an email-style reply with subject "RE: SmartAPI NFO Order Permission and LPP Clarification" attributed to Team Angel One API. This file summarizes **what the pasted reply asserts**; it is not authentication of sender, original message headers or verification of the specific app/API key.

### Statements in reply
- Cross-channel manual position closure via SmartAPI permitted when open NFO position producttype matches and Trading API permissions are enabled. This is not authorization by the owner to place an order.
- NFO SELL STOPLOSS_LIMIT DAY with variety STOPLOSS and price/triggerprice is supported; normal SELL LIMIT uses variety NORMAL.
- Static whitelisted IPv4 required for order/modify/cancel/GTT calls.
- F&O segment, Trading API permission, tech-savvy retail undertaking and applicable algo tagging must be confirmed for this account.
- No exact pre-trade SmartAPI LPP bounds REST API claimed; exchange may reject out-of-range orders with code 17070.
- Reply offers brokerage/fees and suggests production or official mock testing; no real API execution authorized by this reply.
- Broker reply must not be interpreted as a guarantee of STOPLOSS_LIMIT fill or maximum loss.

### Independently checked published sources
- Angel One official access changes: https://smartapi.angelbroking.com/exchange-regulations
- NSE circular of 20 Nov 2026: https://nsearchives.nseindia.com/content/circulars/INSP77559.pdf
- NSE LPP FAQ and error 17070: https://www.nseindia.in/static/trade/limit-price-protection-faqs
- Angel One STT schedule: https://www.angelone.in/support/charges-and-cashbacks/stt-securities-transaction-tax

## Engineering decisions
1. Do not send even a passive LIMIT order and cancel it to test app permission; cancellation can fail and live order can fill.
2. On LPP rejection/17070, **no automatic adjust-and-resubmit**. On unknown network outcome, **never blindly retry**. Re-authenticate and reconcile independent current broker orderbook + tradebook + positions and request fresh authorization for a changed order.
3. No direct derivation of dynamic LPP from a quote. Best bid 10.85 from V32 was a historical transient observation, not a live executable guarantee.
4. Fee rates supplied in email are not automatically loaded into the trading engine. Verify actual plan, charges, full cost basis and taxes with broker ledger before computing loss.
5. Keep separate draft orders: V30 SELL LIMIT 10.50 vs V28/29 SELL STOPLOSS_LIMIT trigger 10.00 / limit 9.95. Never silently switch types or auto-adopt manual position.
6. V34 SQLite shadow journal remains simulated/offline; does not certify production order lifecycle or replace Supabase STOPPED guard.

## V35 source
- `live_v7/broker_reply_evidence_v35.py` is a **pure offline evidence checklist** and always returns canSubmitOrder=false.
- `live_v7/test_broker_reply_evidence_v35.py` has 18 regression tests. All asserted flags in a mock packet are still NOT independent broker attestation.

## AWS offline validation
Use isolated Git worktree from root-owned main repository:
```bash
bash -c '
set -e
REPO=/opt/optionx-v7
DIR=/opt/optionx-v7-reply-v35
sudo git -C "$REPO" fetch --no-tags origin refs/heads/optionx-v35-broker-reply-compliance-20261126
if [ ! -e "$DIR" ]; then
  sudo git -C "$REPO" worktree add --detach "$DIR" FETCH_HEAD
fi
test "$(sudo git -C "$DIR" rev-parse HEAD)" = "$(sudo git -C "$REPO" rev-parse FETCH_HEAD)"
cd "$DIR"
python3 -B -m unittest live_v7.test_broker_reply_evidence_v35 -v
echo V35_AWS_OFFLINE_TEST_COMPLETE
'
```

NO AWS service deployment, NO broker login/order modification or placing, NO guard removal; separate exact order-specific final authorization remains required.
