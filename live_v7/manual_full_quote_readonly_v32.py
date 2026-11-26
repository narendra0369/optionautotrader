"""V32 authenticated Angel FULL market quote, read-only evidence.

Fixed market data endpoint only. NEVER places, modifies or cancels an order.
The exchange feed timestamp is broker-reported, not independently exchange-
authenticated. Quote data cannot establish LPP, entitlement, fees or fill.
"""
from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
import json
import ssl
import urllib.error
import urllib.request

import angel_gateway
from live_v7.aws_angel_owner_reader import _config, verify_login
from live_v7.angel_books_readonly import read_book
from live_v7.manual_sl_preflight_v26 import assess_manual_positions

ROOT = "https://apiconnect.angelone.in"
PATH = "/rest/secure/angelbroking/market/v1/quote"
SYMBOL = "NIFTY29DEC2629000CE"
TOKEN = "38158"
EXPECTED_QTY = 65
LIMIT = Decimal("10.50")
MAX_BYTES = 65536
MAX_BROKER_FEED_AGE_S = 10

class FullQuoteBlocked(ValueError):
    pass


def _positive_decimal(value, label):
    if isinstance(value, bool) or not isinstance(value, (str,int,float,Decimal)):
        raise FullQuoteBlocked(label+"_INVALID")
    try:
        result=Decimal(str(value))
    except (ValueError,TypeError,InvalidOperation):
        raise FullQuoteBlocked(label+"_INVALID") from None
    if not result.is_finite() or result <= 0:
        raise FullQuoteBlocked(label+"_INVALID")
    return result


def _exchange_time(raw):
    # Do not guess missing timezone; Angel's local trading timestamps must
    # explicitly use Asia/Kolkata offset here, never server local time.
    from datetime import timedelta
    ist = timezone(timedelta(hours=5, minutes=30))
    if isinstance(raw,bool) or raw is None:
        return None
    if isinstance(raw,(int,float)) or (isinstance(raw,str) and raw.isdigit()):
        try:
            value=float(raw)
            if value > 1e12:
                value/=1000.0
            return datetime.fromtimestamp(value,timezone.utc)
        except (ValueError,OverflowError,OSError):
            return None
    if not isinstance(raw,str):
        return None
    try:
        dt=datetime.fromisoformat(raw.replace("Z","+00:00"))
        if dt.tzinfo:
            return dt.astimezone(timezone.utc)
    except ValueError:
        pass
    for fmt in ("%d-%b-%Y %H:%M:%S", "%Y-%m-%d %H:%M:%S"):
        try:
            return datetime.strptime(raw,fmt).replace(tzinfo=ist).astimezone(timezone.utc)
        except ValueError:
            pass
    return None


def parse_full_quote(payload, *, received_at=None):
    if not isinstance(payload,dict) or payload.get("status") is not True:
        raise FullQuoteBlocked("FULL_QUOTE_BROKER_FAILED")
    data=payload.get("data")
    if not isinstance(data,dict):
        raise FullQuoteBlocked("FULL_QUOTE_DATA_INVALID")
    fetched=data.get("fetched")
    if not isinstance(fetched,list) or len(fetched)!=1 or not isinstance(fetched[0],dict):
        raise FullQuoteBlocked("FULL_QUOTE_REQUIRES_EXACTLY_ONE_INSTRUMENT")
    row=fetched[0]
    # Angel may omit the exchange field, but token must match EXACTLY;
    # exchange is anchored by the fixed NFO-only outbound request.
    if str(row.get("symbolToken")) != TOKEN or row.get("tradingSymbol") != SYMBOL:
        raise FullQuoteBlocked("FULL_QUOTE_CONTRACT_MISMATCH")
    if row.get("exchange") not in (None,"NFO"):
        raise FullQuoteBlocked("FULL_QUOTE_EXCHANGE_MISMATCH")
    last=_positive_decimal(row.get("ltp"),"LTP")
    depth=row.get("depth")
    if not isinstance(depth,dict):
        raise FullQuoteBlocked("FULL_QUOTE_DEPTH_MISSING")
    buy=depth.get("buy"); sell=depth.get("sell")
    if not isinstance(buy,list) or not isinstance(sell,list) or not buy or not sell:
        raise FullQuoteBlocked("FULL_QUOTE_BID_ASK_MISSING")
    if not isinstance(buy[0],dict) or not isinstance(sell[0],dict):
        raise FullQuoteBlocked("FULL_QUOTE_DEPTH_INVALID")
    bid=_positive_decimal(buy[0].get("price"),"BEST_BID")
    ask=_positive_decimal(sell[0].get("price"),"BEST_ASK")
    if bid > ask:
        raise FullQuoteBlocked("FULL_QUOTE_CROSSED_BOOK")
    for side in (buy[0],sell[0]):
        quantity=side.get("quantity")
        if isinstance(quantity,bool) or not isinstance(quantity,(str,int)) or not str(quantity).isdigit() or int(quantity)<=0:
            raise FullQuoteBlocked("FULL_QUOTE_DEPTH_QUANTITY_INVALID")
    seen=received_at or datetime.now(timezone.utc)
    if not isinstance(seen,datetime) or seen.utcoffset() is None:
        raise FullQuoteBlocked("RECEIVE_CLOCK_INVALID")
    feed=_exchange_time(row.get("exchFeedTime"))
    age=(seen.astimezone(timezone.utc)-feed).total_seconds() if feed else None
    return {
        "contract":SYMBOL,"token":TOKEN,"ltp":str(last),
        "bestBid":str(bid),"bestAsk":str(ask),
        "bidQuantity":int(buy[0]["quantity"]),"askQuantity":int(sell[0]["quantity"]),
        "brokerFeedTimestampUTC":feed.isoformat() if feed else None,
        "brokerFeedAgeSeconds":round(age,3) if age is not None else None,
        "brokerReportedFeedAgeWithin10s": age is not None and 0<=age<=MAX_BROKER_FEED_AGE_S,
        "bidAtOrAboveDraftLimit":bid>=LIMIT,
        "feedTimestampIndependentlyExchangeVerified":False,
        "tickVerified":False,"lppVerified":False,
        "brokerOrderWritePermissionVerified":False,"actualFeesVerified":False,
        "canSubmitOrder":False,"submittedOrder":False,"realOrdersEnabled":False,
    }


def fetch_full_quote(owner, *, fetch=None):
    if not angel_gateway._owner_bound(owner):
        raise FullQuoteBlocked("OWNER_NOT_BOUND")
    session=angel_gateway._clean_session(owner,datetime.now(timezone.utc).timestamp())
    if not session or not session.get("jwt") or not session.get("apiKey"):
        raise FullQuoteBlocked("BROKER_SESSION_INVALID")
    body=json.dumps({"mode":"FULL","exchangeTokens":{"NFO":[TOKEN]}},
                    separators=(",",":")).encode()
    headers={
        "Accept":"application/json","Content-Type":"application/json",
        "Authorization":"Bearer "+session["jwt"],"X-PrivateKey":session["apiKey"],
        "X-UserType":"USER","X-SourceID":"WEB",
        "User-Agent":"OptionX-FullQuote-ReadOnly-V32/1.0",
        **angel_gateway.angel_client_identity_headers(allow_public_lookup=False),
    }
    req=urllib.request.Request(ROOT+PATH,headers=headers,data=body,method="POST")
    try:
        if fetch is None:
            opener=urllib.request.build_opener(
                angel_gateway.NoRedirect(),
                urllib.request.HTTPSHandler(context=ssl.create_default_context()))
            stream=opener.open(req,timeout=10)
        else:
            stream=fetch(req,timeout=10)
        with stream as response:
            if getattr(response,"status",200)!=200:
                raise FullQuoteBlocked("FULL_QUOTE_HTTP_ERROR")
            raw=response.read(MAX_BYTES+1)
        received_at=datetime.now(timezone.utc)
        if len(raw)>MAX_BYTES:
            raise FullQuoteBlocked("FULL_QUOTE_OVERSIZED")
        return parse_full_quote(json.loads(raw),received_at=received_at)
    except FullQuoteBlocked:
        raise
    except (OSError,ValueError,TypeError,UnicodeError,urllib.error.URLError):
        raise FullQuoteBlocked("FULL_QUOTE_UNAVAILABLE_OR_INVALID") from None


def run():
    owner=None
    try:
        owner,client=_config()
        verify_login(owner,client)
        positions=read_book(owner,"positions")["positions"]
        orders=read_book(owner,"orderbook")["orders"]
        inspected=assess_manual_positions(positions,orders)
        if len(inspected)!=1:
            raise FullQuoteBlocked("POSITION_REQUIRES_EXACTLY_ONE_LONG")
        item=inspected[0]
        if (item["contract"]!=SYMBOL or item["instrumentToken"]!=TOKEN
                or item["netLongQuantity"]!=EXPECTED_QTY or item["activeSellOrders"]!=0):
            raise FullQuoteBlocked("POSITION_CHANGED_OR_SELL_CONFLICT")
        for order in orders:
            if order.get("symbol")==SYMBOL and not order.get("statusKnown",False):
                raise FullQuoteBlocked("ORDER_STATUS_UNKNOWN")
        quote=fetch_full_quote(owner)
        print("V32_OWNER_POSITION_AND_FULL_QUOTE: PASS")
        for field in ("contract","token","ltp","bestBid","bestAsk","bidQuantity",
                      "askQuantity","brokerFeedTimestampUTC","brokerFeedAgeSeconds",
                      "brokerReportedFeedAgeWithin10s","bidAtOrAboveDraftLimit"):
            print(field.upper()+":",quote[field])
        print("FEED_TIMESTAMP_INDEPENDENT_EXCHANGE_PROOF: NO")
        print("TICK_LPP_ORDER_PERMISSION_FEES: NOT_VERIFIED")
        print("BROKER_ORDER_SUBMITTED: NO | REAL_ORDERS: OFF")
        return 0
    except Exception:
        print("V32_FULL_QUOTE_READ_ONLY: BLOCKED")
        print("BROKER_ORDER_SUBMITTED: NO | REAL_ORDERS: OFF")
        return 2
    finally:
        if owner:
            try: angel_gateway.disconnect(owner)
            except Exception: pass


if __name__=="__main__":
    raise SystemExit(run())
