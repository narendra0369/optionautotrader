# OptionX V7 — Release gates and owner operations

**STATUS: DEVELOPMENT SOURCE ONLY / NO LIVE ORDERS / TESTING DEFERRED**

Architecture proposal:

1. OptionX frontend signs user in through existing Supabase Auth.
2. Backend independently validates the bearer token and configured personal
   owner ID; it does not trust browser-supplied authorization booleans.
3. A server-only encrypted vault (NOT YET INSTALLED) supplies short-lived
   broker credentials only to an authorized server process.
4. A fixed-origin, GET-only read adapter inspects Angel or Delta account data.
5. Server verifies contract master, quote/bid/ask, margin, per-trade/day risk,
   broker orderbook/positions, no unknown orders and emergency STOP.
6. A transaction-safe private Postgres journal retains intent IDs and lifecycle
   changes; audit events are chained and independently anchored.
7. An approved execution worker with registered static egress could **only
   later** submit orders after all legal, broker, infrastructure, regression,
   outage and recovery gates are confirmed and the owner separately approves.
8. Fill-confirmed broker-native stop/exit protection must be observable and
   reconciled. On unknown acknowledgements, halt additional entry and require
   manual reconciliation instead of blindly retrying an order.

## Implemented as non-executing V7 GitHub drafts

- intent_gate.py — block-on-unknown order eligibility
- contracts.py and angel_master.py — contract/token/lot/tick/expiry candidates
- read_only_transport.py and read_only_bridge.py — isolated owner-bound GET
  transport, disabled by default, no broker orders
- broker_readonly.py — GET route definitions and response normalizers
- protective_exit.py — verified stop/target need and acknowledgement planner
- order_journal.py and ledger_store.py — local lifecycle and private Postgres
  shadow-preview reservation; **not** a deployed live order store
- private_ledger_schema_draft.sql — private tables, ownership constraints,
  positions, risk, protection, audit, state. **NOT APPLIED**
- kill_switch.py — always STOPPED with no ON state
- audit_chain.py — tamper-evident event structure; external key and
  independent audit-head anchoring not configured
- risk_policy.py — paper tier model preserved; real live budget not inferred
- secret_vault.py — locked interface only; no credentials stored or read
- readiness.py + development-only market_api.py route and live UI panel
- test_future_safety.py — prospective offline tests authored but **NOT RUN**

## Things not completed and why

- **Registered static IP:** No verified static outbound IPv4 owned by the
  user has been supplied or registered in Angel One. Existing Render free
  market-feed instance is not an approved execution host.
- **Broker approvals:** NSE/SEBI retail algo and Angel authorization,
  applicable tagging/registration and exchange approval are not verified.
- **Delta session:** No Delta India private account connection or compliant
  secret vault. Delta requires API key/secret and IP-whitelist; private
  orders/positions endpoints may require Trading permission even for GET.
- **Actual contract quote and fill:** A public Angel master or BTC derivatives
  listing is not sufficient to verify fresh executable prices, margin or fills.
- **Broker-native exits:** Order placement, modification, cancellation, stop,
  target, reject/partial-fill recovery, web socket reconnection, duplicate
  prevention and gap protection are not executed or tested.
- **Database durability:** SQL schema has not been applied, or reconciled
  against existing production tables. Shadow ledger is not persistent yet.
- **Live capital rules:** Existing paper tier model is retained; owner has
  not separately approved executable sizing and accepted option spreads,
  brokerage costs, currencies and broker risk settings.
- **Testing:** Owner requested deferral. No offline, integration, paper/shadow,
  live broker or end-to-end test has been run for V7.
- **Deployment:** V7 is not deployed. Current V6 website and existing paper
  research services remain unmodified.

## Regulatory/API references

- Angel One official SmartAPI API and static-IP notice:
  https://smartapi.angelone.in/docs
  https://smartapi.angelbroking.com/exchange-regulations
- Angel official NFO scrip-master:
  https://margincalculator.angelone.in/OpenAPI_File/files/OpenAPIScripMaster.json
- Delta Exchange India API, including signature, IP whitelist and permission:
  https://docs.delta.exchange/
- Supabase private schema grants and RLS:
  https://supabase.com/docs/guides/database/postgres/row-level-security

## Future release authorization checklist

Before any V7 production deploy: perform a detailed source review, use a
separate staging database and a verified backup, inspect automatic migrations,
run tests and check security advisors, verify all broker account and exchange
requirements, and confirm the owner wants the deployment. Then perform
broker-read-only validation, paper/shadow validation and recovery tests.
**Real order execution must require a second explicit owner authorization
AFTER those checks; this source branch has no live-order method.**

Do not send broker PIN, API secret or TOTP through ChatGPT, a GitHub issue or
an email. Never print or commit any secret value.
