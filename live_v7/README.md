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


## V7 continued development (2026-11-24)

Files added in this continued stage:
- broker_readonly.py: fixed, allowlisted **GET-only** read-route catalog;
  strict Angel NFO orderbook/position response normalization, unknown-status
  blocking, and Delta read-only response shape check. No HTTP client here.
- kill_switch.py: stopped-by-default emergency-stop and reset-request
  state machine; no enabled/running state can be produced.
- audit_chain.py: minimum-data HMAC audit event structure, chained digests,
  and a verifier sketch. This is not an independently anchored audit log
  until a durable store and a protected server key are integrated.

IMPORTANT: The existing OptionX V6 services still run their original branch.
The V7 files are standalone development drafts and have no live API
integration, network client, order methods or live permissions.

### Read-only integration mapping (not yet activated)

Angel One official Python SDK routes: account positions, order book,
trade book, and funds/RMS are GET endpoints. Only these are listed.
Delta India exposes read-only private positions and orders endpoints.
No private credential was read or copied into GitHub, no remote
broker call was made, and no order was placed.

### Pending after testing is authorized

1. Confirm raw broker schemas from a read-only verified session, then
   normalize full/partial fills, positions, cost/margin and account identity.
2. Make a durable per-owner kill switch and append-only audit store with RLS,
   concurrency protection and an independent HMAC head anchor.
3. Add authenticated server-only transport, credentials vault and trusted
   provenance; do not accept browser-supplied readiness booleans.
4. Run isolated unit and integration tests, outage/partial-fill recovery and
   a supervised paper/shadow trading period.
5. Check the registered static outbound IP and applicable exchange/broker
   algorithmic-trading conditions before designing real execution.
6. Only after tests and separate explicit owner approval, evaluate whether
   broker order placement can safely be enabled.

Status: **SOURCE DRAFTS WRITTEN; TESTS NOT RUN; NO PRODUCTION DEPLOY**.


## Continued build: integrated source-only V7 preparation (2026-11-24)

The following were also committed to this isolated branch **without testing**
and **without a production deploy**:

- contracts.py: exact Decimal lot/tick/multiplier, provenance and quote checks.
  Delta perpetual futures require explicit verified no-expiry status.
- angel_master.py: broker-published NFO contract candidate filtering.
  Does NOT assume tick/strike scale or invent available contracts.
- read_only_transport.py: restricted GET-only HTTPS Angel and Delta account
  transport, disabled by default, with no redirects or arbitrary hosts.
- read_only_bridge.py: broker-profile-matched 15-minute Angel RAM session
  bridge for server-only Order Book and Positions reads, behind default OFF.
- ledger_store.py: transactional, idempotent **shadow-preview** ledger writer.
  The matching private Postgres schema is a draft only and NOT installed.
- protective_exit.py: stop/target coverage and broker-acknowledgement
  validation *plans*, not actual broker stop orders.
- risk_policy.py: existing stepped paper lots retained, no silent live
  conversion. Live budget and lot size require separate approval.
- secret_vault.py: deliberately locked vault interface; actual encrypted
  vault/KMS provider not installed and no credential values stored.
- readiness.py, market_api.py and live_ui.mjs/index.html: versioned,
  owner-authenticated, non-executing readiness display. The deployed V6
  website is not changed.
- test_future_safety.py: future offline tests written but **NOT RUN**.
- private_ledger_schema_draft.sql: private Supabase ownership, journal,
  protection, risk, audit and kill-switch tables; **NOT APPLIED**.
- RELEASE_GATES.md: detailed remaining prerequisites and release controls.

Current release status:
- Existing V6 live-order gateway: hard locked.
- V7 live-order implementation: intentionally absent.
- V7 source: saved to GitHub development branch.
- Broker logins, real orders, and live trading: not started here.
- Tests: deferred at the user's request.
- Render/Supabase production: unchanged by these V7 commits.

See RELEASE_GATES.md for remaining actions requiring verified infrastructure,
broker permissions, account approval and later tests. The current read-only
market feed is not an execution-grade Angel NFO/Delta order source.
