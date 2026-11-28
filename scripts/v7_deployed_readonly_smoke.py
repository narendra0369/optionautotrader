"""Read-only verification of deployed OptionX V7 staging services.

No account credentials, cookies, broker private routes or order submission.
Fails if backend health ceases to explicitly declare real orders disabled.
Provider OHLC is research data; this DOES NOT certify broker fills or auto trading.
"""
from __future__ import annotations

import json
import sys
import time
from datetime import datetime, timezone
from urllib.parse import urlencode
from urllib.request import Request, urlopen

ROOT = "https://optionx-v7-offline-test-staging.onrender.com"
EXPECTED_MARKETS = ("NIFTY", "BANKNIFTY", "BTC")
TF = "15m"
TIMEFRAME_MS = 900_000


def read(path: str) -> dict:
    req = Request(
        ROOT + path,
        headers={"Accept": "application/json", "User-Agent": "OptionX-V7-StagingSmoke/1.0"},
        method="GET",
    )
    last_error: Exception | None = None
    for attempt in range(3):
        try:
            with urlopen(req, timeout=25) as response:
                if response.status != 200:
                    raise AssertionError(f"Unexpected HTTP {response.status}")
                if response.headers.get("Content-Type", "").split(";")[0].strip() != "application/json":
                    raise AssertionError("Endpoint did not return JSON")
                payload = response.read(2_000_001)
                if len(payload) > 2_000_000:
                    raise AssertionError("Too much data")
                data = json.loads(payload)
                if not isinstance(data, dict):
                    raise AssertionError("Endpoint JSON must be an object")
                return data
        except (OSError, TimeoutError, ValueError) as error:
            last_error = error
            if attempt < 2:
                time.sleep(2 + attempt * 3)
    raise AssertionError(f"Public GET failed after retries: {type(last_error).__name__}") from last_error


def check_health() -> None:
    body = read("/health")
    if body.get("status") != "ok" or body.get("paperOnly") is not True:
        raise AssertionError("Backend health did not confirm paper-only service")
    if body.get("liveOrdersEnabled") is not False:
        raise AssertionError("REAL ORDER LOCK NOT CONFIRMED")
    print("PASS: staging health reports PAPER ONLY, REAL ORDERS OFF")


def check_candles(market: str) -> None:
    path = "/api/candles?" + urlencode({"market": market, "timeframe": TF})
    body = read(path)
    bars = body.get("bars")
    if body.get("market") != market or body.get("timeframe") != TF:
        raise AssertionError(market + ": wrong market/timeframe")
    if not isinstance(bars, list) or len(bars) < 120:
        raise AssertionError(market + ": fewer than 120 source OHLC bars")
    if not isinstance(body.get("provider"), str) or not body["provider"]:
        raise AssertionError(market + ": source attribution missing")
    if body.get("feedType") != ("spot" if market == "BTC" else "indicative-index"):
        raise AssertionError(market + ": wrong feed classification")
    previous = -1
    now_ms = int(datetime.now(timezone.utc).timestamp() * 1000)
    for b in bars:
        if not isinstance(b, dict):
            raise AssertionError(market + ": non-object bar")
        ts = b.get("time")
        if not isinstance(ts, int) or isinstance(ts, bool) or ts <= previous or ts > now_ms + 5 * 60_000:
            raise AssertionError(market + ": unordered/future OHLC")
        vals = [b.get(x) for x in ("open", "high", "low", "close")]
        if not all(isinstance(x, (int, float)) and not isinstance(x, bool) and 0 < x < 1e12 for x in vals):
            raise AssertionError(market + ": invalid OHLC values")
        o, h, l, c = vals
        if h < max(o, c) or l > min(o, c) or h < l:
            raise AssertionError(market + ": inconsistent OHLC")
        previous = ts
    # Do not label an exchange closure as a feed outage. Currency/contract trading
    # readiness is NOT inferred from feed recency or this research proxy.
    print(f"PASS: {market} {TF}, provider={body['provider']}, bars={len(bars)}")


def main() -> int:
    check_health()
    for market in EXPECTED_MARKETS:
        check_candles(market)
    print("PASS: deployed research feeds; no credentialed broker or order checks performed")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except (AssertionError, KeyError, TypeError) as exc:
        print("FAIL: " + str(exc), file=sys.stderr)
        sys.exit(1)
