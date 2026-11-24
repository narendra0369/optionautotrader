"""OptionX owner-bound Angel One automatic ATM RESEARCH preview. NO ORDERS.

No manual strike, option premium or Greeks entries: index quote + official
NFO instrument master + current NFO LTP + selected option Greeks are fetched
after a new broker 15-minute candle signal. If any step fails, no premium
and NO trade; never fabricate fill times, orderbook or strategy activation.

This is a deliberately conservative experimental strategy-signal preview,
not the existing 200K backtester or production ORB18 live engine.
"""
from __future__ import annotations
from datetime import datetime, timedelta, time, timezone
from decimal import Decimal, InvalidOperation
import json
import ssl
import threading
import time as systime
import urllib.error
import urllib.request
from zoneinfo import ZoneInfo

import angel_gateway
from live_v7.angel_marketdata import _owner, _get_master, quote_ltp, MarketDataError
from live_v7.angel_greeks import angel_selected_contract_greeks
from live_v7.auto_atm_two_trade import (
   select_atm, paper_greek_exit, schedule_15m, AutoATMBlocked,
)

IST=ZoneInfo("Asia/Kolkata")
LTP_URL="https://apiconnect.angelone.in/rest/secure/angelbroking/order/v1/getLtpData"
CANDLE_URL="https://apiconnect.angelone.in/rest/secure/angelbroking/historical/v1/getCandleData"
INDEX={
 "NIFTY": {"symbol":"Nifty 50","token":"99926000"},
 "BANKNIFTY":{"symbol":"Nifty Bank","token":"99926009"}
}
_ALLOWED_STRATEGIES=("ORB18","EMA")
_LOCK=threading.Lock()
_LAST={}
MIN_POLL_SECS=35


def _get_json(user_id, url, payload, *, fetch=None):
    session=_owner(user_id)
    if url not in (LTP_URL,CANDLE_URL):
        raise MarketDataError("UNSUPPORTED_INDEX_READ")
    headers={
      "Content-Type":"application/json","Accept":"application/json",
      "Authorization":"Bearer "+session["jwt"],"X-PrivateKey":session["apiKey"],
      "X-UserType":"USER","X-SourceID":"WEB","User-Agent":"OptionX-AutoATM-ReadOnly/1.0",
      **angel_gateway.angel_client_identity_headers(allow_public_lookup=fetch is None),
    }
    request=urllib.request.Request(url,method="POST",
             data=json.dumps(payload,separators=(",",":")).encode(),headers=headers)
    try:
        if fetch is not None:
            response=fetch(request,timeout=12)
        else:
            response=urllib.request.build_opener(
                angel_gateway.NoRedirect(),
                urllib.request.HTTPSHandler(context=ssl.create_default_context())
            ).open(request,timeout=12)
        with response as stream:
            if getattr(stream,"status",200)!=200:
                raise MarketDataError("BROKER_INDEX_HTTP_ERROR")
            data=stream.read(262145)
            if len(data)>262144:
                raise MarketDataError("BROKER_INDEX_RESPONSE_TOO_LARGE")
        obj=json.loads(data)
    except MarketDataError:
        raise
    except (OSError,urllib.error.URLError,TimeoutError,ValueError,UnicodeDecodeError,TypeError):
        raise MarketDataError("BROKER_INDEX_READ_UNAVAILABLE") from None
    if not isinstance(obj,dict) or obj.get("status") is not True:
        raise MarketDataError("BROKER_INDEX_DATA_REJECTED")
    return obj.get("data")


def _quote_spot(user_id,market,*,quote_fetch=None):
    config=INDEX[market]
    data=_get_json(user_id,LTP_URL,{"exchange":"NSE",
                   "tradingsymbol":config["symbol"],"symboltoken":config["token"]},
                   fetch=quote_fetch)
    if (not isinstance(data,dict) or data.get("exchange")!="NSE" or
        data.get("tradingsymbol")!=config["symbol"] or
        str(data.get("symboltoken"))!=config["token"]):
        raise MarketDataError("BROKER_INDEX_TOKEN_OR_SYMBOL_MISMATCH")
    try:
        spot=Decimal(str(data.get("ltp")))
        if not spot.is_finite() or not 1000<spot<1000000:
            raise ValueError()
    except (InvalidOperation,ValueError,TypeError):
        raise MarketDataError("BROKER_INDEX_PRICE_INVALID") from None
    return float(spot)


def _read_closed_15m(user_id,market,now,*,candle_fetch=None):
    conf=INDEX[market]
    ist=now.astimezone(IST)
    from_time=(ist-timedelta(days=5)).strftime("%Y-%m-%d %H:%M")
    to_time=ist.strftime("%Y-%m-%d %H:%M")
    data=_get_json(user_id,CANDLE_URL,{
      "exchange":"NSE","symboltoken":conf["token"],
      "interval":"FIFTEEN_MINUTE","fromdate":from_time,"todate":to_time},
      fetch=candle_fetch)
    if not isinstance(data,list) or len(data)>1200:
        raise MarketDataError("BROKER_INDEX_CANDLES_UNAVAILABLE")
    parsed=[]
    last_t=None
    for row in data:
        if not isinstance(row,(list,tuple)) or len(row)<5:
            raise MarketDataError("BROKER_INDEX_CANDLE_SHAPE")
        try:
            at=datetime.fromisoformat(row[0])
            if at.tzinfo is None:
                raise ValueError()
            at=at.astimezone(IST)
            open_,high,low,close=[Decimal(str(q)) for q in row[1:5]]
            if (any(not x.is_finite() or x<=0 for x in (open_,high,low,close))
               or high<max(open_,close) or low>min(open_,close) or high<low):
                raise ValueError()
        except (TypeError,ValueError,InvalidOperation):
            raise MarketDataError("BROKER_INDEX_CANDLE_INVALID") from None
        if last_t is not None and at<=last_t:
            raise MarketDataError("BROKER_INDEX_CANDLE_NOT_MONOTONIC")
        last_t=at
        if at+timedelta(minutes=15)<=now.astimezone(IST):
            parsed.append({"time":at,"open":open_,"high":high,"low":low,"close":close})
    if len(parsed)<25:
        raise MarketDataError("INSUFFICIENT_BROKER_INDEX_15M_CANDLES")
    return parsed


def _ema(vals,period):
    if len(vals)<period:
        raise MarketDataError("EMA_CANDLES_INSUFFICIENT")
    value=sum(vals[:period])/Decimal(period)
    k=Decimal(2)/(Decimal(period)+1)
    result=[None]*(period-1)+[value]
    for price in vals[period:]:
        value=value+k*(price-value)
        result.append(value)
    return result


def _signal(bars,market,strategy,now):
    """Only a NEW 15m close crossing 9/21 EMA or 90min opening range qualifies."""
    local=now.astimezone(IST)
    last=bars[-1]
    if (last["time"].date()!=local.date() or
        last["time"]+timedelta(minutes=15)>local or
        (local-last["time"]-timedelta(minutes=15)).total_seconds()>180):
        return None
    # No signal outside the allowed entry session. Exchange holidays and
    # interruptions are unverified; simulation is never approved for orders.
    if local.weekday()>=5 or not time(9,30)<=local.time()<time(14,45):
        return None
    side=None
    if strategy=="EMA":
        closes=[b["close"] for b in bars]
        fast=_ema(closes,9)
        slow=_ema(closes,21)
        if fast[-2] is None or slow[-2] is None:
            return None
        if fast[-2]<=slow[-2] and fast[-1]>slow[-1]:
            side="CE"
        elif fast[-2]>=slow[-2] and fast[-1]<slow[-1]:
            side="PE"
    elif strategy=="ORB18":
        # Opening range = first 18 FIVE-minute bars = first SIX 15m bars,
        # from 09:15 to 10:45; source is authenticated index 15m.
        today=[b for b in bars if b["time"].date()==local.date()]
        base=datetime.combine(local.date(),time(9,15),IST)
        first=[b for b in today if base<=b["time"]<base+timedelta(minutes=90)]
        if len(first)!=6 or [b["time"] for b in first]!=[
                base+timedelta(minutes=15*i) for i in range(6)]:
            return None
        high=max(b["high"] for b in first)
        low=min(b["low"] for b in first)
        later=[b for b in today if b["time"]>=base+timedelta(minutes=90)]
        if len(later)<2 or later[-2]["time"]+timedelta(minutes=15)!=later[-1]["time"]:
            return None
        if later[-2]["close"]<=high and later[-1]["close"]>high:
            side="CE"
        elif later[-2]["close"]>=low and later[-1]["close"]<low:
            side="PE"
    if not side:
        return None
    return {"side":side,"atIST":last["time"].isoformat(),
            "signalId":market+"_"+strategy+"_"+last["time"].strftime("%Y%m%d_%H%M"),
            "status":"BROKER_INDEX_15M_SIGNAL_PREVIEW_ONLY",
            "fidelityNote":"Experimental EMA 9/21 close cross or ORB first 18×5m equivalent range. Not identical to all Strategy Lab 200K rules."}


def angel_auto_atm_readonly(user_id,market,strategy,*,now=None,
                            index_quote_fetch=None,index_candle_fetch=None,
                            master_fetch=None,option_quote_fetch=None,
                            greek_fetch=None):
    """One owner-verified request, auto-ATM/Greeks only after a fresh signal.

    MUST be gated in HTTP layer by private owner token, staging origin,
    read-only feature flag, and never called in real order gateway.
    """
    if market not in INDEX or strategy not in _ALLOWED_STRATEGIES:
        raise MarketDataError("UNSUPPORTED_AUTO_ATM_REQUEST")
    now=datetime.now(timezone.utc) if now is None else now
    if now.tzinfo is None or now.utcoffset() is None:
        raise MarketDataError("NAIVE_SERVER_CLOCK")
    session=_owner(user_id)
    with _LOCK:
        wall=now.timestamp()
        if wall-_LAST.get(user_id,0)<MIN_POLL_SECS:
            raise MarketDataError("AUTO_ATM_READ_RATE_LIMIT")
        _LAST[user_id]=wall
    sched=schedule_15m(now)
    status={
       "broker":"Angel","mode":"AUTO_ATM_READONLY_RESEARCH",
       "market":market,"strategy":strategy,"signal":None,
       "nextStrategyCheck":sched["nextCheckIST"],"tradingCalendarVerified":False,
       "fillETASeconds":None,"fillTime":"UNKNOWN_UNTIL_BROKER_EXECUTION",
       "dailyEntryHardCap":2,
       "dailyEntryCountVerified":False,"dailyEntryCount":None,
       "selectedContract":None,"exitPlan":None,
       "canSubmitOrder":False,"liveOrdersEnabled":False,
       "notice":"NO REAL ORDERS. Missing historical/index/option/Greeks data fails closed; no fill-time promise. 2-entry shadow policy is not linked to live account."
    }
    bars=_read_closed_15m(user_id,market,now,candle_fetch=index_candle_fetch)
    signal=_signal(bars,market,strategy,now)
    if signal is None:
        status["status"]="WAITING_FOR_NEW_15M_STRATEGY_SIGNAL"
        return status
    status["signal"]=signal
    spot=_quote_spot(user_id,market,quote_fetch=index_quote_fetch)
    contracts,master_asof=_get_master(fetch=master_fetch,clock=now.timestamp())
    try:
        chosen=select_atm(market=market,side=signal["side"],index_spot=spot,
                         observed_at=now,now=now,contracts=list(contracts.values()),
                         authenticated_index_read=True,official_master_verified=True)
    except AutoATMBlocked as exc:
        raise MarketDataError(str(exc)) from None
    option=quote_ltp(user_id,chosen["token"],master_fetch=master_fetch,
                     quote_fetch=option_quote_fetch,clock=now.timestamp())
    greeks=angel_selected_contract_greeks(
       user_id,chosen["token"],master_fetch=master_fetch,
       greeks_fetch=greek_fetch,clock=now.timestamp())
    if (option["contract"]["token"]!=chosen["token"] or
        greeks["contract"]["token"]!=chosen["token"] or
        option.get("canSubmitOrder") is not False or
        greeks.get("canSubmitOrder") is not False):
        raise MarketDataError("BROKER_ATM_OPTION_SOURCE_MISMATCH")
    try:
        exit_plan=paper_greek_exit(selected=chosen,premium=str(option["ltp"]),
            greeks=greeks["greeks"],strategy=strategy,
            lots=1,per_lot_risk=300,reward_ratio=2,scenario_points=10,minutes=15)
    except AutoATMBlocked as exc:
        raise MarketDataError(str(exc)) from None
    status.update(
       status="READONLY_ATM_PREVIEW_READY_NOT_ORDER_ELIGIBLE",
       selectedContract={**chosen,"premium":option["ltp"],
                         "optionLtpExecutionVerified":False,
                         "greeksExchangeTimeVerified":False,
                         "masterAsOf":master_asof},
       exitPlan=exit_plan
    )
    return status
