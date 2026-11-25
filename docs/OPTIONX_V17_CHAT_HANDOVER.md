# OptionX V17 — New Chat Handover (25 Nov 2026 IST)

**Resume this existing project; do not restart or unlock real orders merely by changing flags.**

## Last verified AWS user output

```text
AWS_ANGEL_PROFILE_VERIFIED: YES
LIVE_ORDERS: OFF | MANUAL_POSITIONS: UNTOUCHED
READ_ONLY_AUDIT_OK: orders=1 positions=1 | entries=BLOCKED | digest=9101e8dcbbca
```

User explicitly confirmed observed `NIFTY29DEC2629000CE` +65 position was **manually entered at Angel One**, NOT by OptionX. Never modify/cancel/close manually entered broker positions automatically. Snapshot may be stale; re-check when needed.

## GitHub, Render, AWS

- Repo `narendra0369/optionautotrader`; branch `optionx-live-prep-v7-20261124`.
- Latest functional V17 commit `98f9423656a9a68f876fad4951a72f64a9bae086`, PR #17.
- PR #16, commit `49928b0`: `live_v7/aws_shadow_observer.py`, append-only diagnostic SQLite and 12 offline tests. User ran all 12 on AWS: OK.
- PR #17: `live_v7/aws_angel_owner_reader.py`, interactive private owner + Angel login in AWS session RAM, GET-only orderbook/tradebook/positions; 242 offline tests PASS. Render backend staging deployed LIVE at V17.
- Frontend https://optionx-v7-frontend-test-staging.onrender.com; staging backend https://optionx-v7-offline-test-staging.onrender.com.
- Render backend `srv-dc291iks728c73bsc680`, frontend `srv-dc2927sipgvc73851nig`.
- AWS confirmed observed egress twice: `43.204.246.235`, matches Angel-registered IP supplied by user; *not independent broker certification*. Render staging outbound `74.220.52.132` is a **different host**, not an AWS mismatch.
- Original AWS source at `/opt/optionx-v7`, original live localhost service `optionx-market-api.service` on `127.0.0.1:10000` previously deployed via independent V14 worktree `/opt/optionx-v7-tradebook-v14`; do not replace or delete. Original AWS source contains untracked private `ops/aws_local_market_feed.py`.
- AWS worktrees: V16 `/opt/optionx-v7-worker-v16`, V17 `/opt/optionx-v7-aws-reader-v17`. The AWS V17 login/observation ran from the V17 worktree, not the website process.
- Private diagnostic SQLite: `/var/lib/optionx-v7/angel-shadow.sqlite3` (NOT production ledger). No secret values in this document.

## Current capabilities versus uncompleted work

**Verified:** AWS Angel profile login, owner verification and read-only broker book observation; 1 order and 1 position observed and sanitized audit written; no broker orders sent by OptionX. Source-level real order lock remains on in `live_v7/angel_execution_transport.py`. `canSubmitOrder:false`, `canCancelOrder:false`, `liveOrdersEnabled:false`.

**NOT verified / NOT enabled:** broker-native protective SL order placement and acceptance; actual order acknowledgement/fill, real-time stop/target lifecycle, partial fills, network timeout and AWS restart reconciliation, authoritative production PostgreSQL ledger, persisted kill switch, independent regulatory broker certification, owner live-risk authorization, certified AWS live execution worker.

- `live_v7/private_ledger_schema_draft.sql` is a **draft**, not applied. Do not change production database without backup, schema audit and explicit authorization.
- AWS V17 login is **interactive**, private, short-lived RAM session. Render Angel login is separate RAM session. Do not assume one reaches the other. Earlier unauthenticated AWS localhost probes returned 401/403 as designed.
- No direct AWS SSH connector; provide copy-paste Ubuntu commands and verify user output before declaring AWS deployment.
- User's preferred **2 maximum auto entries/day** even after target/SL; manual trades separate, conflicting manual exposure blocks new auto entries rather than being modified.
- NIFTY and BANKNIFTY ATM CE/PE on 15-minute strategy timeframe (Angel), RR1:3 target preference. BTC/Delta later. Use broker-confirmed contract size/tick/quote freshness and Greeks; do not guarantee forecast fill durations.
- Preserve preferred premium UI: navy/black, champagne gold, slate cards, white text, green/red for P&L only.
- Paper tier preference: INR 30k start, every additional INR 40k adds one lot, risk INR 300/lot, target INR 600/lot, daily max loss INR 600/lot. This is a paper model, NOT approved live risk sizing.

## Next steps — prioritize writing actual tested code

1. Inspect latest GitHub modules: `market_api.py`, `angel_gateway.py`, `live_v7/aws_angel_owner_reader.py`, `live_v7/aws_shadow_observer.py`, `live_v7/ledger_store.py`, `live_v7/private_ledger_schema_draft.sql`, `live_v7/angel_execution_transport.py`, `live_v7/protective_exit.py`, `live_v7/reconciliation.py`, and tests.
2. Build server-owned secure AWS session / authenticated broker reconciliation and reliable persistent record of OptionX-owned orders while partitioning manual external trades.
3. Develop/test authoritative PostgreSQL ledger in staging, including idempotency, owner guard, two-entry daily budget, backup, recovery; production migration only with approval.
4. Build and simulate native protective-stop, target, partial-fill, unknown-order, cancel, restart, stale-quote and loss-limit states; verify current broker rules against official docs.
5. Keep real order source lock until owner authorization, certification and end-to-end recovery tests completed. **Never claim live ON or submit real orders now.**
6. Use PRs, offline CI and Render staging; backup originals and avoid repeating already passed tests without code changes.

For the most detailed copy-paste handover, user has a separate Markdown artifact named `OPTIONX_V17_HANDOVER_2026-11-25.md`; attach it to the new chat if available. Never request or post API key, PIN, TOTP, JWT, PEM or secrets.

**Next chat opening:** “Continue OptionX V17 from `OPTIONX_V17_HANDOVER_2026-11-25.md` and `docs/OPTIONX_V17_CHAT_HANDOVER.md`. AWS owner-authenticated 3-book read-only observer PASS, orders=1 positions=1, manual trade; finish ledger / protected exits / recovery, then gated live execution certification. Do not restart and do not silently unlock orders.”
