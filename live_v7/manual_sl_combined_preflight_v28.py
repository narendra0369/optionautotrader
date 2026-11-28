"""OptionX V28 consolidated manual SL *read-only* preflight.

Rechecks private authenticated Angel positions/orderbook, contract master and
market-data LTP, and evaluates a strictly DRAFT SELL STOPLOSS_LIMIT at
10.00 trigger / 9.95 limit for owner's explicitly specified long option.

NO place/modify/cancel order API, NO DB updates, NO source lock changes.
A quote received timestamp is not the exchange feed timestamp. No tool here
can prove LPP acceptance, live bid/ask, order write permission, fees or a
guaranteed maximum loss. Output is preparation, NOT an order authorization.
"""
from __future__ import annotations

from datetime import datetime,timezone
from decimal import Decimal,InvalidOperation
import json
import ssl
import urllib.request

import angel_gateway
from live_v7.aws_angel_owner_reader import _config, verify_login
from live_v7.angel_books_readonly import read_book
from live_v7.manual_sl_preflight_v26 import assess_manual_positions
from live_v7.manual_sl_quote_v27 import fetch_ltp

SYMBOL="NIFTY29DEC2629000CE"
TOKEN="38158"
QUANTITY=65
BUY=Decimal("12.92")
LIMIT_LOSS=Decimal("800")
TRIGGER=Decimal("10.00")
LIMIT=Decimal("9.95")
EXPECTED_TICK=Decimal("0.05")
MASTER_URL="https://margincalculator.angelone.in/OpenAPI_File/files/OpenAPIScripMaster.json"


class PreflightBlocked(ValueError):
    pass


def verify_master(records):
    if not isinstance(records,list):
        raise PreflightBlocked("MASTER_SHAPE_INVALID")
    candidates=[x for x in records if isinstance(x,dict)
                and x.get("token")==TOKEN and x.get("symbol")==SYMBOL
                and x.get("exch_seg")=="NFO"]
    if len(candidates)!=1:
        raise PreflightBlocked("CONTRACT_NOT_UNIQUELY_VERIFIED")
    x=candidates[0]
    if x.get("instrumenttype")!="OPTIDX" or str(x.get("expiry"))!="29DEC2026":
        raise PreflightBlocked("CONTRACT_EXPIRY_OR_KIND_MISMATCH")
    try:
        lot=int(x.get("lotsize"))
        tick=Decimal(str(x.get("tick_size")))/Decimal("100")
    except (ValueError,TypeError,InvalidOperation):
        raise PreflightBlocked("MASTER_LOT_OR_TICK_INVALID") from None
    if lot!=QUANTITY or tick!=EXPECTED_TICK:
        raise PreflightBlocked("MASTER_LOT_OR_TICK_CHANGED")
    return {"lot":lot,"tick":tick,"expiry":x["expiry"]}


def evaluate(*,position,orders,master,ltp):
    if not isinstance(orders,list):
        raise PreflightBlocked("BROKER_ORDERS_MISSING")
    rows=assess_manual_positions(position,orders)
    matched=[p for p in rows if p["contract"]==SYMBOL and
             p["instrumentToken"]==TOKEN]
    if len(rows)!=1 or len(matched)!=1 or matched[0]["netLongQuantity"]!=QUANTITY:
        raise PreflightBlocked("LIVE_POSITION_CHANGED_OR_UNVERIFIED")
    if matched[0]["activeSellOrders"]!=0:
        raise PreflightBlocked("EXISTING_ACTIVE_SELL_ORDER")
    info=verify_master(master)
    try:
        last=Decimal(str(ltp))
    except (TypeError,ValueError,InvalidOperation):
        raise PreflightBlocked("LTP_INVALID") from None
    if not last.is_finite() or last<=TRIGGER:
        raise PreflightBlocked("LTP_AT_OR_BELOW_PROPOSED_TRIGGER")
    if LIMIT>=TRIGGER or TRIGGER%info["tick"]!=0 or LIMIT%info["tick"]!=0:
        raise PreflightBlocked("SL_DRAFT_NOT_TICK_ALIGNED")
    premium_loss=(BUY-LIMIT)*QUANTITY
    if premium_loss>=LIMIT_LOSS:
        raise PreflightBlocked("PREMIUM_LOSS_OVER_BUDGET")
    return {
        "symbol":SYMBOL,"token":TOKEN,"quantity":QUANTITY,
        "ltp":last,"trigger":TRIGGER,"limit":LIMIT,
        "entry":BUY,"premium_loss":premium_loss,
        "headroom_before_charges":LIMIT_LOSS-premium_loss,
        "total_premium_paid":BUY*QUANTITY,
        "tick":info["tick"],"expiry":info["expiry"],
        "verifiedBrokerOrderPermission":False,
        "verifiedExchangeFeedTime":False,"verifiedLppAndLiveBidAsk":False,
        "estimatedFeesVerified":False,
        "canSubmitOrder":False,"realOrdersEnabled":False
    }


def load_master():
    req=urllib.request.Request(MASTER_URL,
          headers={"User-Agent":"OptionX-V28-ReadOnlyContractCheck/1.0"})
    opener=urllib.request.build_opener(
        angel_gateway.NoRedirect(),
        urllib.request.HTTPSHandler(context=ssl.create_default_context()))
    with opener.open(req,timeout=45) as f:
        if getattr(f,"status",200)!=200:
            raise PreflightBlocked("INSTRUMENT_MASTER_HTTP_FAILED")
        # Official master is a large file; strict network size bound
        content=f.read(50*1024*1024+1)
    if len(content)>50*1024*1024:
        raise PreflightBlocked("INSTRUMENT_MASTER_TOO_LARGE")
    return json.loads(content)


def run()->int:
    owner=None
    try:
        owner,client=_config()
        verify_login(owner,client)
        positions=read_book(owner,"positions")["positions"]
        orders=read_book(owner,"orderbook")["orders"]
        # Revalidate manual position BEFORE any quote request
        rows=assess_manual_positions(positions,orders)
        if len(rows)!=1 or rows[0]["contract"]!=SYMBOL or rows[0]["instrumentToken"]!=TOKEN or rows[0]["netLongQuantity"]!=QUANTITY or rows[0]["activeSellOrders"]!=0:
            raise PreflightBlocked("MANUAL_POSITION_CHANGED_OR_CONFLICTED")
        master=load_master()
        price=fetch_ltp(owner,symbol=SYMBOL,token=TOKEN)
        result=evaluate(position=positions,orders=orders,master=master,ltp=price)
        print("V28_READ_ONLY_PREFLIGHT: PASS")
        print("CONTRACT:",result["symbol"],"TOKEN:",result["token"])
        print("NET_LONG_QTY:",result["quantity"])
        print("ACTIVE_SELL_ORDERS: 0")
        print("MASTER_EXPIRY:",result["expiry"])
        print("VERIFIED_TICK:",result["tick"])
        print("BROKER_LTP:",result["ltp"])
        print("LTP_RECEIVED_UTC:",datetime.now(timezone.utc).isoformat())
        print("AVERAGE_BUY_PRICE_OWNER_DECLARED:",result["entry"])
        print("MAX_PLANNED_LOSS_INC_FEES:",LIMIT_LOSS)
        print("SL_DRAFT_TRIGGER:",result["trigger"])
        print("SL_DRAFT_LIMIT:",result["limit"])
        print("PREMIUM_LOSS_IF_FILLED_AT_LIMIT_EXC_FEES:",result["premium_loss"])
        print("CHARGES_AND_OTHER_SLIPPAGE_HEADROOM:",result["headroom_before_charges"])
        print("FEED_TIMESTAMP_VERIFIED: NO")
        print("LIVE_BID_ASK_LPP_VERIFIED: NO")
        print("BROKER_ORDER_WRITE_PERMISSION_VERIFIED: NO")
        print("FEES_VERIFIED: NO")
        print("BROKER_STOP_ACK: NOT_TESTED")
        print("REAL_ORDERS: OFF | NO_ORDER_SUBMITTED | MANUAL_POSITION: UNTOUCHED")
        return 0
    except Exception:
        # Do not print secrets, broker responses or proprietary API details.
        print("V28_READ_ONLY_PREFLIGHT: BLOCKED")
        print("BLOCKER: BROKER_LOGIN_BOOK_QUOTE_OR_CONTRACT_NOT_VERIFIED")
        print("REAL_ORDERS: OFF | NO_ORDER_SUBMITTED | MANUAL_POSITION: UNTOUCHED")
        return 2
    finally:
        if owner:
            try: angel_gateway.disconnect(owner)
            except Exception: pass


if __name__=="__main__":
    raise SystemExit(run())
