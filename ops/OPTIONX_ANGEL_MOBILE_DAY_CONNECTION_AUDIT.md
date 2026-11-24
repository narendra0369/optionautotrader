# OptionX Angel One: Mobile daily connection audit and safe staging (24 Nov 2026)

## Verified current design before this change
- Existing V7 frontend has an Angel One login form: Client Code, Trading API Key, PIN and six-digit TOTP; optional status and logout.
- `market_api.py` has owner-authenticated POST `/api/brokers/angel/connect` and `/disconnect`; `GET /api/brokers/angel/status` is owner-authenticated.
- `angel_gateway.py` authenticates `loginByPassword` then validates the returned Angel profile, holds API key and JWT in **server process RAM only** and **never saves PIN/TOTP**. Its former server local cap was 900 seconds (15 minutes), not an all-day login.
- V7 staging uses `https://optionx-v7-offline-test-staging.onrender.com` in Singapore; it is NOT the registered AWS Mumbai static egress 43.204.246.235. Browser login to this staging backend cannot be claimed as an AWS-side trading engine connection.
- V8 public mobile PWA initially had no broker login form, authenticated private AWS gateway or account sync. Live orders remain hard-locked.

## Implemented and tested source changes
- `live_v7/angel_day_session_policy.py` — a pure opt-in read-only *trading-day* session expiration limiter. Uses shorter of current NSE session end (15:30 IST), maximum eight hours, and broker JWT `exp` less 120 seconds; malformed or absent JWT expiry keeps the conservative 15-minute cap. The JWT claim is **not** independently signature validated, and can ONLY reduce a lifetime. Actual broker revocation can happen earlier.
- `angel_gateway.py` — read-only day policy only when `OPTIONX_ANGEL_READONLY_DAY_SESSION=1`, `OPTIONX_AWS_OWNER_HTTPS_GATEWAY_VERIFIED=1`, owner configured and live orders remain OFF. This is **not enabled on Render or AWS** by source changes. Default session remains 15 minutes, protecting existing services. New status fields include `readOnlySessionScope`, `temporaryOneLoginReuse`, `needsFreshTotp` and `connectedToAwsAutoTrading=false`.
- `live_v7/test_angel_day_session_policy.py` — offline checks for default 15min, opt-in day cap, JWT expiry shortening, broken/expired JWT, weekends, market close, no PIN/TOTP persistence, locked broker execution, and feature flags.
- `live_ui.mjs` — session remaining minutes and IST expiry visible on existing HTTPS V7 website, status rechecks on mobile foreground/resume and each minute; never auto-login silently and never stores credentials. This file was committed to BOTH isolated pilot and V7 staging branches.
- `mobile_v8/index.html` — a single mobile shortcut under Access: **Open Secure Angel Login (V7)**, pointing to the existing HTTPS, owner-authenticated V7 broker form at `https://optionx-v7-frontend-test-staging.onrender.com/#live`. No broker credentials in link, URL, storage or V8 PWA.
- V7 frontend Render staging deploy `dep-dc2sv9jncjis73dthk40` returned LIVE.
- V8 mobile Render staging deploy `dep-dc2svad9fdbs738kv3v0` returned LIVE.

## Exact limits / what has NOT been achieved
1. **No all-day broker session from Android to AWS.** A registered IP alone does not create a secure HTTPS owner-bound gateway to the AWS-local broker process. Existing Render Singapore login and AWS SSH owner login have separate, short-lived in-memory sessions, not shared.
2. **No private AWS HTTPS gateway deployed.** A separately verified trusted hostname/TLS/owner-auth proxy is required before entering broker API key/PIN/TOTP from Android directly into AWS.
3. **No day-mode feature flag enabled** on AWS, Render or broker; the source-only option must pass end-to-end gateway, broker expiry, restart, security and session revocation tests.
4. **No encrypted persistent key, PIN, TOTP, refresh token or broker session vault** installed. TOTP must be entered once per actual session login; after expiry/restart/broker revocation the operator must re-authenticate.
5. The Angel One official documentation describes an API session continuing until midnight, subject to broker invalidation, but that is NOT a guarantee of zero reconnection; our proposed policy conservatively caps at NSE 15:30.
6. **No LIVE REAL-MONEY ORDER capability enabled or added.** All broker event/order lifecycle barriers persist.

## Operator path presently usable
1. Open Android installed V8 preview: `https://optionx-v8-mobile-paper-staging.onrender.com`
2. **Access → One-time Angel Connection (Mobile) → Open Secure Angel Login (V7)**.
3. Sign in to personal OptionX account on V7 staging, open Broker Setup, and use its **existing read-only** Client Code/API Key/PIN/TOTP form.
4. After successful broker login in the allowed backend environment, use Check Session and Read-only Orders/Positions during its **15-minute RAM session**; expiry and remaining minutes now visible. If login fails because Render backend IP is not authorized, do not circumvent static-IP restrictions; use private AWS SSH operator path.
5. None of this logs into the AWS backend or enables trading. Do not send broker secrets in ChatGPT, screenshots or third-party forms.

## Remaining implementation for real daily Android-to-AWS authentication
- Provision a trusted private AWS hostname or private overlay with valid TLS, authenticated owner gateway and rate limiting without exposing the raw paper DB/server to the public internet.
- Verify effective AWS egress registered IP matches Angel App; validate signed owner JWT server-side against expected owner, enforce strict HTTPS Origin and no CORS wildcard.
- Integrate the broker session *in the same authorized persistent AWS process* that will service authenticated read-only resources. Fail closed on broker 401/403, app restart, midnight, missing verified JWT expiry, logout and owner session revocation.
- Only then opt in to the day-bound read-only session policy and independently live-test login/expiry/revocation with authorized broker API reads, never orders.
- Real auto trading requires a **separate later approval and actual broker order lifecycle tests**, not included here.
