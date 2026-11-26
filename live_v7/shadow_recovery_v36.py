"""V36 offline cross-book recovery reconciliation for SHADOW observations.

Pure evaluation of caller-supplied, normalized test snapshots. No broker
authentication, network, credentials, orders, cancellation or production writes.
This module NEVER certifies real executions and ALWAYS keeps trading blocked.
"""
from __future__ import annotations
from datetime import datetime, timezone
from collections.abc import Mapping, Sequence

SYMBOL="NIFTY29DEC2629000CE"
TOKEN="38158"
QTY=65
MAX_AGE_SECONDS=10
ACTIVE={"OPEN","PENDING","PARTIALLY_FILLED","CANCEL_REQUESTED"}
TERMINAL={"COMPLETE","CANCELLED","REJECTED"}


class RecoveryBlocked(ValueError):
    pass


def _rows(value, label):
    if not isinstance(value, (list,tuple)) or len(value)>500:
        raise RecoveryBlocked(label+"_INVALID")
    if any(not isinstance(row,Mapping) for row in value):
        raise RecoveryBlocked(label+"_INVALID")
    return value


def _fresh(at, now):
    return (isinstance(at,datetime) and isinstance(now,datetime)
            and at.utcoffset() is not None and now.utcoffset() is not None
            and 0 <= (now.astimezone(timezone.utc)-at.astimezone(timezone.utc)).total_seconds() <= MAX_AGE_SECONDS)


def shadow_reconcile(*, shadow_status, positions, orders, trades,
                     broker_owner_verified, books_complete, received_at, now):
    """Always fail closed, especially on ambiguous or manual broker positions.

    The orderbook/tradebook rows are normalized *test input*; no broker identity
    or transport provenance can be inferred from these caller values.
    """
    pos=_rows(positions,"POSITIONS")
    ords=_rows(orders,"ORDERS")
    fills=_rows(trades,"TRADES")
    blockers={"SOURCE_LOCKED_NO_BROKER_ORDERS",
              "PRODUCTION_JOURNAL_AND_BROKER_LIFECYCLE_NOT_CERTIFIED"}
    if shadow_status not in ("DRAFT","SIMULATED_SEND_UNKNOWN","SIMULATED_ACK","REVIEW_REQUIRED"):
        blockers.add("UNKNOWN_SHADOW_STATE")
    if shadow_status=="SIMULATED_SEND_UNKNOWN":
        blockers.add("AMBIGUOUS_SIMULATED_OUTCOME_NO_RETRY")
    if shadow_status=="SIMULATED_ACK":
        blockers.add("SIMULATED_ACK_NOT_BROKER_ACK")
    if shadow_status=="REVIEW_REQUIRED":
        blockers.add("MANUAL_REVIEW_REQUIRED")
    if broker_owner_verified is not True:
        blockers.add("OWNER_OR_BROKER_NOT_VERIFIED")
    if books_complete is not True or not _fresh(received_at,now):
        blockers.add("INCOMPLETE_OR_STALE_BOOKS")

    matching=[p for p in pos if p.get("symbol")==SYMBOL and str(p.get("instrumentToken"))==TOKEN]
    if len(matching)!=1 or type(matching[0].get("net_quantity")) is not int or matching[0]["net_quantity"]!=QTY:
        blockers.add("POSITION_CHANGED_OR_NOT_UNIQUE")
    if any(p.get("symbol")==SYMBOL and str(p.get("instrumentToken"))!=TOKEN for p in pos):
        blockers.add("POSITION_TOKEN_CONFLICT")

    order_ids=set()
    for o in ords:
        oid=o.get("order_id")
        if not isinstance(oid,str) or not oid or oid in order_ids:
            blockers.add("BROKER_ORDER_IDS_INVALID_OR_DUPLICATE")
        else:
            order_ids.add(oid)
        if o.get("symbol")==SYMBOL:
            if o.get("statusKnown") is not True or o.get("status") not in ACTIVE|TERMINAL:
                blockers.add("UNKNOWN_ORDER_STATUS")
            if (o.get("side")=="SELL" and
                    (o.get("status") in ACTIVE or o.get("statusKnown") is not True)):
                blockers.add("ACTIVE_OR_UNCERTAIN_SELL_CONFLICT")
            q=o.get("quantity"); filled=o.get("filled_quantity")
            if type(q) is not int or type(filled) is not int or q<=0 or not 0<=filled<=q:
                blockers.add("INVALID_ORDER_QUANTITY_OR_FILL")

    # Never infer trade ownership from matching symbol or from a mock ACK.
    seen_fills=set()
    for t in fills:
        fill_id=t.get("fill_id")
        order_id=t.get("order_id")
        if (not isinstance(fill_id,str) or not fill_id or fill_id in seen_fills
                or not isinstance(order_id,str) or not order_id):
            blockers.add("INVALID_OR_DUPLICATE_TRADE_ID")
        else:
            seen_fills.add(fill_id)
        if order_id not in order_ids:
            blockers.add("TRADEBOOK_ORDER_NOT_IN_ORDERBOOK")
        if type(t.get("quantity")) is not int or t["quantity"]<=0:
            blockers.add("INVALID_TRADE_FILL_QUANTITY")

    blockers.add("MANUAL_POSITION_NOT_PLATFORM_OWNED")
    return {
        "observedManualPositionRows":len(matching),
        "observedOrderRows":len(ords),
        "observedTradeRows":len(fills),
        "blockers":sorted(blockers),
        "requiresIndependentBrokerReconciliation":True,
        "manualPositionAdopted":False,
        "canRetryOrder":False,"canSubmitOrder":False,"canCancelOrder":False,
        "realOrdersEnabled":False,
        "status":"OFFLINE_SHADOW_RECOVERY_ONLY",
    }
