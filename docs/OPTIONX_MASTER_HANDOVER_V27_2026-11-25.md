# OPTIONX MASTER HANDOVER — V27 (25 Nov 2026, IST)

**THIS IS THE CONTINUATION ENTRY POINT.** Resume existing project from this document; do not restart and do not repeat tests already PASS unless source has changed.

## Immediate next task
1. V27 GitHub PR #28 was merged into `optionx-live-prep-v7-20261124` at SHA `cd7b8f88ee84a42a4d13612bb273b8990d55f271`. Offline CI for V27 passed; **AWS V27 real LTP has NOT YET run / no BROKER_LTP obtained**.
2. User's last actual owner-authenticated AWS V26 broker output:
```
POSITION_1: CONTRACT=NIFTY29DEC2629000CE TOKEN=38158 NET_QTY=65 ACTIVE_SELL_ORDERS=0 ACTIVE_SELL_REMAINING=0
SL_TRIGGER_LIMIT: NOT_SET | LTP_TICK_BROKER_SUPPORT: NOT_YET_VERIFIED
REAL_ORDERS: OFF | MANUAL_POSITIONS: UNTOUCHED
```
This is a time-scoped snapshot, not proof of present position/exposure. User **explicitly wishes to test a real STOPLOSS_LIMIT SELL against that manual position, but only after contract, quantity, broker allowance, trigger/limit and max-loss verification, and they require separate final affirmative consent before any real order**. They have NOT approved an exact order yet.
3. Next: AWS Ubuntu install V27 isolated worktree, run 10 tests, then use V27 read-only quote CLI. Verify current net quantity/no active sell orders again, broker LTP, official tick size, valid SELL stop trigger/limit with LPP and permitted order fields, price freshness/time, risk and explicit owner final confirmation. **NO order placement until separate informed authorization + broker approval + execution/recovery certification.**

### V27 AWS commands (copy-paste in AWS Ubuntu SSH, not Windows PowerShell)
```bash
sudo bash -c 'set -e; cd /opt/optionx-v7; git fetch --no-tags origin refs/heads/optionx-live-prep-v7-20261124; git worktree add --detach /opt/optionx-v7-quote-v27 FETCH_HEAD; cd /opt/optionx-v7-quote-v27; python3 -B -m unittest live_v7.test_manual_sl_quote_v27 -q; echo V27_AWS_TEST_COMPLETE'
```
```bash
cd /opt/optionx-v7-quote-v27
read -r -p "OptionX Owner UUID: " OWNER
read -rs -p "Angel Client Code: " CLIENT
echo
sudo -u optionx env \
  OPTIONX_OWNER_USER_ID="$OWNER" \
  ANGEL_ALLOWED_CLIENT_CODE="$CLIENT" \
  ANGEL_EGRESS_PUBLIC_IPV4="43.204.246.235" \
  PYTHONDONTWRITEBYTECODE=1 \
  /tmp/optionx-v19-pg-venv/bin/python -B \
  -m live_v7.manual_sl_quote_v27
unset OWNER CLIENT
```
Angel API key, PIN and TOTP are prompted privately on Ubuntu. **Never paste or disclose secrets to chat, code or logs.** An LTP response is NOT exchange timestamp verification or order permission. V27 deliberately prints `BROKER_FEED_TIMESTAMP_VERIFIED: NO` and `TICK_SIZE_AND_LPP_VERIFIED: NO` and leaves SL unset.

## Verified infrastructure and links
- GitHub private repo: `narendra0369/optionautotrader`; active main work branch `optionx-live-prep-v7-20261124`; V27 `cd7b8f8`, PR #28 `https://github.com/narendra0369/optionautotrader/pull/28`.
- Frontend staging `https://optionx-v7-frontend-test-staging.onrender.com`, backend staging `https://optionx-v7-offline-test-staging.onrender.com`; Render backend service `srv-dc291iks728c73bsc680`. V25 commit `30675cb` had Render status LIVE. Do NOT assume V27 deployed to Render; it was merged in GitHub only.
- AWS Lightsail Linux Ubuntu, outward static IP `43.204.246.235`, user confirms same IP registered at Angel One for their self-coded personally used API app. This is **not independently documented proof of broker order-write approval**.
- Original repo `/opt/optionx-v7`; active existing `optionx-market-api.service` from V14 worktree `/opt/optionx-v7-tradebook-v14` must be kept unchanged. AWS login scripts run as OS account `optionx`. Preserved worktrees include `/opt/optionx-v7-pg-v19`, `/opt/optionx-v7-diag-v20`, `/opt/optionx-v7-runtime-v22`, `/opt/optionx-v7-recovery-v23`, `/opt/optionx-v7-manual-sl-v26`; some worktree paths are merely suggested by commands, do not assume physically installed unless user confirmed.
- Python `psycopg==3.2.13` in `/tmp/optionx-v19-pg-venv` (temporary/volatile across reboots). User checked permissions: `POSTGRES_DRIVER: PASS`, `SSL_CERT_READABLE: True`, `RUNNING_AS_OPTIONX: True`.
- Supabase project `yghijfzwsvmzaffllszl`; private Postgres pooler `aws-1-ap-southeast-1.pooler.supabase.com:5432` (user `postgres.yghijfzwsvmzaffllszl`); private CA `/etc/optionx-v7/supabase-ca.crt`. User verified TLS `verify-full`, actual PostgreSQL connection and 9 private tables. Production migration `20261125110607_optionx_v18_private_durable_ledger_stopped_guard` is applied with 9 `optionx_private` tables, RLS and append-only event triggers, STOPPED-only engine guard. **Current schema cannot run a live worker**. Do not alter the DB without appropriate authorization/backup or compromise the separate Zelqoris/public schemas.
- Historical SSH connection from Windows: `ssh -i "$env:USERPROFILE\Downloads\LightsailDefaultKey-ap-south-1.pem" ubuntu@43.204.246.235`; do not assume key pathname if not present.

## Past verified milestones (distinguish offline vs actual broker)
- V17: AWS authenticated Angel GET-only three-book observer, 1 order + 1 position observed, user confirmed manual position, no real orders sent by OptionX.
- V18: 20 AWS offline lifecycle tests PASS, simulations for 2/day entries, restart, write-ahead ambiguous outcomes, partial fills, STOPLOSS_LIMIT checks.
- V19: 18 AWS offline PG recovery tests PASS; actual Supabase TLS connection and 9 tables verified.
- V20: private Ubuntu interactive Angel+PG read-only recovery PASS after fixing Owner UUID input; prior composite `BLOCKED_REASONS` includes manual exposure, native stop uncertified, tradebook fill pending and source lock.
- V21: 21 AWS offline tests PASS; pure TradeBook fill proof and broker orderbook STOPLOSS_LIMIT SELL verifier. GitHub PR #22, SHA `d4673fe`; Render staging LIVE then.
- V22: actual AWS Angel owner login, three books, Supabase ledger and evidence review all PASS; user output: `TRACKED_ENTRIES:0`, `VERIFIED_FILL_ORDERS:0`, `VERIFIED_STOP_ORDERS:0`, `MANUAL_OR_UNTRACKED_ORDERS:1`; real orders OFF. PR #23 SHA `f35d324`.
- V23: 29/29 AWS offline tests PASS; target-vs-stop race/recovery/manual isolation *simulation*, not live broker execution. PR #24 SHA `7b1aa37`, Render LIVE.
- V24: 18 GitHub offline compliance/prelive tests PASS; no MARKET/IOC for algo, static-IP/self-coded account conditions, broker permissions not inferred from read GET. PR #25 SHA `923725f`; Runbook `docs/OPTIONX_V24_PRODUCTION_LIVE_CERTIFICATION.md`.
- V25: 15 GitHub offline Postgres stopped-guard transaction tests PASS; serializable owner row locking code always aborts/rolls back under current STOPPED guard and never writes. PR #26 SHA `30675cb`; Render status LIVE. Not a functional production execution worker.
- V26: 9 GitHub offline tests PASS + **actual AWS authenticated read-only manual position output as above**; PR #27 SHA `fe6e113`.
- V27: 10 GitHub offline mock quote tests and both CI workflows PASS; PR #28 SHA `cd7b8f8`. **No AWS V27 test or real quote reported yet.** V27 read-only quote route uses market-data POST `/rest/secure/angelbroking/order/v1/getLtpData`, *not* broker order POST.
- GitHub all those PRs merged into `optionx-live-prep-v7-20261124`. Running GitHub CI is NOT equivalent to broker-side certification.

## Live execution blockers and safety invariants
- Source-level unconditional real-order lock in `live_v7/angel_execution_transport.py`; no production order-sending worker, no real OptionX BUY/SELL/STOP sent and no actual protective stop acknowledged. Real orders stay OFF, regardless of user’s willingness to test, until the specific test is safe and separately confirmed.
- Manual position is **not** OptionX-owned. Refrain from cancellation/closing/management by matching symbol alone. User has now authorized **preparation** of a separate manual-position test, conditional on detailed inspection and fresh final approval; do NOT silently reinterpret old code's automatic manual isolation as permission to submit a real SELL.
- Snapshot `NIFTY29DEC2629000CE`, token `38158`, net long `65`, zero active sell at that time. Not guaranteed now. Revalidate active orders, holdings, remaining quantity, market state, product type, tick and LPP right before any live intervention.
- Determine and show exact SL trigger/limit, net quantity, premium reference, estimated stop-loss impact relative to actual cost basis, max acceptable risk, gaps/illiquidity, stop-limit non-guarantee, and fees. Request fresh final YES to fully specified order, not generic “ha.”
- Verify Angel One permission for native NFO SELL STOPLOSS_LIMIT on the actual instrument, correct `variety=STOPLOSS`, `ordertype=STOPLOSS_LIMIT`, `duration=DAY`, `transactiontype=SELL`, valid `triggerprice`, `price`, lot/tick, and return statuses. MARKET and IOC should not be used.
- Audit risk of collateral orders/OCO: an independent target SELL when SL SELL remains pending may over-sell. Unknown submit/modify/cancel outcome => never blind retry; fail closed and request authenticated reconciliation.
- No direct SSH remote-command tool to AWS. Github/Render/Supabase connectors are available in this ChatGPT account, but those don't grant SSH or authority to trade. Ask user to execute AWS commands in terminal and return redacted status.
- Initial planned automated trading risk rule: max 2 auto entries per IST day; 15-minute NIFTY/BANKNIFTY ATM CE/PE, eventual BTC Delta. Preferred RR 1:3 for research; virtual paper equity tier starts ₹30k with +1 lot per +₹40k, risk ₹300/lot, target ₹600/lot, daily loss ₹600/lot. **These paper settings do not authorize live position sizing.** UI deep navy/black + champagne gold.
- Real order/regulatory checks need official broker acknowledgement, DIY vs vendor rules, compliance confirmation, real broker stop support, production durable DB journal/worker, kill switch/recovery tests and explicit risk approval. Do not turn off source lock through env.

## Critical module references
- `live_v7/manual_sl_quote_v27.py` and `live_v7/test_manual_sl_quote_v27.py` — NEXT test.
- `live_v7/manual_sl_preflight_v26.py` — authenticated positions/orderbook, no orders.
- `live_v7/aws_runtime_evidence_cli_v22.py` and `live_v7/aws_runtime_evidence_v22.py` — owner-bound Angel+Supabase reconciliation (read-only).
- `live_v7/broker_evidence_v21.py` — pure owned fill/native stop checks.
- `live_v7/execution_coordinator_v23.py` — offline fail-closed OCO/stop/partial/restart simulation.
- `live_v7/prelive_gate_v24.py` — compliance preflight, always LIVE OFF.
- `live_v7/pg_atomic_reservation_v25.py` — current STOPPED guard prevents all write operations.
- `live_v7/angel_execution_transport.py` — **source-locked** no live broker writes.
- `docs/OPTIONX_V20_CHAT_HANDOVER.md`; `docs/OPTIONX_V24_PRODUCTION_LIVE_CERTIFICATION.md`.

## Next-chat user prompt
“**Continue OPTIONX from docs/OPTIONX_MASTER_HANDOVER_V27_2026-11-25.md in my GitHub repo narendra0369/optionautotrader. Do not restart earlier setup. V26 AWS manual position = NIFTY29DEC2629000CE token 38158 long 65, active SELL 0 at last check; V27 PR #28 cd7b8f8 merged with 10 CI tests PASS, but V27 AWS LTP run is pending. Continue directly from V27 AWS installation + private read-only quote, then verify tick/LPP, allowed NFO native STOPLOSS_LIMIT, exact SL/risk and ask me for explicit final consent before any real SELL. Preserve manual position and keep REAL ORDERS OFF meanwhile.**”
