"""Angel One server-only Option Greeks READ, not an order or execution quote.

Broker API: POST /rest/secure/angelbroking/marketData/v1/optionGreek
Body: name and expirydate, e.g. NIFTY / 26NOV2026.
The broker returns a chain; only the verified selected token's corresponding
strike, expiry and CE/PE are returned to the owner. No browser API credentials.

NOT order automation. Broker reports Greeks without verified exchange quote
timestamp, and theoretical sensitivities are not guaranteed prices or stops.
"""
from __future__ import annotations

from datetime import date, datetime, timezone
from decimal import Decimal, InvalidOperation
import json
import re
import ssl
import threading
import time
import urllib.error
import urllib.request

import angel_gateway
from live_v7.angel_marketdata import _owner, _get_master, MarketDataError

_GREEKS_URL="https://apiconnect.angelone.in/rest/secure/angelbroking/marketData/v1/optionGreek"
_DIGITS=re.compile(r"^[0-9]{2,16}$")
_LIMIT_BYTES=256*1024
_LOCK=threading.Lock()
_LAST={}
_MIN_INTERVAL=8


def _num(value, field, low, high):
    if isinstance(value, bool) or not isinstance(value, (str, int, Decimal)):
        raise MarketDataError("BROKER_GREEKS_NUMERIC_INVALID")
    try:
        result=Decimal(value)
    except (InvalidOperation, ValueError, TypeError):
        raise MarketDataError("BROKER_GREEKS_NUMERIC_INVALID") from None
    if not result.is_finite() or not low <= result <= high:
        raise MarketDataError("BROKER_GREEKS_VALUE_OUT_OF_RANGE")
    return result


def angel_selected_contract_greeks(user_id: str, token: str, *,
                                   master_fetch=None, greeks_fetch=None, clock=None):
    """Read Greek snapshot for a token independently verified in NFO master.

    For unit tests only, master_fetch/greeks_fetch allow fake sources;
    production always uses HTTPS with system CA verification.
    """
    session=_owner(user_id)  # trusted server owner binding + RAM session
    if not isinstance(token,str) or not _DIGITS.fullmatch(token):
        raise MarketDataError("INVALID_INSTRUMENT_TOKEN")
    contracts,master_asof=_get_master(fetch=master_fetch,clock=clock)
    contract=contracts.get(token)
    if not contract or contract.get("exchange")!="NFO" or contract.get("side") not in ("CE","PE"):
        raise MarketDataError("UNVERIFIED_OPTION_CONTRACT")
    if contract.get("market") not in ("NIFTY","BANKNIFTY"):
        raise MarketDataError("UNVERIFIED_OPTION_UNDERLYING")
    try:
        expiry=date.fromisoformat(contract["expiry"]).strftime("%d%b%Y").upper()
    except (TypeError,KeyError,ValueError):
        raise MarketDataError("UNVERIFIED_CONTRACT_EXPIRY") from None
    now=time.time() if clock is None else clock
    with _LOCK:
        if now-_LAST.get(user_id,0)<_MIN_INTERVAL:
            raise MarketDataError("GREEKS_POLL_RATE_LIMIT")
        _LAST[user_id]=now
    try:
        headers={
          "Accept":"application/json",
          "Content-Type":"application/json",
          "User-Agent":"OptionX-Angel-ReadOnlyGreeks/1.0",
          "Authorization":"Bearer "+session["jwt"],
          "X-PrivateKey":session["apiKey"],
          "X-UserType":"USER","X-SourceID":"WEB",
          **angel_gateway.angel_client_identity_headers(allow_public_lookup=greeks_fetch is None),
        }
        req=urllib.request.Request(
           _GREEKS_URL,headers=headers,
           data=json.dumps({"name":contract["market"],"expirydate":expiry},
                           separators=(",",":")).encode("utf-8"),
           method="POST",
        )
        if greeks_fetch is not None:
            response=greeks_fetch(req,timeout=10)
        else:
            response=urllib.request.build_opener(
               angel_gateway.NoRedirect(),
               urllib.request.HTTPSHandler(context=ssl.create_default_context())
            ).open(req,timeout=10)
        with response as handle:
            if getattr(handle,"status",200)!=200:
                raise MarketDataError("BROKER_GREEKS_HTTP_UNAVAILABLE")
            raw=handle.read(_LIMIT_BYTES+1)
            if len(raw)>_LIMIT_BYTES:
                raise MarketDataError("BROKER_GREEKS_RESPONSE_OVERSIZED")
        payload=json.loads(raw)
    except MarketDataError:
        raise
    except (OSError,TimeoutError,urllib.error.URLError,ValueError,UnicodeDecodeError,TypeError):
        raise MarketDataError("BROKER_GREEKS_UNAVAILABLE") from None

    if not isinstance(payload,dict) or payload.get("status") is not True:
        raise MarketDataError("BROKER_GREEKS_NO_DATA")
    rows=payload.get("data")
    if not isinstance(rows,list) or len(rows)>1500:
        raise MarketDataError("BROKER_GREEKS_BAD_RESPONSE")
    target_strike=_num(str(contract.get("strike")), "verified_strike",Decimal("0"),Decimal("500000"))
    hits=[]
    for row in rows:
        if not isinstance(row,dict):
            raise MarketDataError("BROKER_GREEKS_BAD_ROW")
        if row.get("name")!=contract["market"] or row.get("expiry")!=expiry:
            # Full chain may have unrelated rows, but never accept them.
            continue
        strike=_num(row.get("strikePrice"),"strike",Decimal("100"),Decimal("500000"))
        if abs(strike-target_strike)>Decimal("0.01") or row.get("optionType")!=contract["side"]:
            continue
        delta=_num(row.get("delta"),"delta",Decimal("-1"),Decimal("1"))
        gamma=_num(row.get("gamma"),"gamma",Decimal("0"),Decimal("5"))
        theta=_num(row.get("theta"),"theta",Decimal("-10000"),Decimal("10000"))
        vega=_num(row.get("vega"),"vega",Decimal("0"),Decimal("10000"))
        iv=_num(row.get("impliedVolatility"),"impliedVolatility",Decimal("0.01"),Decimal("200"))
        if (contract["side"]=="CE" and delta<=0) or (contract["side"]=="PE" and delta>=0):
            raise MarketDataError("BROKER_GREEKS_DELTA_SIDE_MISMATCH")
        hits.append(dict(delta=float(delta),gamma=float(gamma),theta=float(theta),
                         vega=float(vega),iv=float(iv)))
    if len(hits)!=1:
        raise MarketDataError("BROKER_GREEKS_MATCH_NOT_UNIQUE_OR_UNAVAILABLE")
    return {
       "broker":"Angel","resource":"selectedOptionGreeks",
       "source":"Angel One SmartAPI optionGreek",
       "contract":{"market":contract["market"],"symbol":contract["symbol"],
         "token":token,"expiry":contract["expiry"],"strike":contract["strike"],
         "side":contract["side"],"lotSize":contract["lotSize"],
         "tickSize":contract["tickSize"]},
       "greeks":hits[0],
       "masterAsOf":master_asof,
       "observedAt":datetime.fromtimestamp(now,timezone.utc).isoformat(),
       "brokerSourceAuthenticated":True,
       "exchangeTimestampVerified":False,"executionPriceVerified":False,
       "liveExecutionEnabled":False,"orderExecutionEnabled":False,
       "canSubmitOrder":False,
       "notice":"Authenticated chain snapshot; quote & Greeks exchange timestamp unverified; no live exits, no order authorization.",
    }
