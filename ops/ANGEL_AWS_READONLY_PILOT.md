# OptionX Angel One AWS Mumbai — SSH-only pilot (2026-11-24)

## Verified prerequisites
- Existing Lightsail AWS Mumbai host with static public IPv4 43.204.246.235.
- User-provided on-host report: local /health has status=ok, paperOnly=true, liveOrdersEnabled=false; systemd active; real-order route hard-locked; unauthenticated Angel status 401.
- User confirmed SmartAPI App and the registered primary static IPv4 are visible in the official Angel portal. This does NOT certify actual broker access, exchange permissions or API key type.
- **External integration NOT YET TESTED:** no real Angel credential, profile, NFO quote or 15m request was used by GitHub CI or the AI assistant.

## Scope and safety
- Entry point: ops/angel_ssh_readonly_pilot.py, run under the restricted optionx Unix user on the existing AWS instance.
- Credentials are prompted only in the user's interactive SSH TTY using hidden getpass prompts for API key, PIN and fresh TOTP. Do not put credentials in chat, shell history, GitHub, log files, environment variables, a published UI or public URL.
- Existing angel_gateway and live_v7.angel_marketdata modules verify broker profile, official NFO contract master, indicative LTP and completed FIFTEEN_MINUTE historical bars. Credentials/JWT stay in short-lived CLI process RAM and disconnect drops the session on normal exit.
- One-lot ₹300/₹600 paper **preview** is purely hypothetical. No persisted positions, fills, slippage, charges, margin, automatic SL/TP or watch loop. Do not call it a working auto paper account or backtest.
- **Absolutely no real order placement, modification or cancellation routes are present in the pilot; the original gateway real-order locks remain intact.**
- Render (Singapore) is separate from the AWS broker session. A SmartAPI App static IP does NOT make a Render-originated request originate from AWS.
- Never expose raw HTTP port 10000 publicly; keep API on 127.0.0.1 until authenticated HTTPS/domain/owner/rate limits and lifecycle checks pass.

## Deployment from user's own Windows desktop
The OptionX_Angel_AWS_ReadOnly_Pilot.zip contains:
- START_ANGEL_AWS_PILOT.ps1
- START_PRECHECK.bat
- START_ANGEL_READONLY_AND_PAPER.bat
- README_HINDI.txt

The PowerShell script uses the user's own local Downloads PEM key to SSH into the existing server with host-key checking, downloads the reviewed pilot source PINNED to successful CI commit c28dfa7c14cd791e0b3b7b4d263fdb59b1e80f0d into a temp file, installs ONLY a new (no overwrite) /opt/optionx-v7/ops/angel_ssh_readonly_pilot.py with root:optionx ownership and mode 0640, and runs as restricted optionx. Existing systemd is not restarted/reconfigured. If the destination exists but differs, installation is blocked instead of overwriting.

Manual host command after installing reviewed pilot file (interactive SSH terminal):

    sudo -u optionx /bin/sh -c 'cd /opt/optionx-v7 && exec /usr/bin/python3 -B -m ops.angel_ssh_readonly_pilot --expected-ip 43.204.246.235'

Add --connect --market NIFTY --side CE --paper-preview for local hidden broker login prompts. Enter desired option strike in the prompt, or pass --strike 26000 after reviewing the appropriate underlying index level. For BANKNIFTY or PE use --market BANKNIFTY --side PE.

All CI tests are mocked and offline; user must run the real broker SSH flow and provide REDACTED success/failure codes before making broker-access claims.

## Real-order conditions still BLOCKED
Do NOT add or turn on live order submission until independently verifying:
- Broker/exchange algorithmic trading eligibility, static IP on the specific app, owner identity and strict authentication/authorization;
- Token-accurate instruments, lot sizes, exchange-timestamped live quotes, order/margin APIs, exchange rules, charges;
- Idempotency, restart, failure recovery, partial fills, rejects, cancel/modify protections, reconciliation and daily risk caps;
- Kill switch, audit evidence, operator confirmations, emergency manual closure, staged paper-then-small-live acceptance and explicit approval.

Official docs:
https://smartapi.angelone.in/docs
https://smartapi.angelone.in/exchange-regulations

## Confirmed operator broker pilot outcome — 2026-11-24
- Operator reports the user-run AWS Mumbai SSH-only pilot returned ANGEL_PROFILE_VERIFIED connected=True, with masked client suffix (no identity or secrets retained in documentation).
- NIFTY 01 Dec 2026 26000 CE, token 47895, lot size 65; indicative LTP ₹62.15 at 2026-11-24 16:30:46 UTC; 26 completed 15-minute historical candles. These are a point-in-time pilot response, not current market prices or independently exchange-timestamped quotes.
- Pilot reported illustrative one-lot stop ₹57.55 and target ₹71.40, theoretical loss ₹299 and gain ₹601.25 **before charges and slippage**. No paper position had been persisted during that pilot and no real orders were placed. Broker login was discarded at exit.
- Subsequent isolated source work added a private paper-only SQLite journal and an explicit human-driven one-shot quote observation tool, with its own offline tests in this branch. This does NOT establish continuously running auto-paper, public HTTPS broker login, broker order lifecycle, real-money API order approval or live order permission.
- The Windows OptionX_Angel_Paper_Ledger_V2.zip launcher installs two NEW source files without overwriting the original first pilot or the existing systemd service. It defaults to a single illustrative virtual lot. Local operator installation and live paper journal operations have not yet been confirmed.
