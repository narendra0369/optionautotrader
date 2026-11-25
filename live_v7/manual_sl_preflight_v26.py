"""V26 manual-position SL preflight. GET-only; NO order submissions.

The owner explicitly requested verification followed by separate final consent
before any real STOPLOSS_LIMIT SELL. This CLI only reads positions and orderbook,
filters existing active stops, and prints safe contract fields. It never
converts manual positions to platform-owned orders.
"""
from __future__ import annotations
import re
from datetime import datetime, timezone
import angel_gateway
from live_v7.aws_angel_owner_reader import _config, verify_login
from live_v7.angel_books_readonly import read_book

ACTIVE={"OPEN","PENDING","PARTIALLY_FILLED","CANCEL_REQUESTED"}
_SYMBOL=re.compile(r"^[A-Z0-9._-]{4,72}$")

class ManualPreflightError(ValueError):
    pass

def assess_manual_positions(positions:list,orders:list)->list[dict]:
    if not isinstance(positions,list) or not isinstance(orders,list):
        raise ManualPreflightError("BROKER_BOOKS_NOT_VALID")
    out=[]
    for p in positions:
        if not isinstance(p,dict):
            raise ManualPreflightError("POSITION_SHAPE_INVALID")
        qty=p.get("net_quantity")
        if type(qty) is not int or not isinstance(p.get("instrumentToken"),str):
            raise ManualPreflightError("POSITION_QUANTITY_INVALID")
        if qty<=0:
            continue  # a short position cannot be closed by SELL
        symbol=p.get("symbol")
        if not isinstance(symbol,str) or not _SYMBOL.fullmatch(symbol):
            raise ManualPreflightError("SYMBOL_INVALID")
        same=[o for o in orders if o.get("symbol")==symbol and o.get("status") in ACTIVE]
        conflicts=[o for o in same if o.get("side")=="SELL"]
        out.append({
            "contract":symbol,"instrumentToken":p["instrumentToken"],
            "netLongQuantity":qty,"activeSellOrders":len(conflicts),
            "activeSellQuantity":sum(o["quantity"]-o["filled_quantity"] for o in conflicts),
            "conflictingOrdersRequireHumanReview":bool(conflicts),
            "requiresFreshLTPAndTick":True,
            "triggerLimitNotCalculated":True,"canSubmitOrder":False})
    return out

def run()->int:
    owner=None
    try:
        owner,client=_config()
        verify_login(owner,client)
        p=read_book(owner,"positions")
        o=read_book(owner,"orderbook")
        report=assess_manual_positions(p["positions"],o["orders"])
        print("ANGEL_OWNER_READONLY: PASS")
        print("LONG_NFO_POSITIONS:",len(report))
        for i,r in enumerate(report,1):
            print("POSITION_%d: CONTRACT=%s TOKEN=%s NET_QTY=%d ACTIVE_SELL_ORDERS=%d ACTIVE_SELL_REMAINING=%d" %
                (i,r["contract"],r["instrumentToken"],r["netLongQuantity"],
                 r["activeSellOrders"],r["activeSellQuantity"]))
        if not report:
            print("BLOCKED: NO_ELIGIBLE_LONG_NFO_POSITION")
        if any(x["conflictingOrdersRequireHumanReview"] for x in report):
            print("BLOCKED: EXISTING_SELL_ORDER_NEEDS_REVIEW")
        print("SL_TRIGGER_LIMIT: NOT_SET | LTP_TICK_BROKER_SUPPORT: NOT_YET_VERIFIED")
        print("REAL_ORDERS: OFF | MANUAL_POSITIONS: UNTOUCHED")
        return 0
    except Exception:
        print("MANUAL_SL_PREFLIGHT_BLOCKED: OWNER_OR_BROKER_BOOK_INVALID")
        print("REAL_ORDERS: OFF | MANUAL_POSITIONS: UNTOUCHED")
        return 2
    finally:
        if owner:
            try:angel_gateway.disconnect(owner)
            except Exception:pass

if __name__=="__main__":
    raise SystemExit(run())
