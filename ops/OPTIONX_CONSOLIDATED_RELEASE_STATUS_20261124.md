# OptionX consolidated research / live readiness — 24 November 2026

**Scope:** Angel One / NIFTY / BANKNIFTY + AWS Mumbai read-only research and virtual paper accounting. This is NOT certification, production live trading, broker API trading authorization, or an Android release.

## Confirmed from user's own AWS console output
- Existing AWS Mumbai static IPv4 43.204.246.235 outward egress matches the pinned address and source-only backend listens locally with real money orders hard-locked.
- Angel One SmartAPI user-controlled private SSH profile login succeeded from AWS egress, and session was deliberately discarded after each pilot.
- Read-only NIFTY01DEC2626000CE token 47895 (lot 65) fetched official NFO master; indicative LTP 62.15; 26 completed historical 15-minute candles. The timestamp was local observation only and quote freshness/executability was NOT verified.
- AWS combined batch reported 243 Python offline regression tests PASS. These were not broker orders or live execution tests.
- User's AWS paper SQLite account initialized with INR 500000 initial virtual capital, max 12 illustrative stepped lots, max 2 entries per IST day, no open position, no real broker orders.
- User's foreground virtual quote-monitor source module was installed in AWS under restricted optionx user and its setup and status printed PASS. No actual virtual entry or repeated polling session has been reported yet.
- User has begun running a V4 one-shot bundle for paper SQLite integrity/backup and a localhost-only premium dashboard. **Its real AWS result has NOT YET been provided**. Never assume V4 deployed successfully.

## Additional completed source-only work on isolated GitHub branch
- ops/synthetic_live_lifecycle_matrix.py: 21 deterministic, OFFLINE, no-broker-event-fills/no-orders scenarios for stop ACK/rejection, fill and missing protection, stale broker evidence, unknown outcome, duplicate, partial fill, cancel race, restart and reconciliation. Every scenario must remain blocked for live order submission.
- ops/optionx_release_gate_matrix.py: fail-closed factual release readiness report, explicitly distinguishing runtime verification from source/tests. This always reports live trading NOT approved and private production ledger/auth/TLS/order lifecycle not complete.
- ops/https_mobile_access_gate.py: prospective owner/TLS/origin/rate-limit/GET-only policy; **no actual production HTTPS gateway or Android app** is deployed or enabled.
- ops/private_paper_dashboard.py: extra warning for stale/missing local paper LTP observation; the changed source is NOT in earlier pinned V4 package and needs a separately reviewed future deployment.
- .github/workflows/angel-aws-pilot.yml: combines mocks/offline tests, existing API, safety, shadow lifecycle, owner TLS and paper integrity. Latest CI result may be checked for the exact head SHA.
- All changes in isolated branch optionx-angel-aws-pilot-20261124; NO production branch merge, Render deployment, AWS firewall changes, broker order route installation, or credential changes.

## Unresolved / never infer completion from green CI
1. **Actual paper monitoring and repeated paper entries** have not yet been tested in an NSE live session. LTP is an observation, not an executable broker price; only 26 candles, below the existing paper simulator's 120-candle minimum for certain strategies.
2. **Truly unattended 24×7 paper system:** 8-minute foreground monitor cannot persist after SSH disconnect and the temporary Angel session is discarded. Secure KMS/vault, session renewals, broker streaming, reconnection/backoff, exchange holiday calendar and alerting are not implemented or approved.
3. **Secure public web/mobile gateway:** no publicly authenticated HTTPS/domain, signed owner-to-AWS session, mTLS/proxy trust or mobile app release. Existing Render Singapore backend must not be assumed to have AWS egress.
4. **Actual broker private read-only orderbook/tradebook/margin and position reconciliation:** owner authentication and scope checks for those resources remain pending. Profile/LTP alone are not broker order authorization.
5. **Live order lifecycle:** no actual broker buy/sell, LIMIT order acceptance, fill, rejection, partial fill, cancel/modify, unknown acknowledgement, failover, recovery, SL/target protection or emergency manual flatten tested.
6. **Regulation and independent financial risk approval:** official broker/exchange permissions, registered execution app/IP, algorithmic trade approval, execution-grade bid/ask and exchange timestamps, costs, slippage, live funds sizing, margin and durable audit ledger are pending.
7. **Other brokers:** Delta and Stoxkart are not connected/authenticated here, despite other source scaffolding.

## Required safety posture
- Real-money order endpoint continues to return 423 Locked; live order transport is intentionally not deployed.
- No API key, PIN, TOTP, SSH key, client code or JWT in GitHub, ChatGPT, files, logs or shell arguments.
- Private Paper Dashboard must remain on 127.0.0.1:10001, accessed only by SSH from Windows local 127.0.0.1:18751. Do not expose AWS TCP 10000 or 10001 or open unprotected website endpoints.
- Use an explicit separate broker-approved change request to eventually enable live money orders AFTER verified order lifecycle, owner-specific auth, logged test evidence, emergency-stop and recovery validation, and user approval.

## Source verification
- GitHub branch: https://github.com/narendra0369/optionautotrader/tree/optionx-angel-aws-pilot-20261124
- CI workflow: https://github.com/narendra0369/optionautotrader/actions/workflows/angel-aws-pilot.yml
