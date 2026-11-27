"""OPTIONX V90 — read-only evidence adjudicator for Angel fill/ownership/SL.

No network, imports of broker order SDKs, DB writes, owner credential access,
or real order actions. Explicit broker IDs plus authenticated evidence required.
A manual position is never adopted just because its contract matches.
"""
from __future__ import annotations
from collections.abc import Mapping, Sequence

ACTIVE = frozenset({"OPEN", "PENDING", "PARTIALLY_FILLED", "CANCEL_REQUESTED"})
KNOWN = ACTIVE | frozenset({"COMPLETE", "CANCELLED", "REJECTED", "UNKNOWN"})

def adjudicate(*, orders: Sequence[Mapping], fills: Sequence[Mapping],
               positions: Sequence[Mapping], owned_intents: Sequence[Mapping],
               protection_records: Sequence[Mapping],
               authenticated_broker: bool, verified_trade_ids: bool,
               verified_stop_types: bool, verified_order_ack: bool) -> dict:
    """Evidence-only three-way compare. All inputs must be server-sourced.
    
    Filled trade schema (independently verified by an Angel adapter, NOT the
    current trade-row-count adapter): trade_id, order_id, symbol, side,
    quantity (positive int).
    Protection ledger: entry_order_id, stop_order_id, symbol, side="SELL",
    protected_quantity, open_quantity, state="STOP_ACKED".
    """
    issues: set[str] = set()
    for name, data in (("ORDERS", orders), ("FILLS", fills),
                       ("POSITIONS", positions), ("INTENTS", owned_intents),
                       ("PROTECTION", protection_records)):
        if not isinstance(data, (list, tuple)) or len(data) > 500 or any(not isinstance(x, Mapping) for x in data):
            return {"status":"BLOCKED_INVALID_"+name,
                    "fill_reconciled":False,"sl_confirmed":False,
                    "owner_partition_verified":False,"can_trade":False,
                    "can_cancel":False,"manual_positions_touched":False}
    if authenticated_broker is not True:
        issues.add("BROKER_SOURCE_NOT_AUTHENTICATED")
    if verified_trade_ids is not True:
        issues.add("TRADE_IDS_NOT_BROKER_VERIFIED")
    if verified_stop_types is not True:
        issues.add("STOP_ORDER_TYPE_NOT_VERIFIED")
    if verified_order_ack is not True:
        issues.add("ORDER_ACK_NOT_VERIFIED")

    remote_orders: dict[str,Mapping] = {}
    for order in orders:
        oid = order.get("order_id")
        if not isinstance(oid,str) or not oid or oid in remote_orders or order.get("status") not in KNOWN:
            issues.add("BROKER_ORDER_ID_OR_STATUS_INVALID")
        else:
            remote_orders[oid] = order
    local_orders: dict[str,Mapping] = {}
    for intent in owned_intents:
        oid=intent.get("broker_order_id")
        if not isinstance(oid,str) or not oid or oid in local_orders:
            issues.add("OPTIONX_ORDER_OWNERSHIP_ID_INVALID")
        else:
            local_orders[oid]=intent
    if any(oid not in remote_orders for oid in local_orders):
        issues.add("OPTIONX_OWNED_ORDER_NOT_IN_BROKER_BOOK")
    if any(oid not in local_orders for oid in remote_orders):
        # May be historical manual entries; never adopt them.
        issues.add("BROKER_ORDERS_NOT_OWNED_BY_OPTIONX")

    fill_ids: set[str]=set()
    fill_by_order: dict[str,int]={}
    for fill in fills:
        trade_id,oid=fill.get("trade_id"),fill.get("order_id")
        qty=fill.get("quantity")
        if (not isinstance(trade_id,str) or not trade_id or trade_id in fill_ids
            or not isinstance(oid,str) or not oid or type(qty) is not int or qty<=0
            or fill.get("side") not in ("BUY","SELL") or not isinstance(fill.get("symbol"),str)):
            issues.add("BROKER_TRADE_RECORD_INVALID")
            continue
        fill_ids.add(trade_id)
        fill_by_order[oid]=fill_by_order.get(oid,0)+qty
        related=remote_orders.get(oid)
        if related is None:
            issues.add("FILL_ORDER_NOT_IN_BROKER_BOOK")
        elif fill["symbol"] != related.get("symbol") or fill["side"] != related.get("side"):
            issues.add("FILL_CONTRACT_SIDE_MISMATCH")
    for oid,intent in local_orders.items():
        order=remote_orders.get(oid)
        if order is None: continue
        if intent.get("symbol") != order.get("symbol") or intent.get("side") != order.get("side"):
            issues.add("OPTIONX_ORDER_ID_CONTRACT_MISMATCH")
        broker_filled=order.get("filled_quantity")
        if type(broker_filled) is not int or broker_filled<0:
            issues.add("BROKER_FILL_QTY_INVALID")
        elif fill_by_order.get(oid,0)!=broker_filled:
            issues.add("BROKER_TRADE_FILL_QTY_DISCREPANCY")
    for p in positions:
        if type(p.get("net_quantity")) is not int or not isinstance(p.get("symbol"),str):
            issues.add("BROKER_POSITION_INVALID")
        elif p["net_quantity"]!=0:
            # Account aggregate position contains manual exposure: without
            # a broker-supported position identifier/partition it cannot
            # prove OPTIONX ownership or isolated exit rights.
            issues.add("ACCOUNT_NET_POSITION_PARTITION_NOT_PROVEN")
    if len(positions)>0 and not owned_intents:
        issues.add("MANUAL_POSITION_NOT_ADOPTED")

    if not owned_intents:
        issues.add("NO_OPTIONX_OWNED_ENTRY_TO_CERTIFY")
    stop_ids:set[str]=set()
    for rec in protection_records:
        entry=rec.get("entry_order_id"); stop=rec.get("stop_order_id")
        qty,open_qty=rec.get("protected_quantity"),rec.get("open_quantity")
        if not isinstance(stop,str) or not stop or stop in stop_ids:
            issues.add("STOP_ID_MISSING_OR_DUPLICATED"); continue
        stop_ids.add(stop)
        stop_order=remote_orders.get(stop)
        if entry not in local_orders or stop_order is None:
            issues.add("STOP_NOT_BOUND_TO_VERIFIED_ENTRY_AND_BROKER_ORDER");continue
        if (rec.get("state")!="STOP_ACKED"
            or stop_order.get("status") not in {"OPEN","PENDING"}
            or stop_order.get("side")!="SELL"
            or stop_order.get("symbol")!=rec.get("symbol")
            or rec.get("symbol")!=local_orders[entry].get("symbol")
            or rec.get("side")!="SELL"
            or type(qty) is not int or type(open_qty) is not int
            or qty<=0 or qty!=open_qty
            or stop_order.get("quantity")!=qty
            or stop_order.get("is_broker_verified_stop_limit") is not True):
            issues.add("STOP_ACK_OR_COVERAGE_MISMATCH")
    if owned_intents and not protection_records:
        issues.add("OPTIONX_PROTECTION_MISSING")

    fill_ok=(authenticated_broker is True and verified_trade_ids is True and bool(local_orders)
             and not any(s.startswith(("BROKER_TRADE","FILL_","OPTIONX_ORDER",
                                       "BROKER_FILL")) for s in issues))
    ownership_ok=(bool(local_orders) and authenticated_broker is True
                  and "ACCOUNT_NET_POSITION_PARTITION_NOT_PROVEN" not in issues
                  and "OPTIONX_OWNED_ORDER_NOT_IN_BROKER_BOOK" not in issues
                  and "OPTIONX_ORDER_ID_CONTRACT_MISMATCH" not in issues)
    sl_ok=(ownership_ok and fill_ok and verified_stop_types is True
           and verified_order_ack is True and bool(protection_records)
           and not any(s.startswith(("STOP_","OPTIONX_PROTECTION")) for s in issues))
    return {
        "status":"EVIDENCE_REVIEW",
        "optionx_orders":len(local_orders),
        "manual_or_untracked_broker_orders":sum(oid not in local_orders for oid in remote_orders),
        "positions_with_exposure":sum(type(p.get("net_quantity")) is int and p["net_quantity"]!=0 for p in positions),
        "fill_reconciled":fill_ok, "sl_confirmed":sl_ok,
        "owner_partition_verified":ownership_ok,
        "issues":sorted(issues),
        "can_trade":False,"can_cancel":False,"manual_positions_touched":False,
        "note":"Diagnostic proof only; not an order permit or lifecycle certification.",
    }
