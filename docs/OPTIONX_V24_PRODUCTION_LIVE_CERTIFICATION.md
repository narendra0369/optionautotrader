# OptionX V24 — exact requirements for production live broker certification (25 Nov 2026)

Status: **NO real order submitted. LIVE source lock is ON.** V22 authenticated AWS Angel GET books + private Supabase read-only audit PASS; 0 OptionX-owned orders, 1 manual/untracked order, unresolved manual position. V23 29/29 AWS offline tests PASS. The previous trading AWS service must not be replaced by testing modules.

## Policy independently researched
- Angel One's 13 March 2026 explanation of NSE/SEBI retail algo rules: from **1 Apr 2026** client-hosted self-coded API algo orders must originate at *registered* static IP; market and IOC orders are prohibited. Tech-savvy own algorithms under 10 orders/sec use generic exchange algo ID, while above threshold require registration. Hosting on own AWS is an exception **only for qualifying client-owned self-coded algorithms**. An external app sold/hosted for others has different broker-provider/empanelment requirements.
  https://www.angelone.in/news/market-updates/what-s-changing-in-angel-one-s-smartapi-access-from-april-1-2026
- Angel One SmartAPI official order API lists `NORMAL/LIMIT`, `STOPLOSS/STOPLOSS_LIMIT`, `triggerprice`, but listing an order type does NOT certify that the user's specific NFO options contract/account can place and maintain that stop.
  https://smartapi.angelone.in/docs
- Angel forum September 2026 discussion mentioned 9 OPS key cap, vs threshold 10 OPS; **throttle far below either (e.g. 1 outbound order request/sec)** after receiving broker exact route limits. Ops cap and registration are NOT broker approval by themselves.

## Broker confirmation needed, using official broker portal/support (no passwords in tickets)
Ask Angel One to confirm in writing for the specific account, API key/application and registered static IP:
1. API key is allowed for client-owned self-coded strategy from AWS static IPv4; whether generic algo ID tagging and any explicit account whitelisting is handled by SmartAPI automatically.
2. NFO **BUY LIMIT DAY** supported; NFO **SELL STOPLOSS_LIMIT DAY** for bought options supported with precise `variety`, `ordertype`, `triggerprice`, tick, producttype, lot sizing and orderbook statuses. No MARKET/IOC. Verify auction/session restrictions after Aug 2026.
3. Rate limiting including place/modify/cancel/GTT; error codes; whether there is a sanctioned test/mock environment for order lifecycle, including partial fills, stop rejection and timeout.
4. Is self-hosting own code at AWS valid for this owner's use case? If marketed to third parties, separate vendor/Algo Provider obligations apply; do not assume DIY exemption.
5. Confirm there is no current manual exposure in the intended option contract during a controlled live test. OptionX must not touch any existing manual order or position.

## Evidence needed for real-money certification after approval
- Broker and owner re-authenticate in same short-lived AWS worker, static egress matches broker.
- Create durable owner-bound, unique idempotent PostgreSQL order intent in atomic transaction and append audit event before any possible send; committed STOP switch and 2 auto-entries/day budget. Restrict dedicated DB role; backup/PITR, credentials file permissions and systemd restart policy.
- Fully review technical broker SDK changes and response statuses; initial BUY LIMIT order should be owner-authorized by exact contract, max funds/lots and max permitted loss, during permitted exchange time. A real order may incur loss and cannot be retroactively guaranteed protected. Do not use a manual position to test.
- On broker ACK independently GET orderbook and GET tradebook, verify exact broker order ID, owned token, fill IDs/quantity/cost, and match ledger.
- On actual fill, verify optional broker-native SELL STOPLOSS_LIMIT ACK and *live broker orderbook active remaining quantity* equals uncovered owned open quantity. Stop-limit can gap or be rejected; it does not guarantee exit.
- Simulate network partition and kill process in **broker-approved sandbox/mock** before any production forced failure; never pull power or restart during an unprotected live fill. Unknown send outcome -> no blind retry. Partial fills -> recompute coverage. Ensure only owned IDs eligible for any stop/cancel/close, and independent target+stop OCO race fails closed.
- With existing MANUAL_OR_UNTRACKED_BROKER_ORDER and ACCOUNT_POSITION_OWNERSHIP_UNRESOLVED blockers, do NOT initiate an automated real order test. User should not close or change their manual position merely to satisfy diagnostics.
- Production real execution branch requires separately reviewed code, broker certification and bounded risk approval. No environment flag can bypass the current source lock.

## The current V24 preflight
`live_v7/prelive_gate_v24.py` is a **pure, never-allow** compliance and order type checker. Even affirmative attestations can NEVER enable real orders. It rejects MARKET and IOC, non-NFO, source lock changes, stale or untracked broker positions, missing broker written consent, and missing bounded-risk authorization.
Runs `python3 -B -m unittest live_v7.test_prelive_gate_v24 -v` locally or in isolated AWS worktree. It will not contact Angel One or Supabase or modify anything.

## Next concrete build pieces
- Production private PostgreSQL *write* adapter with independent least-privilege DB role, transactional pre-send/unknown journal, append-only audit chain, backups, and multi-worker fencing (require explicit schema change authorization).
- Stopped-mode service with short-lived authenticated sessions, health probes, per-owner locks, daily quota, stop guard. Pair with mocked broker response provider.
- Broker-approved sandbox / mock exchange side-effecting integration tests (entry ACK, partials, stop reject, cancellation ACK, terminal fill). User-approved one-lot real test only if safe gates satisfied and separately authorized.
- Keep manual positions unmodified and LIVE OFF until the above proofs are complete.
