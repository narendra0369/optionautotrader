"""OptionX V7 pure, READ-ONLY broker/local reconciliation draft.

NOT wired to live accounts and NOT an exchange adapter. A broker adapter must
normalize statuses and verify source provenance before calling compare().
Unknown states always block new entries. No automatic cancel or retry.
"""
from __future__ import annotations

from datetime import datetime, timedelta
from typing import Mapping, Sequence, Any

MAX_SNAPSHOT_AGE = timedelta(seconds=10)
FINAL_STATES = {"COMPLETE", "REJECTED", "CANCELLED"}
ACTIVE_STATES = {"OPEN", "PENDING", "PARTIALLY_FILLED", "CANCEL_REQUESTED"}
ALLOWED_STATES = FINAL_STATES | ACTIVE_STATES


def _nonnegative_int(value: Any) -> int | None:
    return value if isinstance(value, int) and not isinstance(value, bool) and value >= 0 else None


def _fresh(snapshot_time: Any, now: datetime) -> bool:
    return (
        isinstance(snapshot_time, datetime)
        and snapshot_time.tzinfo is not None
        and snapshot_time.utcoffset() is not None
        and timedelta(0) <= now - snapshot_time <= MAX_SNAPSHOT_AGE
    )


def compare(
    *,
    tracked_orders: Sequence[Mapping[str, Any]],
    broker_orders: Sequence[Mapping[str, Any]],
    broker_positions: Sequence[Mapping[str, Any]],
    local_positions: Mapping[str, int],
    source_authenticated: bool,
    snapshot_time: datetime | None,
    now: datetime,
) -> dict[str, Any]:
    """Compare broker facts with local records; never permit submission.

    Required normalized order keys:
      order_id, symbol, side, quantity, filled_quantity, status
    Required position keys: symbol, net_quantity.
    Any unrecognized state, discrepancy, missing row or stale snapshot locks
    the *future* entry path. This function does not remedy broker orders.
    """
    blocks: list[str] = []
    if not isinstance(now, datetime) or now.tzinfo is None or now.utcoffset() is None:
        return {"reconciled": False, "newEntriesBlocked": True, "blocks": ["INVALID_SERVER_CLOCK"], "liveExecutionEnabled": False}
    if source_authenticated is not True:
        blocks.append("BROKER_SNAPSHOT_NOT_AUTHENTICATED")
    if not _fresh(snapshot_time, now):
        blocks.append("BROKER_SNAPSHOT_STALE_OR_UNKNOWN")
    if not all(isinstance(x, (list, tuple)) for x in (tracked_orders, broker_orders, broker_positions)):
        return {"reconciled": False, "newEntriesBlocked": True, "blocks": ["INVALID_SNAPSHOT_SHAPE"], "liveExecutionEnabled": False}
    if not isinstance(local_positions, Mapping):
        return {"reconciled": False, "newEntriesBlocked": True, "blocks": ["INVALID_LOCAL_POSITION_STATE"], "liveExecutionEnabled": False}

    local_by_id: dict[str, Mapping[str, Any]] = {}
    remote_by_id: dict[str, Mapping[str, Any]] = {}
    for row in tracked_orders:
        if not isinstance(row, Mapping):
            blocks.append("INVALID_TRACKED_ORDER")
            continue
        oid = row.get("order_id")
        if not isinstance(oid, str) or not oid:
            blocks.append("TRACKED_ORDER_ID_MISSING")
        elif oid in local_by_id:
            blocks.append("DUPLICATE_TRACKED_ORDER")
        else:
            local_by_id[oid] = row

    for row in broker_orders:
        if not isinstance(row, Mapping):
            blocks.append("INVALID_BROKER_ORDER")
            continue
        oid = row.get("order_id")
        if not isinstance(oid, str) or not oid:
            blocks.append("BROKER_ORDER_ID_MISSING")
            continue
        if oid in remote_by_id:
            blocks.append("DUPLICATE_BROKER_ORDER_ID")
            continue
        remote_by_id[oid] = row
        status = row.get("status")
        if status not in ALLOWED_STATES:
            blocks.append("UNKNOWN_BROKER_ORDER_STATUS")
        if status in ACTIVE_STATES:
            blocks.append("UNRESOLVED_BROKER_ORDER")
        qty = _nonnegative_int(row.get("quantity"))
        fill = _nonnegative_int(row.get("filled_quantity"))
        if qty is None or qty == 0 or fill is None or fill > qty:
            blocks.append("INVALID_BROKER_ORDER_QUANTITY")
        if not isinstance(row.get("symbol"), str) or not row["symbol"]:
            blocks.append("BROKER_ORDER_SYMBOL_MISSING")
        if row.get("side") not in ("BUY", "SELL"):
            blocks.append("BROKER_ORDER_SIDE_INVALID")
        if status == "COMPLETE" and qty is not None and fill is not None and qty != fill:
            blocks.append("COMPLETE_BUT_FILL_MISMATCH")
        if status == "REJECTED" and fill not in (0, None):
            blocks.append("REJECTED_BUT_HAS_FILLED_QUANTITY")

    for oid, local in local_by_id.items():
        remote = remote_by_id.get(oid)
        if remote is None:
            blocks.append("TRACKED_ORDER_MISSING_FROM_BROKER_BOOK")
            continue
        if local.get("symbol") != remote.get("symbol") or local.get("side") != remote.get("side"):
            blocks.append("ORDER_ID_MATCH_BUT_CONTRACT_DIFFERS")
        if _nonnegative_int(local.get("filled_quantity")) != _nonnegative_int(remote.get("filled_quantity")):
            blocks.append("LOCAL_BROKER_FILL_QUANTITY_MISMATCH")
    if set(remote_by_id) - set(local_by_id):
        # Manual user orders may exist. They must be explicitly excluded by an
        # owner-verified account partition rather than silently ignored.
        blocks.append("UNTRACKED_BROKER_ORDERS_REQUIRE_REVIEW")

    remote_positions: dict[str, int] = {}
    for row in broker_positions:
        if not isinstance(row, Mapping):
            blocks.append("INVALID_BROKER_POSITION")
            continue
        symbol = row.get("symbol")
        qty = row.get("net_quantity")
        if not isinstance(symbol, str) or not symbol or not isinstance(qty, int) or isinstance(qty, bool):
            blocks.append("INVALID_BROKER_POSITION")
            continue
        if symbol in remote_positions:
            blocks.append("DUPLICATE_BROKER_POSITION")
        remote_positions[symbol] = qty
    for symbol, qty in local_positions.items():
        if not isinstance(symbol, str) or not isinstance(qty, int) or isinstance(qty, bool):
            blocks.append("INVALID_LOCAL_POSITION")
        if remote_positions.get(symbol, 0) != qty:
            blocks.append("POSITION_MISMATCH")
    for symbol, qty in remote_positions.items():
        if local_positions.get(symbol, 0) != qty:
            blocks.append("UNACCOUNTED_BROKER_POSITION")

    return {
        "reconciled": not blocks,
        "newEntriesBlocked": True,  # V7 draft never authorizes entry
        "liveExecutionEnabled": False,
        "blocks": sorted(set(blocks)) if blocks else ["LIVE_EXECUTION_NOT_IMPLEMENTED"],
        "trackedCount": len(local_by_id),
        "brokerOrderCount": len(remote_by_id),
        "brokerPositionCount": len(remote_positions),
        "notice": "Comparison only; no broker modifications or order submissions.",
    }
