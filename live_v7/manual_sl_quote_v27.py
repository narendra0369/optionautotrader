"""V27 manual NFO position: private Angel read-only LTP lookup.

Only POSTs to documented getLtpData market-data endpoint; it NEVER calls a
broker order/modify/cancel route. Does not set SL prices or submit orders.
Credential prompts remain private in owner-bound RAM session. LTP response
lacks exchange feed timestamp here; receiving a response does NOT prove a
fresh/executable quote, exchange tick, price protection limits or approval.
"""
from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
import json
import ssl
import urllib.request

import angel_gateway
from live_v7.aws_angel_owner_reader import _config, verify_login
from live_v7.angel_books_readonly import read_book
from live_v7.manual_sl_preflight_v26 import assess_manual_positions

API="https://apiconnect.angelone.in"
PATH="/rest/secure/angelbroking/order/v1/getLtpData"
MAX_BYTES=65536

class QuoteBlocked(ValueError):
    pass

def parse_ltp(response, *, symbol:str, token:str)->str:
    if not isinstance(response,dict) or response.get("status") is not True:
        raise QuoteBlocked("LTP_BROKER_FAILED")
    row=response.get("data")
    if not isinstance(row,dict):
        raise QuoteBlocked("LTP_DATA_MISSING")
    if (row.get("exchange")!="NFO" or row.get("tradingsymbol")!=symbol
            or str(row.get("symboltoken"))!=token):
        raise QuoteBlocked("LTP_CONTRACT_MISMATCH")
    value=row.get("ltp")
    if isinstance(value,bool) or not isinstance(value,(str,int,float,Decimal)):
        raise QuoteBlocked("LTP_INVALID")
    try:
        price=Decimal(str(value))
    except (InvalidOperation,ValueError,TypeError):
        raise QuoteBlocked("LTP_INVALID") from None
    if not price.is_finite() or price<=0:
        raise QuoteBlocked("LTP_INVALID")
    return str(price)

def fetch_ltp(owner:str, *, symbol:str, token:str, fetch=None)->str:
    if not angel_gateway._owner_bound(owner):
        raise QuoteBlocked("OWNER_NOT_BOUND")
    session=angel_gateway._clean_session(owner,datetime.now(timezone.utc).timestamp())
    if not session or not session.get("jwt") or not session.get("apiKey"):
        raise QuoteBlocked("BROKER_SESSION_INVALID")
    payload=json.dumps({"exchange":"NFO","tradingsymbol":symbol,"symboltoken":token},
                       separators=(",",":")).encode()
    headers={
        "Accept":"application/json","Content-Type":"application/json",
        "Authorization":"Bearer "+session["jwt"],"X-PrivateKey":session["apiKey"],
        "X-UserType":"USER","X-SourceID":"WEB",
        "User-Agent":"OptionX-Manual-SL-ReadOnlyQuote/1.0",
        **angel_gateway.angel_client_identity_headers(allow_public_lookup=False)
    }
    request=urllib.request.Request(API+PATH,data=payload,headers=headers,method="POST")
    try:
        if fetch is None:
            opener=urllib.request.build_opener(
                angel_gateway.NoRedirect(),
                urllib.request.HTTPSHandler(context=ssl.create_default_context()))
            response=opener.open(request,timeout=10)
        else:
            response=fetch(request,timeout=10)
        with response as stream:
            if getattr(stream,"status",200)!=200:
                raise QuoteBlocked("LTP_HTTP_NOT_200")
            raw=stream.read(MAX_BYTES+1)
        if len(raw)>MAX_BYTES:
            raise QuoteBlocked("LTP_TOO_LARGE")
        obj=json.loads(raw)
        return parse_ltp(obj,symbol=symbol,token=token)
    except QuoteBlocked:
        raise
    except (OSError,ValueError,TypeError,UnicodeError):
        raise QuoteBlocked("LTP_RESPONSE_UNAVAILABLE_OR_INVALID") from None

def run()->int:
    owner=None
    try:
        owner,client=_config()
        verify_login(owner,client)
        pos=read_book(owner,"positions")
        orders=read_book(owner,"orderbook")
        rows=assess_manual_positions(pos["positions"],orders["orders"])
        if len(rows)!=1:
            raise QuoteBlocked("REQUIRES_EXACTLY_ONE_LONG_NFO_POSITION")
        item=rows[0]
        if item["conflictingOrdersRequireHumanReview"]:
            raise QuoteBlocked("EXISTING_ACTIVE_SELL_ORDER")
        ltp=fetch_ltp(owner,symbol=item["contract"],token=item["instrumentToken"])
        print("OWNER_AND_BROKER: PASS")
        print("MANUAL_POSITION_CONTRACT:",item["contract"])
        print("INSTRUMENT_TOKEN:",item["instrumentToken"])
        print("NET_LONG_QUANTITY:",item["netLongQuantity"])
        print("ACTIVE_SELL_ORDERS:",item["activeSellOrders"])
        print("BROKER_LTP:",ltp)
        print("LTP_RECEIVED_UTC:",datetime.now(timezone.utc).isoformat())
        print("BROKER_FEED_TIMESTAMP_VERIFIED: NO")
        print("TICK_SIZE_AND_LPP_VERIFIED: NO")
        print("STOP_TRIGGER_LIMIT: NOT_SET")
        print("REAL_ORDERS: OFF | MANUAL_POSITION: UNTOUCHED")
        return 0
    except Exception:
        print("V27_MANUAL_QUOTE_BLOCKED: PRIVATE_LOGIN_OR_BROKER_DATA_INVALID")
        print("REAL_ORDERS: OFF | MANUAL_POSITION: UNTOUCHED")
        return 2
    finally:
        if owner:
            try:angel_gateway.disconnect(owner)
            except Exception:pass

if __name__=="__main__":
    raise SystemExit(run())
