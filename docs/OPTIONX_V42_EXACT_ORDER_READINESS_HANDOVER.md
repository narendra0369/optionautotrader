# OPTIONX V42 exact-order safety contract — 26 November 2026

## State before V42
Owner explicitly accepts financial trading risk and generally requests live orders. Angel One Technical & Compliance email presented by owner asserts live activation; receipt/authenticity and actual account-specific trade permission have not been independently verified. The authenticated read-only V41 observation PASS: login, positions, orders, exact manual long position, quote, freshness; it did NOT send an order or certify production execution. Historical position NIFTY29DEC2629000CE token 38158 quantity 65, but that observation expires and must not be used as current tradable exposure. The owner's general risk acceptance is **not** exact-order consent.

## What V42 adds
`live_v7/exact_order_readiness_v42.py` is PURE offline, with no network, broker SDK, DB or live order transport. It documents separate fail-closed blockers for order intent identity and order types, exact quantity versus fresh account exposure, producttype, tick, active/unknown SELL, position/trade/order book freshness, quote freshness, LPP uncertainty, fees, technical/compliance approval, trading entitlement, durable pre-send intent and unknown-response recovery, and exact-order user consent.

`live_v7/test_exact_order_readiness_v42.py` contains 17 offline tests. Even if caller-supplied flags falsely say all prerequisites PASS, result cannot authorize an order. A production implementation requires independently authenticated and durable evidence and separate source lock release review.

No production service deployment, no Supabase write, no unlocking of `live_v7/angel_execution_transport.py`, no automatic order retries, and manual position untouched.

## AWS offline test
```bash
bash -c '
set -e
REPO=/opt/optionx-v7
DIR=/opt/optionx-v7-safety-v42
sudo git -C "$REPO" fetch --no-tags origin refs/heads/optionx-v42-live-order-recovery-contract-20261126
if [ ! -e "$DIR" ]; then
  sudo git -C "$REPO" worktree add --detach "$DIR" FETCH_HEAD
fi
test "$(sudo git -C "$DIR" rev-parse HEAD)" = "$(sudo git -C "$REPO" rev-parse FETCH_HEAD)"
cd "$DIR"
python3 -B -m unittest live_v7.test_exact_order_readiness_v42 -q
echo V42_AWS_OFFLINE_TEST_COMPLETE
'
```

Passing mocks is NOT certification. Before any real SELL, additional design/development and certification needed: reliable durable production pre-send journal, restart and ambiguous ACK broker reconciliation, collision exclusion for manual positions, validated fees and fresh quote/books, plus the user's explicit approval of the exact SELL (symbol, token, producttype, quantity, LIMIT price or STOPLOSS_LIMIT trigger/limit, duration, budget). Do not infer from a quoted live approval email that these checks were performed.
