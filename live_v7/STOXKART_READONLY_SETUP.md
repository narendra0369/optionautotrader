# OptionX V7 — Stoxkart real-account read-only login setup

**Status (2026-11-24 IST):** Broker option, temporary login and account
verification, read-only NFO positions and per-market routing are implemented
in **isolated V7 staging only**. No real buy/sell order transport exists.

## Verified during development

- Official Stoxkart Superr API published documentation:
  https://developers.stoxkart.com/api-documentation/login
  https://developers.stoxkart.com/api-documentation/portfolio
  https://developers.stoxkart.com/faqs/general-faqs
- Broker confirms API access is advertised as free, with normal brokerage
  charges on executions. Terms reserve changes to pricing.
- Broker terms disallow unattended fully automated orders without exchange
  approvals: https://www.stoxkart.com/terms-conditions
- V7 staging Backend: **97/97** offline tests, including mocked Stoxkart
  request-token exchange, profile match, NFO positions, expiry, replay
  and unsafe route checks (13 gateway tests + 10 HTTP handler tests).
- V7 staging Frontend: Render Node build and Stoxkart callback distribution
  pass. Both services reported LIVE. No actual Stoxkart account was accessed.
- Existing Supabase user-scoped route table now allows 'Stoxkart' only for
  NIFTY/BANKNIFTY. BTC is still Delta-only. RLS remained enabled and all four
  ownership policies were verified after the migration.
- **No live order endpoint was added.**

## What the account owner must do for the first read-only login

1. Open **https://superrapi.stoxkart.com/** and sign in to the Stoxkart API
   developer portal (or create an API account).
2. Create a Superr API app for *your own Stoxkart trading account*.
   Register the EXACT redirect URL:

       https://optionx-v7-frontend-test-staging.onrender.com/stoxkart_callback.html

   Do not use another site's redirect URL or the standard V6 website URL.
3. Open the testing site:

       https://optionx-v7-frontend-test-staging.onrender.com

   Log into the existing personal **OptionX** account. Open **Live Broker
   Setup → Stoxkart Superr API Login**.
4. Enter the API app KEY, app SECRET and expected Stoxkart Client ID in the
   site's HTTPS form. Do not share these with ChatGPT, GitHub or screenshots.
5. Click **Login at Stoxkart (read-only)**. The browser goes to the official
   Stoxkart broker site. Enter the Stoxkart password / TOTP there, NOT in
   OptionX. After broker redirect, the OptionX callback removes the temporary
   request token from the address and returns to the Live Broker Setup tab.
6. Verify the **Stoxkart profile verified** message. OptionX checks the
   actual broker profile's client ID, stores only a RAM session for up to
   15 minutes, and allows **View NFO positions (read-only)**. No order can be
   placed from this stage.
7. The browser and backend keep no long-term API secrets. If Render restarts,
   the login flow expires, or the site is opened in a different tab, repeat
   the login. A Stoxkart profile login is NOT regulatory approval for
   fully automated orders.

## Login troubleshooting

- "Missing flow or request token" → restart the connection in the SAME
  browser tab; ensure the API app redirect URL is exactly correct.
- "Owner not matched" → OptionX account doesn't match the approved personal
  owner binding on the V7 staging backend; do not share account IDs or
  credentials publicly.
- "Stoxkart rejected token/profile" → API app / redirect / client ID / TOTP
  may be wrong, or the broker has changed its auth endpoint/response shape.
  We need a sanitized error code or screenshot WITHOUT secrets to diagnose.
- "Positions unavailable" → profile verification can still work. Position
  API version/permission and current broker schema require owner-authorized
  read-only investigation.
- A full broker session, native SL, target, and real-money order execution
  have **NOT** been implemented or authorized.

## Security & deployment scope

Only the broker's own official domain handles passwords and TOTP. The
Stoxkart API app secret is sent via HTTPS to the owner-authorized V7 backend
and is held in process RAM for a maximum of 10 minutes, then consumed once.
The temporary access token remains in process RAM for at most 15 minutes.
No tokens or secrets are saved in Supabase, browser localStorage, app logs or
GitHub. The broker callback stores the one-time request token only in tab
sessionStorage long enough for the signed-in owner to POST it to the backend;
then it clears it.

No real trades: order placement / modification / cancellation paths are absent
and /api/live/ order endpoints remain permanently blocked in this version.
Do not interpret mocked 97/97 tests as real Stoxkart integration evidence.
