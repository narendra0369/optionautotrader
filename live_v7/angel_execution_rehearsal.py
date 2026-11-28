"""Angel One execution lifecycle verification rehearsal (OFFLINE / READ-ONLY).

A verified Angel profile is NOT an execution permission. This module consumes
normalized read-only broker snapshots supplied by a separately authenticated
owner-bound server. It contains NO network, token access, order endpoint,
credential storage, order submit/cancel/modify method, or live enable flag.

If a broker reply is unknown, delayed, rejected, partially filled or the
protective stop is not independently verified, further entries stay BLOCKED.
"""
from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any, Mapping, Sequence

_ALLOWED_BROKER_STATUSES = frozenset({
    "OPEN", "PENDING", "CANCEL_REQUESTED", "PARTIALLY_FILLED",
    "COMPLETE", "REJECTED", "CANCELLED",
})
_PROTECTION_STATUSES = frozenset({"OPEN", "TRIGGER_PENDING"})
_MAX_AGE = timedelta(seconds=10)


def _timestamp_is_fresh(value: Any, now: datetime) -> bool:
    return (isinstance(value, datetime) and value.utcoffset() is not None
            and isinstance(now, datetime) and now.utcoffset() is not None
            and timedelta(0) <= now - value <= _MAX_AGE)


def _integer(value: Any, *, minimum: int = 0) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and value >= minimum


def _result(blockers: list[str], *, filled: int = 0, protected: int = 0) -> dict[str, Any]:
    return {
        "mode": "READONLY_ANGEL_LIFECYCLE_REHEARSAL",
        "broker": "Angel",
        "liveExecutionEnabled": False,
        "canSubmitOrder": False,
        "canModifyOrder": False,
        "canCancelOrder": False,
        "newEntriesBlocked": True,
        "protectiveStopVerifiedForRehearsal": not blockers and filled > 0 and protected == filled,
        "filledQuantity": filled,
        "protectedQuantity": protected,
        "blockedReasons": sorted(set(blockers)) if blockers else ["BROKER_EXECUTION_NOT_IMPLEMENTED"],
    }


def verify_rehearsal(
    *,
    expected_owner_id: str,
    expected_entry_order_id: str,
    expected_symbol: str,
    expected_token: str,
    expected_quantity: int,
    count_entries_today: int,
    broker_orderbook: Sequence[Mapping[str, Any]] | None,
    broker_positions: Sequence[Mapping[str, Any]] | None,
    protection_orderbook: Sequence[Mapping[str, Any]] | None,
    trusted_meta: Mapping[str, Any] | None,
    now: datetime,
) -> dict[str, Any]:
    """Check one Angel BUY entry and the independent opposite-side STOP.

    Data must be independently authenticated and normalized in the server.
    The output is NEVER permission to place an order (even when all pass).
    """
    blocked: list[str] = []
    if not isinstance(expected_owner_id, str) or len(expected_owner_id) < 8:
        blocked.append("EXPECTED_OWNER_UNVERIFIED")
    if not isinstance(expected_entry_order_id, str) or len(expected_entry_order_id) < 4:
        blocked.append("ENTRY_ORDER_ID_MISSING")
    if not isinstance(expected_symbol, str) or not expected_symbol or len(expected_symbol) > 72:
        blocked.append("EXPECTED_CONTRACT_UNVERIFIED")
    if not isinstance(expected_token, str) or not expected_token:
        blocked.append("EXPECTED_TOKEN_UNVERIFIED")
    if not _integer(expected_quantity, minimum=1):
        blocked.append("EXPECTED_QUANTITY_INVALID")
    if not _integer(count_entries_today) or count_entries_today > 2:
        blocked.append("DAILY_ENTRY_COUNT_UNVERIFIED_OR_EXCEEDED")
    if count_entries_today == 2:
        blocked.append("TWO_DAILY_ENTRIES_ALREADY_USED")

    meta = trusted_meta if isinstance(trusted_meta, Mapping) else {}
    if meta.get("broker") != "Angel" or meta.get("owner_id") != expected_owner_id:
        blocked.append("BROKER_OWNER_MISMATCH")
    for field in ("broker_tls_authenticated", "owner_session_verified", "source_is_readonly"):
        if meta.get(field) is not True:
            blocked.append("UNVERIFIED_" + field.upper())
    if not _timestamp_is_fresh(meta.get("observed_at"), now):
        blocked.append("BROKER_SNAPSHOT_STALE_OR_MISSING")
    if meta.get("unknown_order_outcomes") is not False:
        blocked.append("UNKNOWN_ORDER_OUTCOME")
    if meta.get("manual_intervention_pending") is not False:
        blocked.append("MANUAL_RECONCILIATION_REQUIRED")

    if (not isinstance(broker_orderbook, (list, tuple))
            or not isinstance(broker_positions, (list, tuple))
            or not isinstance(protection_orderbook, (list, tuple))):
        return _result(blocked + ["BROKER_BOOKS_MISSING"])
    if any(not isinstance(row, Mapping) for rows in (
            broker_orderbook, broker_positions, protection_orderbook) for row in rows):
        return _result(blocked + ["BROKER_ROW_MALFORMED"])
    if any(len(rows) > 500 for rows in (broker_orderbook, broker_positions, protection_orderbook)):
        return _result(blocked + ["BROKER_BOOK_OVERSIZED"])

    if any(o.get("status") not in _ALLOWED_BROKER_STATUSES for o in broker_orderbook):
        blocked.append("UNKNOWN_BROKER_ORDER_STATUS")
    matched = [o for o in broker_orderbook if o.get("order_id") == expected_entry_order_id]
    filled = 0
    if len(matched) != 1:
        blocked.append("ENTRY_MISSING_OR_DUPLICATE_IN_BROKER_BOOK")
    else:
        order = matched[0]
        if order.get("symbol") != expected_symbol or order.get("side") != "BUY":
            blocked.append("ENTRY_IDENTITY_MISMATCH")
        if order.get("quantity") != expected_quantity:
            blocked.append("ENTRY_QUANTITY_MISMATCH")
        f = order.get("filled_quantity")
        if not _integer(f) or not _integer(expected_quantity, minimum=1) or f > expected_quantity:
            blocked.append("FILL_QUANTITY_INVALID")
        else:
            filled = f
        if order.get("status") != "COMPLETE" or filled != expected_quantity:
            blocked.append("ENTRY_NOT_FULLY_CONFIRMED")

    positions = [p for p in broker_positions
                 if p.get("symbol") == expected_symbol and p.get("instrumentToken") == expected_token]
    if len(positions) != 1 or not _integer(positions[0].get("net_quantity"), minimum=1):
        blocked.append("BROKER_POSITION_MISSING_OR_AMBIGUOUS")
    elif positions[0]["net_quantity"] != filled:
        blocked.append("BROKER_POSITION_FILL_MISMATCH")

    candidates = [o for o in protection_orderbook
                  if o.get("contract_token") == expected_token
                  and o.get("action") == "EXIT_SELL"]
    protected = 0
    if len(candidates) != 1:
        blocked.append("STOP_MISSING_OR_DUPLICATE")
    else:
        stop = candidates[0]
        quantity = stop.get("protected_quantity")
        if (not isinstance(stop.get("broker_order_id"), str)
                or len(stop["broker_order_id"]) < 4
                or stop["broker_order_id"] == expected_entry_order_id):
            blocked.append("STOP_BROKER_ORDER_ID_INVALID")
        if stop.get("status") not in _PROTECTION_STATUSES:
            blocked.append("STOP_NOT_ACTIVE_ON_BROKER")
        if stop.get("contract_symbol") != expected_symbol or stop.get("broker") != "Angel":
            blocked.append("STOP_CONTRACT_MISMATCH")
        if not _timestamp_is_fresh(stop.get("as_of"), now):
            blocked.append("STOP_ACK_STALE")
        if not _integer(quantity, minimum=1):
            blocked.append("PROTECTED_QUANTITY_INVALID")
        else:
            protected = quantity
        if protected != filled:
            blocked.append("STOP_DOES_NOT_COVER_CONFIRMED_FILL")

    if filled == 0:
        blocked.append("NO_VERIFIED_FILL")
    return _result(blocked, filled=filled, protected=protected)
