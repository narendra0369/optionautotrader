"""V44 strict account order/trade reconciliation, NO order submit.

Consumes isolated *trusted server-side* broker book rows. Rejects missing or
ambiguous fields rather than inferring fills from order status or LTP. Does not
persist identifiers, call broker or authorize retries. The caller must verify
book provenance/time/owner independently.
"""
from __future__ import annotations
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation

ORDER_TERMINAL={"complete","cancelled","rejected"}
ORDER_ACTIVE={"open","pending","trigger pending","partially filled"}
ORDER_STATUS=ORDER_TERMINAL|ORDER_ACTIVE

def _integer(value):
    if isinstance(value,bool): return None
    if isinstance(value,int): return value if value>=0 else None
    if isinstance(value,str) and value.isascii() and value.isdigit():
        return int(value)
    return None

def _decimal(value):
    if isinstance(value,bool): return None
    if not isinstance(value,(str,int,Decimal)): return None
    try:
        v=Decimal(str(value))
        return v if v.is_finite() and v>0 else None
    except (TypeError,ValueError,InvalidOperation):
        return None

def _recent(at,now):
    if not isinstance(at,datetime) or not isinstance(now,datetime): return False
    if at.utcoffset() is None or now.utcoffset() is None: return False
    delta=(now.astimezone(timezone.utc)-at.astimezone(timezone.utc)).total_seconds()
    return 0<=delta<=10

def reconcile(*, intent, orderbook, tradebook, as_of, now,
              owner_authenticated, book_sources_verified):
    """Report only; never returns permission for placing/cancelling an order."""
    blockers=set()
    if owner_authenticated is not True or book_sources_verified is not True:
        blockers.add("BROKER_BOOK_PROVENANCE_UNVERIFIED")
    if not _recent(as_of,now):
        blockers.add("BROKER_BOOKS_STALE_OR_TIME_INVALID")
    if not isinstance(intent,dict):
        intent={}
    order_id=intent.get("broker_order_id")
    required=("tradingsymbol","symboltoken","transactiontype",
              "quantity","producttype")
    if (not isinstance(order_id,str) or len(order_id)<4
        or not all(k in intent for k in required)):
        blockers.add("EXACT_INTENT_OR_ACK_ID_MISSING")
    if not isinstance(orderbook,list) or not isinstance(tradebook,list):
        blockers.add("BOTH_BROKER_BOOKS_REQUIRED")
        orderbook=[]; tradebook=[]
    if len(orderbook)>500 or len(tradebook)>500:
        blockers.add("BOOK_SIZE_EXCEEDED")
        orderbook=[]; tradebook=[]
    order_matches=[r for r in orderbook if isinstance(r,dict) and r.get("orderid")==order_id]
    if len(order_matches)!=1:
        blockers.add("BROKER_ORDER_ID_NOT_UNIQUELY_FOUND")
    expected_qty=_integer(intent.get("quantity"))
    if expected_qty is None or expected_qty==0:
        blockers.add("INTENT_QUANTITY_INVALID")
    order_state=None
    order_filled=None
    if len(order_matches)==1:
        row=order_matches[0]
        keys=("tradingsymbol","symboltoken","transactiontype","producttype")
        if any(row.get(k)!=intent.get(k) for k in keys):
            blockers.add("BROKER_ORDER_IDENTITY_MISMATCH")
        if _integer(row.get("quantity"))!=expected_qty:
            blockers.add("BROKER_ORDER_QUANTITY_MISMATCH")
        status=row.get("status")
        if not isinstance(status,str) or status.strip().lower() not in ORDER_STATUS:
            blockers.add("BROKER_ORDER_STATUS_UNKNOWN")
        else: order_state=status.strip().lower()
        order_filled=_integer(row.get("filledshares"))
        if (order_filled is None or expected_qty is None
            or order_filled>expected_qty):
            blockers.add("BROKER_FILLED_QUANTITY_INVALID")
    related=[]
    for row in tradebook:
        if not isinstance(row,dict):
            blockers.add("TRADEBOOK_SHAPE_INVALID")
            continue
        if row.get("orderid")==order_id:
            related.append(row)
    ids=set()
    total=0
    if not related and order_filled not in (None,0):
        blockers.add("BROKER_FILLED_BUT_NO_TRADES")
    for trade in related:
        trade_id=trade.get("tradeid")
        qty=_integer(trade.get("fillshares"))
        px=_decimal(trade.get("fillprice"))
        if not isinstance(trade_id,str) or not trade_id or trade_id in ids:
            blockers.add("TRADE_ID_MISSING_OR_DUPLICATED")
        else: ids.add(trade_id)
        if qty is None or qty==0 or px is None:
            blockers.add("TRADE_QUANTITY_OR_PRICE_INVALID")
        total+=qty if qty is not None else 0
        for key in ("tradingsymbol","symboltoken","transactiontype","producttype"):
            if trade.get(key)!=intent.get(key):
                blockers.add("TRADE_IDENTITY_MISMATCH")
    if order_filled is not None and total!=order_filled:
        blockers.add("ORDER_TRADE_FILL_TOTAL_MISMATCH")
    if expected_qty is not None and total>expected_qty:
        blockers.add("OVERFILL_OR_DUPLICATE_TRADEBOOK")
    if order_state=="complete" and total!=expected_qty:
        blockers.add("COMPLETE_STATUS_FILL_CONFLICT")
    if order_state=="rejected" and total>0:
        blockers.add("REJECTED_STATUS_HAS_FILLS_VERIFY")
    if order_state in ORDER_ACTIVE:
        blockers.add("ORDER_STILL_ACTIVE_OR_UNCERTAIN")
    if order_state=="cancelled" and total>0:
        blockers.add("PARTIAL_FILL_AFTER_CANCEL_ACCOUNT_RECHECK")
    if not blockers and order_state=="complete":
        state="COMPLETE_BROKER_BOOKS_CONSISTENT"
    elif not blockers and order_state in ("cancelled","rejected"):
        state="TERMINAL_NO_FILL_CONFIRMED_IN_BOOKS"
    else:
        state="RECONCILIATION_REVIEW_REQUIRED"
    # Even a consistent book cannot independently prove external ownership or
    # authorize a fresh send, replace, market exit or stop placement.
    return {"state":state,"blockers":sorted(blockers),
            "filledQuantityObserved":total if not blockers else None,
            "orderStatusObserved":order_state,
            "canSubmitOrder":False,"canRetryUnknownOrder":False,
            "canCancelOrder":False,"liveOrdersEnabled":False}
