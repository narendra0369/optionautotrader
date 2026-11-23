# OptionX — Live Trading V7 Preparation (ISOLATED / UNTESTED)

Updated: 2026-11-24

## What this branch does

Branch: optionx-live-prep-v7-20261124
Base: optionx-200k-strategy-lab-20261123

This work is **preparation only**. It deliberately does **not** place or cancel
broker orders, does **not** toggle a production flag, and is **not deployed** to
the current OptionX Render services.

The owner explicitly deferred testing for now. Accordingly, no regression,
simulation, live-account, login, broker, or execution tests were run as part
of this development stage.

Files:
- intent_gate.py — pure broker/contract/quote/risk preflight with a permanent
  canSubmitOrder=false result. Includes exact decimal risk calculations,
  Indian-market session cutoff, quote staleness, daily-loss, two-trades-per-day
  hard cap, owner/static-IP/contract prerequisites.
- order_journal.py — local-only SQLite intent reservation and lifecycle
  state transitions, including uncertainty states that require reconciliation.
  For developer rehearsal only; NOT a cloud source of truth.
- reconciliation.py — read-only normalized broker/local order and position
  comparison. Missing orders, unmatched fills, unknown order states or stale
  snapshots block new entries.

**None of these files is an Angel One or Delta order adapter.**

## Requirements before genuine live enablement

1. Dedicated, owner-controlled **static outbound IPv4** registered with the
   chosen broker. The existing shared Render feed is not independently verified
   as an approved execution host. Do not spoof or infer header IPs.
2. Broker-specific approval for client-developed retail algos, as applicable;
   comply with exchange and Angel One / Delta India requirements.
3. Secure, encrypted broker credential/session vault; scoped broker account
   binding; sessions refreshed safely; NEVER put credentials in GitHub or logs.
4. Server-authenticated market quotes and live contract master (exact
   token/product ID, expiry, tick size, lot size, margin, trading status).
   Yahoo index and Kraken spot proxies are not tradable NFO/Delta contracts.
5. Broker adapter for read-only orderbook, tradebook, positions and margin.
   All results normalized with explicit unknown/error handling.
6. Durable, transactionally safe journal with per-order idempotency shared
   across processes and restarts, separate from Render ephemeral disk.
7. Correct order placement, acknowledgement, modification/cancellation, exit
   and STOP workflows. Unknown submission result must NOT trigger retry or
   new entry without broker reconciliation.
8. Strong account risk controls: capital-based lot sizing, stop loss, target,
   costs, liquidity, slippage, per-trade and per-day drawdown, session close,
   2-trade/day maximum, kill switch, no accidental naked short exposure.
   Preserve the existing stepped paper-capital model; DO NOT silently
   replace its thresholds. Confirm live account sizing before activation.
9. Unit, integration, historical replay, paper/live shadow, outage recovery,
   duplicate-replay, rejected-order, partial-fill, zero-fill, cancel,
   idempotency, broker-down and static-IP tests.
10. Separate, explicit owner approval to activate real trading **only after**
    all requirements and tests pass.

## Safe sequence for the next development pass (no testing yet)

- Wire authenticated read-only broker status/contract discovery from Angel
  One and Delta; add no order endpoint.
- Add persistent audit events and a kill-switch UI state, with server-side
  authorization and owner isolation.
- Add quote/contract provenance to backtest-to-live transitions; ensure
  strategy results are research, not executable orders.
- Implement broker-specific execution adapter as **not callable** until
  approvals, tests and final owner opt-in are complete.

## Trading limits and assumptions

Earlier research defaults: INR 300 per-trade risk, INR 600 daily stop, and
2 trades/day. These are **not guaranteed executable** for real option lot
sizes, slippage and fees. Preserve paper settings and confirm live limits
separately. Backtests on index OHLC cannot establish actual CE/PE P&L.

Sources:
- Angel One static IP retail API change:
  https://smartapi.angelbroking.com/exchange-regulations
- Angel One SmartAPI docs:
  https://smartapi.angelone.in/docs
- SEBI retail algo framework:
  https://www.sebi.gov.in/
