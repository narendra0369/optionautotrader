# OptionX consolidated research / live readiness — 24 November 2026

**Scope:** Angel One / NIFTY / BANKNIFTY + AWS Mumbai read-only research and virtual paper accounting. This is NOT certification, production live trading, broker API trading authorization, or an Android release.

## Confirmed from user's own AWS console output
- Existing AWS Mumbai static IPv4 43.204.246.235 outward egress matches the pinned address and source-only backend listens locally with real money orders hard-locked.
- Angel One SmartAPI user-controlled private SSH profile login succeeded from AWS egress, and session was deliberately discarded after each pilot.
- Read-only NIFTY01DEC2626000CE token 47895 (lot 65) fetched official NFO master; indicative LTP 62.15; 26 completed historical 15-minute candles. The timestamp was local observation only and quote freshness/executability was NOT verified.
- AWS combined batch reported 243 Python offline regression tests PASS. These were not broker orders or live execution tests.
- User's AWS paper SQLite account initialized with INR 500000 initial virtual capital, max 12 illustrative stepped lots, max 2 entries per IST day, no open position, no real broker orders.
- User's foreground virtual quote-monitor source module was installed in AWS under restricted optionx user and its setup and status printed PASS. No actual virtual entry or repeated polling session has been reported yet.
- User's V4 actual AWS output has now confirmed PASS: private paper SQLite quick_check and schema/account integrity, owner-only consistent SQLite backup created in /var/lib/optionx-paper/backups/, non-overwriting dashboard and recovery modules staged under the restricted optionx user, AWS egress and locked order endpoint rechecked, local SSH-tunneled dashboard responded on Windows 127.0.0.1:18751. Virtual equity INR 500000, 0 trades, 0 open positions, 12 max stepped virtual lots. Real-money orders remained OFF.

## V6 real AWS + Angel One read-only results — user verified 24 Nov 2026

The operator supplied the full Windows PowerShell and private AWS SSH terminal results of
`OptionX V6 Fixed` (Windows folder `OptionX_V6_Fixed_20261124_230154`).
This **supersedes** the earlier V4-only runtime snapshot below; do not repeat verified checks
unless a code change or expiry requires them.

- `PASS: pinned no-overwrite safe V6 modules staged`: original AWS market API service,
  broker order gateway, production Render, GitHub production branch and firewall preserved.
- `PASS: isolated no-network watchdog systemd unit staged`, `WATCHDOG HEALTHY_PAPER_LEDGER`
  and `PASS: background 24H PAPER HEALTH WATCHDOG ACTIVE`. The independent
  `optionx-paper-health-watchdog.service` had started with a private 0600 heartbeat
  and no Angel session / real order access. This monitors **SQLite integrity and
  virtual quote staleness**, NOT unattended price streaming or automatic trading.
  A single success response does not prove 24-hour uptime.
- `PASS: 21/21 offline broker lifecycle failure scenarios`; these were synthetic
  and did not exchange any real order or simulate verified exchange fills.
- `PASS: server egress IPv4 matches attached AWS static IP`,
  `PASS: localhost research backend healthy and paper-only`,
  `PASS: real-order endpoint remains hard-locked`.
- Paper account recovered/checked with ₹500,000 virtual starting capital,
  0 open paper positions and virtual tier limit 12 lots (existing V4 result).
- Separate public HTTPS `https://optionx-v8-mobile-paper-staging.onrender.com`
  was reached successfully from the Windows runner. This is an installable
  **read-only mobile PWA shell**, **NOT** a signed native APK, privately
  authenticated AWS sync, or broker-trading application.
- Authenticated private Angel One profile verified during a short-lived SSH session.
  The official account GET-only **NFO orderbook and positions read** passed,
  reporting `NFO_POSITION_ROWS=0`, `NFO_NONZERO_POSITION_ROWS=0`,
  `NFO_ORDER_ROWS=0`, `NFO_OPEN_OR_PENDING_ORDER_ROWS=0`,
  `POSITION_OR_ORDER_MANUAL_REVIEW_REQUIRED=False`. No private broker IDs
  or positions were copied to source control. Snapshot counts apply only to
  the moment tested; they do not certify future account state.
- Temporary Angel session was discarded, with
  `ACCOUNT_READONLY_PILOT_COMPLETED: no broker orders sent`;
  `LIVE_TRADING_NOT_APPROVED`.
- One-shot release gate matrix deliberately listed **13 live release blockers**.
  The earlier "authenticated orderbook/tradebook/positions" blocker is now
  **partially satisfied** by a private GET-only orderbook + positions read;
  broker **tradebook, fill/order state reconciliation, independent time evidence**
  and repeated/restart tests remain unverified. Avoid changing this entire
  blocker to PASS from a single empty snapshot.
- V6 ended `OPTIONX V6 SAFE INSTALLER ENDED. REAL-MONEY ORDERS OFF.`

## Necessary next independently verifiable steps

1. In an NSE regular session, conduct a single intentionally approved
   *virtual-only* paper entry and 8-minute foreground quote monitoring
   (previously zero paper positions). Record safe actual output and stale-data
   handling. Do not submit real broker orders.
2. Review 24x7 watchdog across an extended observation window, service restarts,
   old quote warnings, and any alarm destination; do not confuse a healthy
   database with a live market data stream.
3. Test a private authenticated Angel One **Tradebook and Funds read**, if the
   account/broker scopes permit, without logging sensitive account values.
   Independently verify snapshot timestamps, owner session, retry/reconciliation.
4. To connect private account data to Android/HTTPS, design and separately
   verify server-authenticated owner-bound JWT / session validation,
   TLS gateway, proxy trust, rate limits, audit logs, safe CORS, and anti-BOLA.
   No private AWS HTTP port exposed or production service changed yet.
5. Full automatic paper execution depends on a lawful secure unattended broker
   session solution, persistent market-data feed, verified exchange calendar,
   strategy signal validation, broker quote staleness, risk stops, fail-closed
   reconnection, monitoring and manual STOP. Current watchdog does none of these.
6. Actual Angel One and other brokers' order execution remains blocked until
   applicable registration/permission, owner capital/risk approval, verified
   limit-order types, margin and charges, broker-native protective exits,
   tradebook reconciliation, unknown ACK, rejection/partial fills, cancel and
   restart recovery, audit storage and explicit new live permission.

## Additional completed source-only work on isolated GitHub branch
- ops/angel_private_account_readonly_audit.py: owner-verified, private-SSH, GET-only account position/orderbook COUNTS audit, with short-lived session and no raw account data printed. **SOURCE ONLY; actual AWS broker-private read has NOT YET BEEN RUN.**
- ops/synthetic_live_lifecycle_matrix.py: 21 deterministic, OFFLINE, no-broker-event-fills/no-orders scenarios for stop ACK/rejection, fill and missing protection, stale broker evidence, unknown outcome, duplicate, partial fill, cancel race, restart and reconciliation. Every scenario must remain blocked for live order submission.
- ops/optionx_release_gate_matrix.py: fail-closed factual release readiness report, explicitly distinguishing runtime verification from source/tests. This always reports live trading NOT approved and private production ledger/auth/TLS/order lifecycle not complete.
- ops/https_mobile_access_gate.py: prospective owner/TLS/origin/rate-limit/GET-only policy; **no actual production HTTPS gateway or Android app** is deployed or enabled.
- ops/private_paper_dashboard.py: extra warning for stale/missing local paper LTP observation; the changed source is NOT in earlier pinned V4 package and needs a separately reviewed future deployment.
- .github/workflows/angel-aws-pilot.yml: combines mocks/offline tests, existing API, safety, shadow lifecycle, owner TLS and paper integrity. Latest CI result may be checked for the exact head SHA.
- All changes in isolated branch optionx-angel-aws-pilot-20261124; NO production branch merge, Render deployment, AWS firewall changes, broker order route installation, or credential changes.


## Follow-on work verified after V4
- Render **new isolated public HTTPS mobile staging** static site created and deployment reached `live`: https://optionx-v8-mobile-paper-staging.onrender.com . This is an Android-installable **read-only PWA shell**, not a native signed APK and has **NO** connection to any private AWS Paper database or owner auth.
- PWA has four premium navy/champagne-gold screens: Home, Strategies, Backtesting, Access. It is publicly visible but has **no real broker login, no real order endpoints, no account sync, no secrets**. GitHub build/manifest/icon tests PASS.
- A strictly unprivileged `ops.paper_health_watchdog` and restricted `ops/systemd/optionx-paper-health-watchdog.service` are source-complete and offline CI tested. A one-shot Windows V6 ZIP installer was created to deploy this isolated 24x7 **database HEALTH watchdog** without broker sessions, market data streams or orders. **AWS installation has NOT yet been confirmed by user output.**
- 21 synthetic order/partial fill/stop/cancel/restart/duplicate safety replay scenarios and a source-only readiness matrix PASS offline CI. A new short-lived SSH owner-only Angel Orderbook/Positions GET pilot is source-complete and mocked tests PASS; actual operator-run GET result still **PENDING**.
- Angel official April 2026 notice requires registered static IP for API order execution, and disallows algorithmic Market/IOC orders (see official broker references below). Do not interpret previously verified Angel profile login/official scrip master as live-execution eligibility.

## Unresolved / never infer completion from green CI
1. **Actual paper monitoring and repeated paper entries** have not yet been tested in an NSE live session. LTP is an observation, not an executable broker price; only 26 candles, below the existing paper simulator's 120-candle minimum for certain strategies.
2. **Truly unattended 24×7 brokerage-backed PAPER strategy:** 24x7 watchdog source checks only SQLite integrity/staleness (no broker login/feed); it is NOT an automatic paper trader. 8-minute foreground monitor stops when SSH disconnects and the Angel session is discarded. Secure vault/session renewal, broker streaming, exchange holiday calendar and alerting are still incomplete.
3. **Owner-authenticated private web/mobile bridge:** public HTTPS static PWA preview has been deployed; private AWS account sync, verified owner identity, TLS trusted proxy to AWS, authenticated API, and native Android signed APK remain unimplemented. Existing Render Singapore backend must not be assumed to have AWS egress.
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
