"""V93 guarded Angel SL-LIMIT transport, deliberately NOT an HTTP route.

Only a certified, single-use V52 permit for the exact order can authorize
network dispatch. Caller must supply a production-verified risk gate and
fresh broker snapshot. No permit issuer, gateway route or automatic retry here.
Future deployment must provide a certified permit issuer, persistent intent
reservation, worker identity and broker account controls independently.
"""
from __future__ import annotations
from datetime import datetime, timedelta
from decimal import Decimal, InvalidOperation
from collections.abc import Mapping
from live_v7.certified_execution_permit_v52 import verify_dispatch_permit

class SLDispatchBlocked(PermissionError):
    pass

def _amount(x):
    if isinstance(x,bool) or not isinstance(x,(str,int,Decimal)):raise SLDispatchBlocked("PRICE_INVALID")
    try:r=Decimal(str(x))
    except InvalidOperation:raise SLDispatchBlocked("PRICE_INVALID") from None
    if not r.is_finite() or r<=0:raise SLDispatchBlocked("PRICE_INVALID")
    return r

def plan(*, owner, position, orders, ltp, tick, trigger, limit,
         snapshot_at, now, gate):
    """Exact-plan verification; caller is a trusted AWS worker, not a browser.

    Gate must contain production-side evidence, not browser claims. A valid
    plan is NOT itself a dispatch authorization.
    """
    if not isinstance(gate,Mapping) or gate.get("productionPermitted") is not True:
        raise SLDispatchBlocked("PRODUCTION_GATE_DENIED")
    # Production governance is checked by the worker, never by JavaScript.
    if gate.get("workerIdentityVerified") is not True or gate.get("riskReservationCommitted") is not True or gate.get("ownerApprovedExactOrder") is not True or gate.get("durableUnknownOutcomeFenceCommitted") is not True:
        raise SLDispatchBlocked("REQUIRED_SERVER_PROOFS_MISSING")
    if not isinstance(owner,str) or len(owner)<8:raise SLDispatchBlocked("OWNER_UNVERIFIED")
    if (not isinstance(now,datetime) or now.utcoffset() is None or
        not isinstance(snapshot_at,datetime) or snapshot_at.utcoffset() is None
        or not timedelta(0)<=now-snapshot_at<=timedelta(seconds=10)):
        raise SLDispatchBlocked("BROKER_SNAPSHOT_STALE")
    if not isinstance(position,Mapping) or position.get("exchange")!="NFO":
        raise SLDispatchBlocked("NFO_POSITION_REQUIRED")
    symbol=position.get("symbol");token=position.get("instrumentToken")
    qty=position.get("net_quantity")
    product=position.get("producttype")
    if (not isinstance(symbol,str) or not symbol.startswith(("NIFTY","BANKNIFTY"))
        or not isinstance(token,str) or not token.isdigit()
        or type(qty) is not int or qty<=0
        or product not in ("CARRYFORWARD","INTRADAY")):
        raise SLDispatchBlocked("POSITION_OR_BROKER_PRODUCT_UNVERIFIED")
    if not isinstance(orders,list) or any(not isinstance(x,Mapping) for x in orders):
        raise SLDispatchBlocked("ORDERBOOK_UNVERIFIED")
    if any(o.get("symbol")==symbol and o.get("status") in
           ("OPEN","PENDING","PARTIALLY_FILLED","CANCEL_REQUESTED","UNKNOWN")
           for o in orders):
        raise SLDispatchBlocked("EXISTING_OR_UNKNOWN_ACTIVE_ORDER")
    px,t,l,step=map(_amount,(ltp,trigger,limit,tick))
    if not (l<=t<px):raise SLDispatchBlocked("SL_PRICE_RELATION_INVALID")
    if (t/step)%1 or (l/step)%1:raise SLDispatchBlocked("BROKER_TICK_NOT_ALIGNED")
    if gate.get("brokerLppChecked") is not True or gate.get("brokerProductConfirmed") is not True:
        raise SLDispatchBlocked("BROKER_LPP_OR_PRODUCT_NOT_CONFIRMED")
    return {"variety":"STOPLOSS","tradingsymbol":symbol,"symboltoken":token,
            "transactiontype":"SELL","exchange":"NFO","ordertype":"STOPLOSS_LIMIT",
            "producttype":product,"duration":"DAY","price":str(l),
            "triggerprice":str(t),"quantity":str(qty)}

def guarded_submit(*, owner, draft, permit, submit, read_orderbook, now=None):
    """No fallback/retry. Unknown outcome is a hard block, never duplicate send.

    Caller must only invoke after plan() with verified server-side inputs. The
    exact single-use permit is consumed before one broker POST. If anything
    fails, human reconciliation with broker orderbook is required.
    """
    if not isinstance(draft,dict) or set(draft)!={
        "variety","tradingsymbol","symboltoken","transactiontype","exchange",
        "ordertype","producttype","duration","price","triggerprice","quantity"}:
        raise SLDispatchBlocked("ORDER_PAYLOAD_INVALID")
    if draft["variety"]!="STOPLOSS" or draft["ordertype"]!="STOPLOSS_LIMIT" or draft["transactiontype"]!="SELL" or draft["duration"]!="DAY":
        raise SLDispatchBlocked("NOT_A_SELL_SL_LIMIT")
    if not callable(submit) or not callable(read_orderbook):
        raise SLDispatchBlocked("BROKER_ADAPTER_MISSING")
    # No key, no permit issuer, no unlocked worker => this denies.
    verify_dispatch_permit(operation="place",owner=owner,payload=draft,permit=permit,now=now)
    try:
        ack=submit(draft) # exactly one broker POST, not a retry loop
    except Exception:
        return {"state":"UNKNOWN_BROKER_OUTCOME","canRetry":False,
                "brokerOrderPlacedConfirmed":False}
    if not isinstance(ack,Mapping) or not isinstance(ack.get("orderid"),str) or len(ack["orderid"])<4:
        return {"state":"UNKNOWN_BROKER_OUTCOME","canRetry":False,
                "brokerOrderPlacedConfirmed":False}
    oid=ack["orderid"]
    try: book=read_orderbook()
    except Exception:
        return {"state":"ORDER_ACK_AWAITING_BOOK_RECONCILIATION","canRetry":False,
                "brokerOrderPlacedConfirmed":False}
    if not isinstance(book,list):
        return {"state":"ORDERBOOK_UNVERIFIED","canRetry":False,
                "brokerOrderPlacedConfirmed":False}
    rows=[o for o in book if isinstance(o,Mapping) and o.get("order_id")==oid]
    if len(rows)!=1:
        return {"state":"ORDER_ID_NOT_VERIFIED_IN_BOOK","canRetry":False,
                "brokerOrderPlacedConfirmed":False}
    row=rows[0]
    if (row.get("symbol")!=draft["tradingsymbol"] or row.get("side")!="SELL"
        or row.get("quantity")!=int(draft["quantity"])
        or row.get("status") not in ("OPEN","PENDING","PARTIALLY_FILLED","COMPLETE")):
        return {"state":"BROKER_ORDER_MISMATCH_REVIEW","canRetry":False,
                "brokerOrderPlacedConfirmed":False}
    return {"state":"BROKER_ORDER_ID_AND_BOOK_MATCHED","brokerOrderId":oid,
            "canRetry":False,"brokerOrderPlacedConfirmed":True,
            "stopTriggerAcceptedIndependently":False,
            "note":"Stop fields require raw broker order confirmation before SL certification."}
