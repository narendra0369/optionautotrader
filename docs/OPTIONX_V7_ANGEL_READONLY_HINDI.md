# OPTIONX V7 — Angel One Read-Only Account Snapshot (24 November 2026)

## Scope
Separate V7 Staging only. The production OptionX URL, Paper Engine and hard-locked real order gateway remain unchanged. The authenticated owner may request **GET** NFO Positions and NFO Order Book via official SmartAPI fixed read endpoints:
- `/rest/secure/angelbroking/order/v1/getPosition`
- `/rest/secure/angelbroking/order/v1/getOrderBook`

The backend needs a current, owner-matched, RAM-only Angel One profile session. This token expires after 15 minutes or a restart. Never copy your API key, PIN, TOTP or broker JWT into ChatGPT or GitHub.

## Gates
- Exact staging origin `https://optionx-v7-frontend-test-staging.onrender.com`; `OPTIONX_V7_STAGING_CORS=1`
- Verified Supabase JWT and `OPTIONX_OWNER_USER_ID` account binding
- Explicit separate server flag `OPTIONX_V7_READONLY_ANGEL_ENABLED=1` (OFF by default)
- Allowlisted GET operations only; normalized NFO rows, capped size, and no browser storage
- 423 on disabled read-only flag; 401 on missing OptionX session; 403 on wrong origin; 503 on expired/failed broker session

## Current limitations
- No broker quotes, risk order execution, margin, fill reconciliation or live trading.
- Snapshot records may be empty, or the broker may reject GET requests due to IP/API policy.
- This is NOT a permanent session, streaming feed, automation permission, or approved execution host.
- A staging deploy clears existing RAM-only broker sessions. Fresh owner verification on staging is required.
- The production frontend does not gain access to these private staging routes.

## Safe verification checklist
1. Confirm backend/Frontend staging deploys passed Python offline security and JavaScript static packaging tests.
2. With feature flag OFF, signed-in owner GET returns 423, no broker call (offline tests).
3. With feature flag ON, wrong origin returns 403 and unauthenticated call returns 401.
4. On staging, log in as OptionX owner and verify Angel profile. Click `View NFO Positions` or `View NFO Order Book` to attempt a single GET.
5. On a real broker refusal or API/IP restriction, keep real orders OFF and report only the generic error.
6. Confirm sign-out/disconnect/expiry clears snapshots in the browser.

No credentials are stored in Supabase, GitHub, Render variables, or client storage. No POST order/modify/cancel endpoints are added.
