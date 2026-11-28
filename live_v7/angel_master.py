"""OptionX V7 — Angel NFO instrument-master candidates, research-only.

Master source documented by Angel:
https://margincalculator.angelone.in/OpenAPI_File/files/OpenAPIScripMaster.json

The feed may be temporarily unavailable. Never synthesize a token, expiry,
lot size, strike or tick. Instrument-master membership is NOT proof of
exchange tradability or a valid execution quote. Data must be downloaded and
timestamped by a trusted backend; this module performs NO HTTP calls.

The feed's tick_size and strike columns may use broker-specific scaling.
No conversion is assumed here. An authenticated tick/lot verification is
required separately before allowing any order.
"""
from __future__ import annotations

import re
from datetime import datetime, timedelta
from typing import Any, Iterable, Mapping

MASTER_URL = "https://margincalculator.angelone.in/OpenAPI_File/files/OpenAPIScripMaster.json"
MASTER_MAX_AGE = timedelta(hours=24)
SOURCES = {"NIFTY": "NIFTY", "BANKNIFTY": "BANKNIFTY"}
INSTRUMENT_KINDS = {"CE": "OPTIDX", "PE": "OPTIDX", "FUT": "FUTIDX"}
_SYMBOL = re.compile(r"^[A-Z0-9._-]{4,72}$")
_TOKEN = re.compile(r"^[A-Za-z0-9_-]{1,64}$")


class InstrumentMasterError(ValueError):
    pass


def candidates(
    records: Iterable[Mapping[str, Any]],
    *,
    market: str,
    contract_kind: str,
    downloaded_at: datetime,
    now: datetime,
    limit: int = 30,
) -> dict[str, Any]:
    """Return *unverified* real-master candidates; nothing is executable.

    Neither API products, lot sizes nor expiry weekdays are hardcoded.
    The owner must select a real symbol AND validate broker quote/margin.
    """
    if market not in SOURCES or contract_kind not in INSTRUMENT_KINDS:
        raise InstrumentMasterError("NFO market/contract kind not supported")
    if not isinstance(now, datetime) or now.utcoffset() is None:
        raise InstrumentMasterError("Server timestamp required")
    if not isinstance(downloaded_at, datetime) or downloaded_at.utcoffset() is None:
        raise InstrumentMasterError("Verified feed timestamp required")
    if not timedelta(0) <= now - downloaded_at <= MASTER_MAX_AGE:
        raise InstrumentMasterError("Master missing, stale or from future")
    if not isinstance(limit, int) or isinstance(limit, bool) or not 1 <= limit <= 100:
        raise InstrumentMasterError("Invalid candidate limit")
    if not isinstance(records, (list, tuple)) or len(records) > 250000:
        raise InstrumentMasterError("Invalid source size")

    hits: list[dict[str, Any]] = []
    seen: set[str] = set()
    for raw in records:
        if not isinstance(raw, Mapping):
            continue
        name = raw.get("name")
        segment = raw.get("exch_seg")
        instrument_type = raw.get("instrumenttype")
        symbol = raw.get("symbol")
        token = raw.get("token")
        expiry = raw.get("expiry")
        if (
            name != SOURCES[market] or segment not in ("NFO", "nfo")
            or instrument_type != INSTRUMENT_KINDS[contract_kind]
            or not isinstance(symbol, str) or not _SYMBOL.fullmatch(symbol)
            or not isinstance(token, str) or not _TOKEN.fullmatch(token)
            or token in seen
            or not isinstance(expiry, str)
        ):
            continue
        if contract_kind in ("CE", "PE") and not symbol.endswith(contract_kind):
            continue
        if contract_kind == "FUT" and not symbol.endswith("FUT"):
            continue
        try:
            expiration_day = datetime.strptime(expiry.upper(), "%d%b%Y").date()
        except ValueError:
            continue
        if expiration_day < now.date():
            continue
        lot_raw = raw.get("lotsize")
        if not isinstance(lot_raw, str) or not lot_raw.isdigit():
            continue
        lot = int(lot_raw)
        if not 1 <= lot <= 100000:
            continue
        seen.add(token)
        hits.append({
            "broker": "Angel", "exchange": "NFO", "market": market,
            "kind": contract_kind, "token": token, "symbol": symbol,
            "expiryDate": expiration_day.isoformat(), "lotSizeFromMaster": lot,
            "rawTickValue": str(raw.get("tick_size", ""))[:30],
            "rawStrikeValue": str(raw.get("strike", ""))[:30],
            "downloadedAt": downloaded_at.isoformat(),
            "lotSizeIndependentlyConfirmed": False,
            "tickScaleIndependentlyConfirmed": False,
            "quoteVerified": False,
            "canSubmitOrder": False,
        })
        if len(hits) >= limit * 20:
            break

    hits.sort(key=lambda r: (r["expiryDate"], r["symbol"]))
    return {
        "source": "ANGEL_OFFICIAL_SCRIP_MASTER_CANDIDATES",
        "market": market,
        "kind": contract_kind,
        "count": min(limit, len(hits)),
        "rows": hits[:limit],
        "masterFreshnessChecked": True,
        "brokerQuoteVerified": False,
        "liveOrderExecutionEnabled": False,
        "notice": "Candidate tokens only: confirm tick, spread, lot size, quote, margin and trading status.",
    }
