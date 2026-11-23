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
