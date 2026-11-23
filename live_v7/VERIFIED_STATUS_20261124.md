# OPTIONX V7 — Verified Release Status (24 Nov 2026, IST)

This is a factual snapshot of work completed as of this commit, not an
authorization to perform real-money trading.

## Confirmed completed

- GitHub: V7 isolated branch optionx-live-prep-v7-20261124.
- GitHub: draft pull request #1 targeting the existing V6 production branch.
- V7 backend staging Render service: optionx-v7-offline-test-staging.
- V7 frontend staging Render service: optionx-v7-frontend-test-staging.
- Render backend staging: 73 offline tests passed, 0 failures, build successful
  on commit 7a2f3a37bc337c90973067d754627a1d0f8c1afe, deployment LIVE.
- Render frontend staging: Node syntax checks and deterministic chart, 200k
  strategy, paper engine and broker UI tests PASSED; deployment LIVE.
- Regression coverage includes contract multipliers, currency consistency,
  broker quote token matching, immutable live lock, stop acknowledgements,
  partial fills, unknown broker results, order replay, app restarts and
  duplicate event prevention.
- V7 staging UI routes owner-bound broker status requests to V7 staging API.
  Production host continues using the V6 production API.
- V7 staging CORS is opt-in; read-only private inspection and all
  real-order execution still disabled.
- Production V6 backup branch exists:
  optionx-v6-backup-before-modules-fix-20261124.
- The production V6 services remain independent of the V7 staged branch.

## Clarification on static asset packaging

The Render static-site build command omits paper_ui.mjs / live_ui.mjs in its
literal cp invocation, **but tests.mjs already copies these required modules
into dist/** during the build. Therefore these files were not proven missing
from the published site. Temporary redundant tracked copies were removed.
No production functional outage is inferred from the build command alone.

## Still NOT complete

1. Angel One registered static outbound IPv4 and authorization for client API
   order execution. This cannot be inferred from login or outbound-IP lookup.
   See https://smartapi.angelbroking.com/exchange-regulations
2. Delta India separately authenticated, authorized API connection and IP
   whitelisting. No broker secret or token has been requested in chat.
   See https://docs.delta.exchange/
3. Production-grade verified contract master / live bid-ask / broker margin /
   broker order, trade and position reconciliation. Research/index candles
   cannot substitute for tradable option premiums.
4. Encrypted credentials vault and trusted egress host. The V7 LockedVault
   intentionally refuses to load or store private brokerage secrets.
5. Durable V7 ledger in a private, authenticated database. SQL draft is
   committed but **not applied** to the existing shared Supabase instance.
   No dev database branch exists. V7 staging tests use SQLite/mock data.
6. End-to-end broker-assisted sandbox or controlled order lifecycle, including
   rejected orders, partial fills, native SL/Target/OCO, cancel/modify, market
   gap and broker disconnection. Offline emulation alone is insufficient.
7. Final explicit live-capital sizing/charges/risk authorization and a real
   money execution implementation after all prerequisites are satisfied.

## Status contract

- Production real-money order execution: **OFF**.
- V7 test backend: **ONLINE, RESEARCH / READINESS ONLY**.
- V7 test frontend: **ONLINE, RESEARCH / READINESS ONLY**.
- Live buy/sell order transport: **NOT IMPLEMENTED OR AUTHORIZED**.
- Do not merge the V7 draft PR solely because offline tests passed.
- Do not set a 'live enabled' flag, paste brokerage credentials into chat,
  or copy the paper 30k/40k-step lot sizing directly to real contracts.

## Only after external prerequisites

Register the correct dedicated static IPv4 with Angel One (and Delta as
required), verify algo eligibility and API scopes in broker portal, choose
a vetted server-only KMS and trading egress, prepare a backup and separate
Supabase staging DB, then test real broker orderbook/positions read-only.
Only after broker approval, risk review, end-to-end controlled testing and
independent owner opt-in should executable order methods be considered.
