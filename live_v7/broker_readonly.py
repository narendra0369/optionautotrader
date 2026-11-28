"""OptionX V7: read-only broker snapshot contracts and strict normalization.

DEV ONLY, NO network calls, credential handling, live routes, or order methods.
This module accepts authenticated broker responses supplied by a future
server-only transport, never directly from a browser.
Schema validation alone DOES NOT prove the snapshot is from a broker.
"""
from __future__ import annotations

import re
from datetime import datetime, timedelta
from decimal import Decimal, InvalidOperation
from typing import Any, Mapping, Sequence

# Audited READ requests only. Do not add side-effecting routes to this table.
# References: Angel One SmartAPI Python official smartConnect.py;
# Delta Exchange India REST v2 docs (read-only order and position lookups).
READ_ROUTES = {
    "Angel": {
        "orderbook": ("GET", "/rest/secure/angelbroking/order/v1/getOrderBook"),
        "tradebook": ("GET", "/rest/secure/angelbroking/order/v1/getTradeBook"),
        "positions": ("GET", "/rest/secure/angelbroking/order/v1/getPosition"),
        "funds": ("GET", "/rest/secure/angelbroking/user/v1/getRMS"),
    },
    "Delta": {
        "orders": ("GET", "/v2/orders"),
        "positions": ("GET", "/v2/positions/margined"),
    },
}
ANGEL_STATES = {
    "complete": "COMPLETE",
    "open": "OPEN",
    "pending": "PENDING",
    "trigger pending": "PENDING",
    "validation pending": "PENDING",
    "after market order req received": "PENDING",
    "cancelled": "CANCELLED",
    "rejected": "REJECTED",
    "modify pending": "PENDING",
    "cancel pending": "CANCEL_REQUESTED",
    "partially filled": "PARTIALLY_FILLED",
}
_ALLOWED_EXCHANGES = {"NFO"}
# SmartAPI account snapshots can contain cash and other segment positions.
# Ignore recognized NON-NFO records, but reject unknown exchange codes and
# malformed NFO records. Never interpret cash positions as derivative contracts.
_NON_NFO_EXCHANGES = {"NSE", "BSE", "BFO", "CDS", "MCX", "NCDEX"}
_SYMBOL = re.compile(r"^[A-Z0-9._-]{4,72}$")
_MAX_RECORDS = 500


class BrokerSnapshotError(ValueError):
    pass


def _decimal(x: Any, label: str) -> Decimal:
    if isinstance(x, bool) or not isinstance(x, (str, int, Decimal)):
        raise BrokerSnapshotError(label + " must be an exact decimal")
    try:
        v = Decimal(x)
    except (InvalidOperation, TypeError):
        raise BrokerSnapshotError(label + " invalid") from None
    if not v.is_finite():
        raise BrokerSnapshotError(label + " must be finite")
    return v


def _integer(x: Any, label: str) -> int:
    if isinstance(x, bool):
        raise BrokerSnapshotError(label + " invalid")
    if isinstance(x, int):
        v = x
    elif isinstance(x, str) and re.fullmatch(r"-?\d+", x):
        v = int(x)
    else:
        raise BrokerSnapshotError(label + " must be integer")
    if abs(v) > 2_000_000_000:
        raise BrokerSnapshotError(label + " unreasonably large")
    return v


def readonly_route(broker: str, resource: str) -> dict[str, str]:
    """Return fixed method/path only, with no credentials and no URL assembly."""
    if broker not in READ_ROUTES or resource not in READ_ROUTES[broker]:
        raise BrokerSnapshotError("Unsupported read-only resource")
    method, path = READ_ROUTES[broker][resource]
    return {"method": method, "path": path, "mode": "READ_ONLY"}


def _rows(response: Any) -> Sequence[Mapping[str, Any]]:
    if not isinstance(response, Mapping) or response.get("status") is not True:
        raise BrokerSnapshotError("Angel broker response failed")
    data = response.get("data")
    if data is None:
        # Some APIs return null on a valid empty position book.
        return ()
    if not isinstance(data, list) or len(data) > _MAX_RECORDS:
        raise BrokerSnapshotError("Unexpected broker rows")
    if any(not isinstance(row, Mapping) for row in data):
        raise BrokerSnapshotError("Invalid broker row")
    return data


def angel_orders(response: Any) -> list[dict[str, Any]]:
    """Normalize Angel orderbook without treating unknown statuses as cancelled.

    Data shape is checked, not authenticated here. A transport must verify the
    broker TLS endpoint, API authentication and account ownership separately.
    """
    normalized: list[dict[str, Any]] = []
    seen: set[str] = set()
    for raw in _rows(response):
        order_id = raw.get("orderid")
        symbol = raw.get("tradingsymbol")
        exchange = raw.get("exchange")
        side = raw.get("transactiontype")
        raw_state = raw.get("orderstatus", raw.get("status"))
        if exchange in _NON_NFO_EXCHANGES:
            continue
        if exchange not in _ALLOWED_EXCHANGES:
            raise BrokerSnapshotError("Unrecognized Angel order exchange")
        if not isinstance(order_id, str) or not re.fullmatch(r"[A-Za-z0-9_-]{4,96}", order_id):
            raise BrokerSnapshotError("Invalid Angel order ID")
        if order_id in seen:
            raise BrokerSnapshotError("Duplicate Angel order ID")
        seen.add(order_id)
        if not isinstance(symbol, str) or not _SYMBOL.fullmatch(symbol):
            raise BrokerSnapshotError("Invalid Angel contract symbol")
        if side not in ("BUY", "SELL"):
            raise BrokerSnapshotError("Unsupported NFO order side")
        qty = _integer(raw.get("quantity"), "quantity")
        filled = _integer(raw.get("filledshares"), "filledshares")
        if qty <= 0 or not 0 <= filled <= qty:
            raise BrokerSnapshotError("Invalid Angel fill quantity")
        if not isinstance(raw_state, str):
            raise BrokerSnapshotError("Angel order status missing")
        state = ANGEL_STATES.get(raw_state.strip().lower(), "UNKNOWN")
        # Unknown must never become a final or filled order.
        normalized.append({
            "order_id": order_id,
            "symbol": symbol,
            "exchange": exchange,
            "side": side,
            "quantity": qty,
            "filled_quantity": filled,
            "status": state,
            "statusKnown": state != "UNKNOWN",
        })
    return normalized


def angel_positions(response: Any) -> list[dict[str, Any]]:
    """Normalize net signed quantities. Reject unfamiliar exchanges/fields."""
    result: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()
    for raw in _rows(response):
        symbol = raw.get("tradingsymbol")
        exchange = raw.get("exchange")
        token = raw.get("symboltoken")
        if exchange in _NON_NFO_EXCHANGES:
            continue
        if exchange not in _ALLOWED_EXCHANGES:
            raise BrokerSnapshotError("Unrecognized Angel position exchange")
        if not isinstance(symbol, str) or not _SYMBOL.fullmatch(symbol):
            raise BrokerSnapshotError("Position symbol invalid")
        if not isinstance(token, str) or not token:
            raise BrokerSnapshotError("Missing position instrument token")
        key = (exchange, symbol)
        if key in seen:
            raise BrokerSnapshotError("Duplicate position contract; aggregate only after broker verification")
        seen.add(key)
        net_quantity = _integer(raw.get("netqty"), "netqty")
        result.append({"symbol": symbol, "exchange": exchange,
                       "instrumentToken": token, "net_quantity": net_quantity})
    return result


def delta_snapshot_shape(response: Any, kind: str) -> dict[str, Any]:
    """Only structural validation, NOT a broker-authorized position check.

    Delta private endpoints have version-dependent response shapes. Preserve
    unknown fields only on the server; this function deliberately refuses to
    guess field mappings, order IDs, multipliers, or margin values.
    """
    if kind not in ("orders", "positions"):
        raise BrokerSnapshotError("Unknown Delta snapshot kind")
    if not isinstance(response, Mapping) or response.get("success") is not True:
        raise BrokerSnapshotError("Delta response failed")
    rows = response.get("result")
    if not isinstance(rows, list) or len(rows) > _MAX_RECORDS or any(
        not isinstance(row, Mapping) for row in rows
    ):
        raise BrokerSnapshotError("Unexpected Delta snapshot shape")
    return {
        "broker": "Delta",
        "resource": kind,
        "rowCount": len(rows),
        "schemaMapped": False,
        "tradingReady": False,
        "notice": "Delta positions/orders require broker-specific field mapping and account verification.",
    }


def snapshot_metadata(
    *, broker: str, resource: str, received_at: datetime,
    now: datetime, account_owner_verified: bool
) -> dict[str, Any]:
    """Age/audit metadata. Does NOT cryptographically authenticate the source."""
    readonly_route(broker, resource)
    if not isinstance(received_at, datetime) or received_at.utcoffset() is None:
        raise BrokerSnapshotError("Missing aware snapshot timestamp")
    if not isinstance(now, datetime) or now.utcoffset() is None:
        raise BrokerSnapshotError("Missing aware server timestamp")
    age = now - received_at
    fresh = timedelta(0) <= age <= timedelta(seconds=10)
    return {
        "broker": broker,
        "resource": resource,
        "ageSeconds": max(0, int(age.total_seconds())),
        "shapeOrTimingFresh": fresh,
        "ownerVerifiedByCaller": account_owner_verified is True,
        "liveExecutionEnabled": False,
        "canSubmitOrder": False,
        "notice": "Identity/source authentication MUST be enforced by the server transport.",
    }
