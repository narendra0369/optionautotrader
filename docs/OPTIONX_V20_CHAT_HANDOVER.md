# OptionX V20 / V21 Continuation Handover — 25 Nov 2026 IST

**Resume existing OptionX. Do not start over. Real orders are OFF. Never alter the manual Angel One position.**
Full owner-downloadable handover: `OPTIONX_V20_HANDOVER_2026-11-25.md`.

## Repository and infrastructure
- Repo `narendra0369/optionautotrader`, active target branch `optionx-live-prep-v7-20261124`. V21 work is PR from `optionx-v21-book-evidence-20261125`.
- Render staging backend `https://optionx-v7-offline-test-staging.onrender.com`; frontend `https://optionx-v7-frontend-test-staging.onrender.com`.
- AWS Lightsail external IP/egress `43.204.246.235` (Angel registered per user), original repo `/opt/optionx-v7`. Preserve original `optionx-market-api.service` and V14 worktree. AWS user `optionx` for private runs. No direct AWS SSH connector; user runs commands locally.
- AWS worktrees: `/opt/optionx-v7-lifecycle-v18`, `/opt/optionx-v7-pg-v19`, `/opt/optionx-v7-diag-v20`. AWS Python virtual environment `/tmp/optionx-v19-pg-venv` has `psycopg 3.2.13`.
- Supabase project `yghijfzwsvmzaffllszl`. Migration `20261125110607_optionx_v18_private_durable_ledger_stopped_guard`: 9 `optionx_private` tables, RLS all enabled, browser access blocked, 2 append-only triggers, STOPPED-only engine guard. Secrets never in chat or GitHub.
- AWS SSL CA `/etc/optionx-v7/supabase-ca.crt` (Supabase Root 2021); pooler `aws-1-ap-southeast-1.pooler.supabase.com` port 5432. User verified `SUPABASE_TLS_VERIFIED: YES / POSTGRES_CONNECTION: PASS / OPTIONX_LEDGER_TABLES: 9 / REAL_ORDERS: OFF`. Do not suggest disabling TLS or repeating working connection setup.

## Milestones already finished
- V18 PR #19 squash `111ed366`: 20/20 AWS safety tests PASS; local lifecycle rehearsal (write-before-send unknown, 2-entry cap, fill monotonicity, exact protective stop verification, recovery); **not live production execution**.
- V19 PR #20 squash `68acb686`: 18/18 AWS tests PASS; read-only broker books + PG ledger comparison.
- V20 PR #21 squash `e2c90bfb`: staged, private owner/PG/Angel diagnostics and mocked CI PASS.
- User ran V20 authenticated broker + database recovery; last verified output:
```
BLOCKED_REASONS: ACCOUNT_POSITION_OWNERSHIP_UNRESOLVED,BROKER_NATIVE_STOP_END_TO_END_NOT_CERTIFIED,MANUAL_OR_UNTRACKED_BROKER_ORDER,REAL_ORDER_WORKER_SOURCE_LOCKED,TRADEBOOK_FILL_RECONCILIATION_PENDING
REAL_ORDERS: OFF | MANUAL_POSITIONS: UNTOUCHED
```
This means READ-ONLY connection/reconciliation **executed successfully**, but it explicitly blocks real entries. User's previously observed manual option position `NIFTY29DEC2629000CE` +65 (at that earlier snapshot) is **manual**, not OptionX-owned. Never cancel, close, adopt, or alter based on matching symbol.
- Source lock remains in `live_v7/angel_execution_transport.py` unconditionally blocking order writes.

## V21 next work
- `live_v7/angel_books_readonly.py` tradebook summary intentionally returns `fillsBrokerVerified=False, reconciliationPending=True` even if raw rows exist. Implement *strict* read-only broker fill evidence processing, not assume raw trades are reconciled. Angel official Get Trade Book response docs show `fillid`, `orderid`, `fillsize`, `fillprice`, `tradingsymbol`, `transactiontype`, `exchange`. Compare with owner-tracked broker order IDs and full orderbook quantities. Reject duplicate fill IDs, unknown statuses, non-NFO/ambiguous rows, stale data.
- Implement separate broker orderbook STOPLOSS_LIMIT `SELL` verification: matching owned order ID, product contract/token, trigger/limit valid, confirmed remaining quantity = owned OPEN quantity, status active. Never assume database row alone proves broker ACK. Partial fill, cancellation, target/stop races block.
- Write tests, PR, CI and Render staging; then provide Ubuntu isolated worktree command; keep transport source locked. No live orders without explicit authorization and certified end-to-end worker.
- Maintain maximum 2 auto entries per IST day, manual-trade isolation, 15m NIFTY/BANKNIFTY ATM CE/PE, paper stepped risk model (not live), premium navy/gold UI. No credentials/PEM/URI in chat.

## Continuation prompt
“Continue OptionX from `docs/OPTIONX_V20_CHAT_HANDOVER.md` and `OPTIONX_V20_HANDOVER_2026-11-25.md`. V20 authenticated AWS+Angel+Supabase read-only reconciliation passed but listed 5 blockers. Complete V21 strict broker TradeBook fill evidence and native protective SL orderbook verifier with offline tests/CI. Keep manual position untouched and real orders OFF.”
