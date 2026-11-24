"""Staging-only Angel One NFO instrument master and quote-only SmartAPI bridge.

Cannot place, change, cancel or reconcile real orders. Uses the temporary
owner-matched, profile-verified RAM session; credentials never leave server.
Official instrument-master file is streamed and reduced to current NFO index
contracts. No fabricated spot, price, contract ID or executed fills.
"""
from __future__ import annotations
import codecs
from datetime import datetime, date, timezone, timedelta
from decimal import Decimal, InvalidOperation
import io
import json
import os
import re
import ssl
import threading
import time
import urllib.error
import urllib.request
from zoneinfo import ZoneInfo

import angel_gateway
from live_v7.read_only_transport import NoRedirect, ReadOnlyTransportError

MASTER_URL = "https://margincalculator.angelbroking.com/OpenAPI_File/files/OpenAPIScripMaster.json"
LTP_URL = "https://apiconnect.angelone.in/rest/secure/angelbroking/order/v1/getLtpData"
MAX_MASTER_BYTES = 75 * 1024 * 1024
TTL_SECONDS = 4 * 60 * 60
_ALLOWED = {"NIFTY", "BANKNIFTY"}
_SYMBOL = re.compile(r"^(NIFTY|BANKNIFTY)[A-Z0-9._-]{4,65}$")
_DIGITS = re.compile(r"^[0-9]{2,14}$")
_LOCK = threading.RLock()
_CACHE = {"loaded": 0.0, "contracts": {}, "asof": ""}
_LAST_QUOTE = {}

class MarketDataError(ValueError):
    def __init__(self, code: str):
        super().__init__("Verified Angel market data unavailable")
        self.code = code

def _decimal(value, *, positive=True) -> Decimal:
    if isinstance(value, bool) or not isinstance(value, (int, float, str, Decimal)):
        raise MarketDataError("INVALID_INSTRUMENT_NUMBER")
    try:
        x = Decimal(str(value))
    except (InvalidOperation, ValueError):
        raise MarketDataError("INVALID_INSTRUMENT_NUMBER") from None
    if not x.is_finite() or (positive and x <= 0):
        raise MarketDataError("INVALID_INSTRUMENT_NUMBER")
    return x

def _stream_json_array(handle):
    """Stream potentially large official JSON array without materializing 150k rows.

    Each element is bounded to 1MB and the total input to 75MB.
    Reject truncated, malformed or unexpected top-level input.
    """
    decoder = json.JSONDecoder()
    utf8 = codecs.getincrementaldecoder("utf-8")()
    buffer, index, started, total = "", 0, False, 0
    while True:
        while True:
            while index < len(buffer) and buffer[index].isspace():
                index += 1
            if not started:
                if index >= len(buffer): break
                if buffer[index] != "[":
                    raise MarketDataError("INSTRUMENT_MASTER_FORMAT")
                started, index = True, index + 1
                continue
            while index < len(buffer) and (buffer[index].isspace() or buffer[index] == ","):
                index += 1
            if index >= len(buffer): break
            if buffer[index] == "]":
                if buffer[index + 1:].strip():
                    raise MarketDataError("INSTRUMENT_MASTER_FORMAT")
                return
            if buffer[index] != "{":
                raise MarketDataError("INSTRUMENT_MASTER_FORMAT")
            try:
                item, end = decoder.raw_decode(buffer, index)
            except json.JSONDecodeError:
                break
            if not isinstance(item, dict):
                raise MarketDataError("INSTRUMENT_MASTER_FORMAT")
            yield item
            index = end
            if index > 64 * 1024:
                buffer, index = buffer[index:], 0
        if len(buffer) - index > 1024 * 1024:
            raise MarketDataError("INSTRUMENT_MASTER_OVERSIZED_ROW")
        chunk = handle.read(64 * 1024)
        if not isinstance(chunk, (bytes, bytearray)):
            raise MarketDataError("INSTRUMENT_MASTER_FORMAT")
        total += len(chunk)
        if total > MAX_MASTER_BYTES:
            raise MarketDataError("INSTRUMENT_MASTER_OVERSIZED")
        if not chunk:
            raise MarketDataError("INSTRUMENT_MASTER_TRUNCATED")
        try:
            buffer += utf8.decode(chunk)
        except UnicodeDecodeError:
            raise MarketDataError("INSTRUMENT_MASTER_ENCODING") from None

def _row(item, today):
    if item.get("exch_seg") != "NFO":
        return None
    market = item.get("name")
    if market not in _ALLOWED:
        return None
    typ = item.get("instrumenttype")
    if typ not in ("OPTIDX", "FUTIDX"):
        return None
    symbol, token = item.get("symbol"), item.get("token")
    if not isinstance(symbol, str) or not _SYMBOL.fullmatch(symbol):
        return None
    if not isinstance(token, str) or not _DIGITS.fullmatch(token):
        return None
    try:
        expiry = datetime.strptime(item["expiry"].upper(), "%d%b%Y").date()
    except (ValueError, AttributeError, KeyError, TypeError):
        return None
    if expiry < today or (expiry - today).days > 180:
        return None
    try:
        lot = int(item["lotsize"])
        tick = _decimal(item["tick_size"]) / 100
        if not (1 <= lot <= 10000) or not (Decimal("0.01") <= tick <= Decimal("100")):
            return None
        if typ == "OPTIDX":
            side = symbol[-2:]
            if side not in ("CE", "PE"):
                return None
            strike = _decimal(item["strike"]) / 100
            if not (Decimal("100") < strike < Decimal("500000")):
                return None
        else:
            side, strike = "FUT", None
    except (MarketDataError, ValueError, KeyError, TypeError):
        return None
    return {
        "market": market, "symbol": symbol, "token": token, "exchange": "NFO",
        "instrumentType": typ, "side": side, "expiry": expiry.isoformat(),
        "strike": float(strike) if strike is not None else None,
        "lotSize": lot, "tickSize": float(tick),
    }

def _open_url(url: str, timeout: int):
    opener = urllib.request.build_opener(
        NoRedirect(), urllib.request.HTTPSHandler(context=ssl.create_default_context()))
    return opener.open(urllib.request.Request(url, headers={"Accept":"application/json",
               "User-Agent":"OptionX-NFO-Master-Readonly/1.0"}), timeout=timeout)

def _get_master(*, fetch=None, clock=None):
    now = time.time() if clock is None else clock
    with _LOCK:
        if _CACHE["contracts"] and 0 <= now - _CACHE["loaded"] < TTL_SECONDS:
            return _CACHE["contracts"], _CACHE["asof"]
    try:
        response = fetch(MASTER_URL, timeout=30) if fetch else _open_url(MASTER_URL, 30)
        today = datetime.fromtimestamp(now, ZoneInfo("Asia/Kolkata")).date()
        contracts = {}
        with response as handle:
            for item in _stream_json_array(handle):
                row = _row(item, today)
                if row:
                    token = row["token"]
                    if token in contracts and contracts[token] != row:
                        raise MarketDataError("MASTER_DUPLICATE_TOKEN")
                    contracts[token] = row
                    if len(contracts) > 40000:
                        raise MarketDataError("INSTRUMENT_MASTER_LIMIT")
        if not contracts:
            raise MarketDataError("INSTRUMENT_MASTER_EMPTY")
    except MarketDataError:
        raise
    except (urllib.error.URLError, TimeoutError, OSError, ValueError):
        raise MarketDataError("INSTRUMENT_MASTER_UNAVAILABLE") from None
    asof = datetime.fromtimestamp(now,timezone.utc).isoformat()
    with _LOCK:
        _CACHE.update(loaded=now, contracts=contracts, asof=asof)
    return contracts, asof

def _owner(user_id):
    if not angel_gateway._owner_bound(user_id):
        raise MarketDataError("OWNER_NOT_VERIFIED")
    session = angel_gateway._clean_session(user_id, time.time())
    if not session or not isinstance(session.get("apiKey"),str) or not isinstance(session.get("jwt"),str):
        raise MarketDataError("ANGEL_SESSION_EXPIRED")
    return session

def list_contracts(user_id, market, side, *, strike=None, fetch=None, clock=None):
    _owner(user_id)
    if market not in _ALLOWED or side not in ("CE","PE","FUT"):
        raise MarketDataError("INVALID_CONTRACT_FILTER")
    wanted = None
    if strike is not None and strike != "":
        wanted = _decimal(strike)
        if not Decimal("100") < wanted < Decimal("500000"):
            raise MarketDataError("INVALID_CONTRACT_FILTER")
    contracts,asof = _get_master(fetch=fetch,clock=clock)
    rows=[x for x in contracts.values() if x["market"]==market and x["side"]==side]
    if not rows:
        raise MarketDataError("NO_VERIFIED_CONTRACTS")
    nearest_expiry = min(x["expiry"] for x in rows)
    rows=[x for x in rows if x["expiry"]==nearest_expiry]
    rows.sort(key=lambda x:(abs(Decimal(str(x["strike"]))-wanted) if wanted is not None and x["strike"] is not None else Decimal(str(x["strike"] or 0)),x["symbol"]))
    return {
        "broker":"Angel","market":market,"side":side,"expiry":nearest_expiry,
        "masterAsOf":asof,"totalMatchingExpiry":len(rows),
        "contracts":rows[:30],"quotesValidated":False,"realOrderEnabled":False,
        "liveExecutionEnabled":False,"orderExecutionEnabled":False,"canSubmitOrder":False,
        "notice":"Official Angel instrument metadata. Contracts can expire; this is NOT a quote or order authorization.",
    }

def quote_ltp(user_id, token, *, master_fetch=None, quote_fetch=None, clock=None):
    session = _owner(user_id)
    if not isinstance(token,str) or not _DIGITS.fullmatch(token):
        raise MarketDataError("INVALID_INSTRUMENT_TOKEN")
    master,asof = _get_master(fetch=master_fetch,clock=clock)
    contract = master.get(token)
    if not contract:
        raise MarketDataError("UNVERIFIED_INSTRUMENT_TOKEN")
    now = time.time() if clock is None else clock
    with _LOCK:
        if now - _LAST_QUOTE.get(user_id, 0.0) < 3:
            raise MarketDataError("QUOTE_POLL_RATE_LIMIT")
        _LAST_QUOTE[user_id] = now
    try:
        from angel_gateway import angel_client_identity_headers
        headers = {
            "Accept":"application/json","Content-Type":"application/json",
            "User-Agent":"OptionX-Angel-QuoteReadonly/1.0",
            "Authorization":"Bearer "+session["jwt"],"X-PrivateKey":session["apiKey"],
            "X-UserType":"USER","X-SourceID":"WEB",
            **angel_client_identity_headers(allow_public_lookup=quote_fetch is None),
        }
        payload = json.dumps({"exchange":"NFO","tradingsymbol":contract["symbol"],
                              "symboltoken":contract["token"]}).encode()
        req=urllib.request.Request(LTP_URL, data=payload, headers=headers, method="POST")
        if quote_fetch is not None:
            response=quote_fetch(req,timeout=10)
        else:
            response=urllib.request.build_opener(
                NoRedirect(),urllib.request.HTTPSHandler(context=ssl.create_default_context())
            ).open(req,timeout=10)
        with response as handle:
            raw=handle.read(32769)
            if getattr(handle,"status",200)!=200 or len(raw)>32768:
                raise MarketDataError("BROKER_QUOTE_BAD_RESPONSE")
        result=json.loads(raw)
    except MarketDataError:
        raise
    except (OSError,TimeoutError,urllib.error.URLError,ValueError):
        raise MarketDataError("BROKER_QUOTE_UNAVAILABLE") from None
    if not isinstance(result,dict) or result.get("status") is not True or not isinstance(result.get("data"),dict):
        raise MarketDataError("BROKER_QUOTE_REJECTED")
    data=result["data"]
    if (data.get("exchange")!="NFO" or data.get("tradingsymbol")!=contract["symbol"]
            or str(data.get("symboltoken"))!=token):
        raise MarketDataError("BROKER_QUOTE_CONTRACT_MISMATCH")
    price = _decimal(data.get("ltp"))
    if price>Decimal("10000000"):
        raise MarketDataError("BROKER_QUOTE_BAD_PRICE")
    return {
        "broker":"Angel","source":"Angel SmartAPI Get LTP Data",
        "contract":contract,"ltp":float(price),"observedAt":datetime.fromtimestamp(now,timezone.utc).isoformat(),
        "masterAsOf":asof,"exchangeTimestampVerified":False,
        "executionPriceVerified":False,"quoteFreshnessVerified":False,
        "liveExecutionEnabled":False,"orderExecutionEnabled":False,"canSubmitOrder":False,
        "notice":"Read-only indicative last traded price; no exchange timestamp verification, margin or execution permission.",
    }


CANDLES_URL = "https://apiconnect.angelone.in/rest/secure/angelbroking/historical/v1/getCandleData"
_LAST_CANDLES = {}

def historical_15m(user_id, token, *, days=3, master_fetch=None, candle_fetch=None, clock=None):
    """On-demand 15-minute NFO OHLC (up to 7 calendar days), not a fill model.

    Uses broker's fixed historical-candle REST query (POST, read semantics).
    Rejects invented tokens, unexpected intervals, implausible OHLC, duplicate
    timestamps, future/incomplete bars and owner/session mismatches.
    """
    session = _owner(user_id)
    if not isinstance(token, str) or not _DIGITS.fullmatch(token):
        raise MarketDataError("INVALID_INSTRUMENT_TOKEN")
    if isinstance(days,bool) or not isinstance(days,int) or days not in (1,2,3,5,7):
        raise MarketDataError("INVALID_CANDLE_WINDOW")
    master,asof = _get_master(fetch=master_fetch,clock=clock)
    contract=master.get(token)
    if not contract:
        raise MarketDataError("UNVERIFIED_INSTRUMENT_TOKEN")
    now=time.time() if clock is None else clock
    with _LOCK:
        if now - _LAST_CANDLES.get(user_id,0.0) < 10:
            raise MarketDataError("CANDLE_POLL_RATE_LIMIT")
        _LAST_CANDLES[user_id]=now
    ist=ZoneInfo("Asia/Kolkata")
    end=datetime.fromtimestamp(now,ist)
    start=end-timedelta(days=days)
    datestr=lambda x: x.strftime("%Y-%m-%d %H:%M")
    try:
        from angel_gateway import angel_client_identity_headers
        headers={
            "Accept":"application/json","Content-Type":"application/json",
            "User-Agent":"OptionX-Angel-CandlesReadonly/1.0",
            "Authorization":"Bearer "+session["jwt"],"X-PrivateKey":session["apiKey"],
            "X-UserType":"USER","X-SourceID":"WEB",
            **angel_client_identity_headers(allow_public_lookup=candle_fetch is None),
        }
        body=json.dumps({
           "exchange":"NFO","symboltoken":contract["token"],
           "interval":"FIFTEEN_MINUTE",
           "fromdate":datestr(start),"todate":datestr(end)
        }).encode()
        req=urllib.request.Request(CANDLES_URL,data=body,headers=headers,method="POST")
        response=(candle_fetch(req,timeout=12) if candle_fetch else
                  urllib.request.build_opener(
                    NoRedirect(),urllib.request.HTTPSHandler(context=ssl.create_default_context())
                  ).open(req,timeout=12))
        with response as handle:
            raw=handle.read(262145)
            if getattr(handle,"status",200)!=200 or len(raw)>262144:
                raise MarketDataError("BROKER_CANDLES_BAD_RESPONSE")
        result=json.loads(raw)
    except MarketDataError:
        raise
    except (OSError,TimeoutError,urllib.error.URLError,ValueError):
        raise MarketDataError("BROKER_CANDLES_UNAVAILABLE") from None
    if not isinstance(result,dict) or result.get("status") is not True:
        raise MarketDataError("BROKER_CANDLES_REJECTED")
    data=result.get("data")
    if not isinstance(data,list) or len(data)>700:
        raise MarketDataError("BROKER_CANDLES_BAD_FORMAT")
    bars=[]
    seen=set()
    for rawrow in data:
        if not isinstance(rawrow,list) or len(rawrow)<5 or len(rawrow)>7:
            raise MarketDataError("BROKER_CANDLES_BAD_FORMAT")
        try:
            stamp=datetime.fromisoformat(rawrow[0])
            if stamp.tzinfo is None:
                stamp=stamp.replace(tzinfo=ist)
            ts=int(stamp.timestamp()*1000)
            o,h,l,c=[_decimal(v) for v in rawrow[1:5]]
            v=_decimal(rawrow[5],positive=False) if len(rawrow)>5 else Decimal(0)
        except (TypeError,ValueError,MarketDataError):
            raise MarketDataError("BROKER_CANDLES_BAD_FORMAT") from None
        if (ts in seen or h<max(o,c) or l>min(o,c) or l>h or
            v<0 or h>Decimal("10000000")):
            raise MarketDataError("BROKER_CANDLES_INVALID_OHLC")
        seen.add(ts)
        # Only completed candles can be used for historical research.
        if ts + 15*60*1000 > int(now*1000)-5000:
            continue
        if ts < int(start.timestamp()*1000)-15*60*1000:
            raise MarketDataError("BROKER_CANDLES_OUTSIDE_WINDOW")
        bars.append({"time":ts,"open":float(o),"high":float(h),"low":float(l),
                     "close":float(c),"volume":float(v)})
    bars.sort(key=lambda x:x["time"])
    return {
        "broker":"Angel","source":"Angel SmartAPI historical FIFTEEN_MINUTE",
        "contract":contract,"timeframe":"15m","bars":bars,"barCount":len(bars),
        "from":datestr(start),"to":datestr(end),"masterAsOf":asof,
        "observedAt":datetime.fromtimestamp(now,timezone.utc).isoformat(),
        "historical":True,"fillPricesVerified":False,"costsOrSlippageIncluded":False,
        "liveExecutionEnabled":False,"orderExecutionEnabled":False,"canSubmitOrder":False,
        "notice":"Historical contract OHLC only. No lookahead, executable quote, slippage/charges, margin or order permission."
    }
