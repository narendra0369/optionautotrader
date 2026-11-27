"""OPTIONX V87 read-only Angel reconciliation. No credentials, broker network, writes or order methods.
Input must originate from trusted authenticated owner-side read_three_books; browser JSON is not trusted.
"""
from __future__ import annotations
from datetime import datetime, timedelta
from typing import Mapping

RESOURCES = ("orderbook", "tradebook", "positions")
ACTIVE = {"OPEN", "PENDING", "PARTIALLY_FILLED", "CANCEL_REQUESTED", "UNKNOWN"}
TERMINAL = {"COMPLETE", "CANCELLED", "REJECTED"}

def reconcile(books: Mapping, *, received_at: datetime, now: datetime,
              owner_session_verified: bool, server_authenticated_transport: bool,
              optionx_order_ids: frozenset[str] = frozenset()) -> dict:
    reasons: list[str] = []
    if not isinstance(books, Mapping) or books.get("broker") != "Angel" or books.get("allReadsSucceeded") is not True:
        reasons.append("THREE_BOOKS_NOT_VERIFIED")
    if owner_session_verified is not True or server_authenticated_transport is not True:
        reasons.append("BROKER_OWNER_OR_TRANSPORT_NOT_VERIFIED")
    if not isinstance(received_at, datetime) or received_at.utcoffset() is None or not isinstance(now, datetime) or now.utcoffset() is None:
        reasons.append("TIMESTAMPS_MISSING")
    elif not timedelta(0) <= now - received_at <= timedelta(seconds=10):
        reasons.append("BROKER_SNAPSHOT_STALE")
    raw = books.get("books", {}) if isinstance(books, Mapping) else {}
    if not isinstance(raw, Mapping) or set(raw.keys()) != set(RESOURCES):
        reasons.append("THREE_BOOKS_INCOMPLETE")
        raw = {}
    for name in RESOURCES:
        b = raw.get(name)
        if not isinstance(b, Mapping) or b.get("broker") != "Angel" or b.get("resource") != name or b.get("mode") != "OWNER_BOUND_READ_ONLY" or b.get("canSubmitOrder") is not False or b.get("liveExecutionEnabled") is not False:
            reasons.append("INVALID_" + name.upper() + "_SNAPSHOT")
    orders = raw.get("orderbook", {}).get("orders") if isinstance(raw.get("orderbook"), Mapping) else None
    positions = raw.get("positions", {}).get("positions") if isinstance(raw.get("positions"), Mapping) else None
    trade = raw.get("tradebook", {}).get("tradeRows") if isinstance(raw.get("tradebook"), Mapping) else None
    if not isinstance(orders, list) or not isinstance(positions, list) or not isinstance(trade, int) or trade < 0:
        reasons.append("BROKER_BOOK_PAYLOAD_INCOMPLETE")
        orders, positions, trade = [], [], 0
    if any(not isinstance(x, Mapping) for x in orders + positions):
        reasons.append("BROKER_BOOK_RECORD_INVALID")
        orders, positions = [], []
    if not isinstance(optionx_order_ids, frozenset) or any(not isinstance(x, str) or not x for x in optionx_order_ids):
        reasons.append("OPTIONX_ID_SET_UNVERIFIED")
        optionx_order_ids = frozenset()
    open_orders = [o for o in orders if o.get("status") in ACTIVE]
    if any(o.get("status") not in ACTIVE | TERMINAL for o in orders):
        reasons.append("UNKNOWN_ORDER_STATE")
    if any(o.get("status") == "UNKNOWN" for o in open_orders):
        reasons.append("UNKNOWN_ORDER_STATE")
    if any(o.get("order_id") not in optionx_order_ids for o in open_orders):
        reasons.append("NON_OPTIONX_ACTIVE_ORDER_PRESERVE")
    if any(not isinstance(p.get("net_quantity"), int) for p in positions):
        reasons.append("POSITION_QUANTITY_INVALID")
    if any(isinstance(p.get("net_quantity"), int) and p["net_quantity"] != 0 for p in positions):
        reasons.append("BROKER_EXPOSURE_OWNER_RECONCILIATION_REQUIRED")
    # Existing tradebook adapter counts rows, not verified trade/fill IDs.
    reasons.append("FILL_ID_RECONCILIATION_NOT_CERTIFIED")
    return {
        "scope": "READ_ONLY_DIAGNOSTIC", "broker": "Angel",
        "booksReceived": len(raw), "orderRows": len(orders),
        "positionRows": len(positions), "tradeRows": trade,
        "activeOrderRows": len(open_orders),
        "nonzeroPositionRows": sum(isinstance(p.get("net_quantity"), int) and p["net_quantity"] != 0 for p in positions),
        "reasons": sorted(set(reasons)), "recoveryCertified": False,
        "canPlace": False, "canSell": False, "canCancel": False,
        "canModify": False, "manualPositionsTouched": False,
    }
