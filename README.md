# OptionX 200K Strategy Lab — Web research dashboard

This is a **working, paper/research-only** web application for NIFTY, BANKNIFTY and BTC. It contains 200,000 deterministically generated unique rule configurations, CSV loading, computation in a browser Web Worker, 70/30 training/holdout separation, ranked training results with out-of-sample statistics, CSV/JSON export, real Supabase email/password login and RLS-protected saved runs.

## Start it

- On Windows double-click `START_LOCAL_WINDOWS.bat` (requires Python), or upload these source files to a static website hosting service (Render Static Site: publish directory `.` and build command `echo Ready`).
- Website users sign up with an email and password, confirm their email if requested, and sign in.
- In Strategy Lab choose NIFTY / BANKNIFTY / BTC, upload a **15-minute** OHLC CSV with `time,open,high,low,close` headings, in ascending time order; 100+ bars and under 50 MB. The engine checks the median interval for 15 minutes and rejects bad values.
- Choose a scan size: **2,000 (quick), 20,000 (extended), or all 200,000**. Screening may take minutes or longer on phones; the Worker reports progress and supports Stop.
- Check in-sample rank, **out-of-sample win rate**, trade count, net R and drawdown. Export CSV or JSON.
- The training screen defaults to the latest 1,500 training candles; choose 3,000 or *all training candles* to change that. 30% of candles are held out for validation and do not influence screening.

## Strategy count and reproducibility

`5 signals × 5 filters × 4 exits × 4 ATR stop multiples × 5 reward multiples × 5 indicator periods × 20 price-entry momentum buffers = 200,000`.

Scanned strategy IDs use the deterministic permutation `id = (step × 104729) mod 200000` to avoid a biased quick scan. All 200,000 IDs are visited exactly once in the exhaustive scan. Only the **top 40 training-ranked** candidates get holdout validation to avoid leakage from using holdout to select configurations.

## What this does **not** do

- Does not connect a broker; does not place ANY orders, live or paper orders; not auto trading.
- Does not fetch exchange or paid historical market data. No data is preloaded. Data must come from a licensed source or user's own CSV export.
- Does not prove profitability or a future win rate. No backtest results exist until you upload actual candles and run the engine. In-sample search over 200k candidates entails **severe multiple-testing/overfitting risk**; even a positive OOS result needs independent forward testing.
- Index price candles are **not options premiums**; the engine gives strategy signal behavior in **R units**, not genuine CE/PE profit or leverage-adjusted return. Real options P&L would require each option's contract-specific premium history, strikes, expiries, fills, fees, and slippage. BTC candle backtests do not account for perpetual futures funding, liquidation, leverage, exchange outages or contract details.
- Broker credentials must never be entered into this web application.

## Auth and privacy

Only the Supabase `sb_publishable_` client key is included in the frontend. This is intentionally public; never include a service key. This deployment uses the already-connected **ZELQORIS-DB** Supabase project for Supabase Auth and an isolated `optionx_backtest_runs` table. This means the authentication user pool is shared with that project; a dedicated Supabase project is recommended for long-term isolation. Candles are processed in the browser and **not** persisted. Saved backtest summaries use RLS (`auth.uid() = user_id`). The administrator must ensure Auth's Redirect URL list and email confirmation work for the final website domain; changing the existing project Site URL may affect the marketplace, so do not change it without reviewing dependencies.

## Development checks

Run `node tests.mjs` to verify the 200k unique configurations, CSV validation, 1000 deterministic test candidates, and finite results. Tests use a **synthetic** 380-bar series and are **not** market-performance proof.

## Security and production checklist

Static hosting over HTTPS; Supabase Auth enabled; row-level security applied via `schema.sql`; password reset/email redirect settings verified; CDN library loaded; HTTPS and CORS in place; no secret keys in the repo; regression backtests against actual contract-level data; independent backtest engine audit before any broker integration. For high-volume SaaS usage, move the 200k jobs to a proper server-side queue and implement per-user quotas, persistence and abuse limits.

## V2 — Charts and no-CSV backtest flow (23 November 2026)

- New **Live Charts** navigation offers NIFTY, BANKNIFTY, Bitcoin (BTC/USD Kraken spot), and 1m / 5m / 15m / 30m / 1h / 4h / 1d candle intervals.
- Separate **read-only** Render Python feed service exposes `/health` and `/api/candles?market=NIFTY&timeframe=15m` with strict fixed symbol/timeframe allowlist. No broker API secrets or orders. The frontend polls about every 45 seconds while chart page is open; this is NOT a licensed tick-by-tick real-time NSE feed.
- Indian indices: unofficial Yahoo Finance endpoint (potentially delayed and may be blocked/unavailable), with short intraday historical lookback. Do not advertise as real-time NSE exchange data. Bitcoin: Kraken public OHLC BTC/USD (spot, not futures). Kraken provides up to 720 recent candles per request, may include incomplete last candle.
- 'Backtest this timeframe' sends only the **completed** selected candles to Strategy Lab, enabling 2,000 / 20,000 / 200,000 combination scans and train/holdout results. Current candle excluded; no made-up prices. The CSV import is retained and its interval is validated against the selected timeframe.
- The current Render Static Site build command copies `index.html styles.css app.mjs engine.mjs engine.worker.mjs` only. For deployment, `chart.mjs` is embedded in `app.mjs` between BEGIN/END EMBEDDED CANDLE VIEWER markers; `chart.mjs` remains pure-source module for unit tests. If future features are added to `chart.mjs`, regenerate this embedded section or update the static site build command to copy it and restore the module import.
- The existing Supabase table gets nullable/default `timeframe` column to persist run timescale alongside source and results. SQL migration in `timeframe_migration.sql`.
- For live, legally authorized 1-minute NIFTY/BANKNIFTY ticks and options premium backtests, a separately contracted/licensed market feed and contract-specific data are still required. Yahoo data is indicative; provider failure is surfaced as an error and never replaced with fictional candles.

Tests: `node tests.mjs`; `python -m unittest -q test_market_api`; `python market_api.py` for read-only local API. No external packages for API. Browser tests may use mocked market-data response; they do not prove an external market data provider is reachable.

## V3 — Auto Paper + Broker Center (23 Nov 2026)

Paper Auto page allows selecting an exact 1–200000 strategy ID, market, timeframe, initial capital, per-entry risk, daily realized loss guard, 1–5 trades/day, cost and slippage assumptions. The same strategy ID can be selected directly from a ranked backtest via **Paper →**. There is one RLS-isolated Supabase state account per user per market, saved with an optimistic concurrency `version` guard; the most recent 100 closed paper trades are kept in that account's JSON state. SQL: `paper_migration.sql`. No broker tokens are kept in a browser or Supabase.

**Critical scope of the simulation:**

- Trading is *automatic only while a signed-in browser tab stays actively open*, with a 45-second polling attempt and catch-up fail-closed for missed bars. Closing/suspending the browser stops it. This is not server-side unattended 24/7 execution.
- Bar-close replay: a signal is calculated after a bar closes, and an entry at the next bar open is known and accounted for **only once that next bar closes**. It is not a live quote, futures or options fill. A start/restart never replays historic trades.
- Paper signals use exactly the same 200,000 `configAt` strategy IDs and `signalFor`/`prepare` indicator logic as the backtester. Closing same-bar SL/TP both touched assumes stop first, with gap-down/up stop price worse than stop where appropriate. Configurable costs/slippage are charged; linear units never leverage. Maximum notional is virtual capital. Gap circuit breaker prevents disconnected backfills.
- Default NIFTY and BANKNIFTY paper capital ₹100,000, entry risk ₹300, daily realized loss guard ₹600, max 2 entries/day; they are *not tradeable index option contracts*. Default BTC paper capital $10,000, entry risk $15, daily realized loss $30 and max 2 entries/day. The loss guard is a rule for entries, not a guaranteed hard loss cap; overnight gaps may exceed it.
- User actions: Start Paper Auto, Stop Entries, Emergency Paper Flatten at last completed candle close, Sync/Check Signals, Reset while flat, private paper ledger.
- Broker center links to official Zerodha, Angel One, DhanHQ and Delta API docs. There is **no genuine broker login, OAuth flow or live trading in V3**; live order capability is deliberately hard-disabled until separate, tested secure server adapters, broker credentials via secure provider flows, exchange-authorized contract-level data, postback/WebSocket order reconciliation and recovery tests, broker and statutory compliance, and explicit authorization.
- The site's Render static build command uses a fixed file-copy allowlist. `node tests.mjs` stages `paper_engine.mjs` and `paper_ui.mjs` in `dist/` before the Render command copies the other frontend files, avoiding any Render service changes. Test command: `node tests.mjs`.

## V4 — Secure Live Broker Preparation (real orders OFF)

- A new `#live` tab offers a broker selection (Zerodha / Angel One / Dhan / Delta), strategy-ID selection, and a read-only LIMIT order readiness preview. There is **no broker OAuth flow implemented yet** and no credential entry on the public page.
- The backend verifies the signed-in Supabase access token using its Auth `/auth/v1/user` API before returning account-specific readiness status or preview results. The publishable key is safe for browser use; never place a service role key in the frontend.
- Gateway endpoints:
  - `GET /api/live/capabilities` (public list of supported broker integrations, no linked credentials)
  - `GET /api/live/status` (requires valid Supabase access token; returns LOCKED)
  - `POST /api/live/preflight` (requires valid Supabase access token; returns BLOCKED preview; no broker calls)
  - `POST /api/live/orders`, `/api/live/arm`, `/api/live/connect` etc. all respond **423 REAL_ORDERS_HARD_LOCKED**; no order execution code exists.
- 2026 NSE/SEBI retail algo rules require broker-approved retail algo/client-direct API and whitelisted static IP where applicable. A free Render-hosted market feed is **not** a compliant execution host. Use an approved broker-controlled runtime or broker-approved dedicated static-IP infrastructure, account-specific authenticated sessions, instrument-master mapping, broker LTP and margin/risk gates, order reconciliation, duplicate-idempotency handling, outage recovery, audit logging and an independently verified kill switch **before** considering live permission.
- Public Yahoo index candles and Kraken spot candles are NOT executable NFO option premiums, Indian futures quotes or Delta contract prices. Real fills must never be simulated from those feeds.
- Build regression: `node tests.mjs && python -m unittest -q test_market_api test_live_gateway`. Current Render static build already runs `node tests.mjs`, which copies the extra frontend modules to `dist/`.
- Deployment remains on the isolated OptionX branch, preserving `main` and ZELQORIS. No secrets requested or modified.

## V5 — Angel One + Delta India dual-broker routing (23 Nov 2026)

This upgrade focuses on **Angel One SmartAPI** for NIFTY/BANKNIFTY option/future preparation and **Delta Exchange India** for BTC perpetual future / option research. Existing paper-auto and strategy screens remain unchanged.

1. Log in to `https://optionx-200k-strategy-lab.onrender.com/#live`.
2. Press **Save Angel + Delta routing**. The optional `optionx_broker_routes` Supabase table stores only `user_id`, `market`, `broker` and timestamp under individual row-level security. No API key, PIN, OTP, private token, credential or approval bit is persisted.
3. Under **Delta India · Real BTC Contract Explorer**, choose futures/perpetual or options and press **Load BTC contracts**. This calls Delta's **public** `/v2/products` endpoint through the Python market feed, filters to BTC and displays the first page (not an exhaustive symbol master). It can fail when Delta returns no results or blocks the host. Selecting a currently live/operational product populates the **order preview only**; does NOT connect the private trading account or place orders.
4. On **Live Charts**, choose BTC + **Delta India BTCUSD Perpetual** to load the official read-only `/v2/history/candles` BTCUSD derivatives feed for 1m / 5m / 15m / 30m / 1h / 4h / 1d (<=700 completed bars). You can use these candles for *signal-only* backtesting; futures P&L needs the correct contract multiplier, funding, margin and execution costs. Kraken spot remains separately selectable.
5. For Angel One, check the official SmartAPI documentation and register the broker-approved **static IPv4** for API order requests. Full SmartAPI client-auth, NFO instrument master, broker quotes, account order status/fills, and live execution are **not connected** in V5.

Endpoint matrix (Python read-only service):

- `GET /api/brokers/catalog` — signed-in OPTIONX user; broker mapping and readiness.
- `GET /api/brokers/delta/products?kind=future|option` — signed-in user; first page of live BTC products from Delta's public product API.
- `GET /api/brokers/delta/product?symbol=BTCUSD` — signed-in user; verifies one public contract.
- `GET /api/brokers/delta/candles?symbol=BTCUSD&timeframe=15m` — public research candles; allowlisted BTC symbols and timeframes; not order-grade.
- All other `/api/brokers/*` POST endpoints respond **HTTP 423**. All `/api/live/orders`, `/api/live/arm`, `/api/live/connect` remain **HTTP 423**. No broker API credentials or signed private requests are implemented.

`node tests.mjs && python -m unittest -q test_market_api` runs local synthetic regressions. Build command on existing Render Static Site is fixed, so tests stage supplemental JS modules into `dist/` before the original copy step; in addition the chart is intentionally bundled into `app.mjs` to support existing deployments. The Python service's existing build command automatically imports `dual_brokers.py` through `market_api.py` and includes `test_dual_brokers.py` through `test_market_api.py`. **No change to the site's main branch or ZELQORIS marketplace service.**

**Release gate before any live auto-trading:** independent owner-only credential vault and authentication, broker-compliant static IP and exchange algo approvals, exact derivative contract mapping, live broker quotes and RMS limits, broker order-status WebSocket/postback with idempotency and recovery, durable encrypted audit trail, tested emergency kill switch and explicit separately approved trade-permission opt-in. The publicly hosted Render research server is not an approved live order executor. Do not share API credentials in chat or the public readiness page.
