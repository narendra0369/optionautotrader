"""OptionX V7 offline-only bracket/recovery event replay.

No broker SDK, HTTP, credentials, secrets, order placement or real execution.
This deterministic observer consumes synthetic/normalized broker events and
detects partial fills, stale broker evidence, oversized exits, missing stop
coverage, duplicate events, unknown acknowledgements and restart uncertainty.

A successful shadow replay is NOT proof of exchange-side SL/Target protection.
Actual orderbook/tradebook and exchange-native order-type tests remain necessary.
"""
from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any, Mapping, Sequence

MAX_EVIDENCE_AGE = timedelta(seconds=10)
KINDS = frozenset({
    "ENTRY_ACK", "ENTRY_FILL", "ENTRY_REJECT", "ENTRY_UNKNOWN",
    "STOP_ACK", "STOP_REJECT", "STOP_UNKNOWN", "EXIT_FILL",
    "CANCEL_ACK", "RECONCILED",
})


class ReplayError(ValueError):
    pass


def _quantity(value: Any) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ReplayError("Cumulative fill quantity must be a nonnegative integer")
    return value


def replay(
    events: Sequence[Mapping[str, Any]],
    *,
    planned_entry_quantity: int,
    now: datetime,
    verified_account: bool,
    full_broker_reconciliation_after_restart: bool = False,
    restart_occurred: bool = False,
) -> dict[str, Any]:
    """Read-only replay. Unknown states never unlock an execution gate.

    Events must come from a trusted normalized broker source for real
    observation; caller-supplied flags alone do not constitute authentication.
    Event quantities are cumulative, not deltas. No event creates an order.
    """
    errors: list[str] = []
    if isinstance(planned_entry_quantity, bool) or not isinstance(planned_entry_quantity, int) or planned_entry_quantity <= 0:
        raise ReplayError("Positive planned quantity required")
    if not isinstance(now, datetime) or now.utcoffset() is None:
        raise ReplayError("Timezone-aware server clock required")
    if not isinstance(events, (tuple, list)) or len(events) > 1000:
        raise ReplayError("Invalid event stream")
    if verified_account is not True:
        errors.append("OWNER_ACCOUNT_NOT_VERIFIED")

    entry_filled = 0
    exit_filled = 0
    stop_protected = 0
    entry_order_unknown = False
    stop_order_unknown = False
    entry_rejected = False
    stop_rejected = False
    stop_ack_seen = False
    seen: set[str] = set()
    previous_time: datetime | None = None

    for raw in events:
        if not isinstance(raw, Mapping):
            errors.append("INVALID_EVENT_SHAPE")
            continue
        kind = raw.get("kind")
        event_id = raw.get("event_id")
        when = raw.get("as_of")
        if kind not in KINDS:
            errors.append("UNKNOWN_EVENT_KIND")
            continue
        if not isinstance(event_id, str) or not event_id.isascii() or not (8 <= len(event_id) <= 96):
            errors.append("INVALID_EVENT_ID")
            continue
        if event_id in seen:
            errors.append("DUPLICATE_EVENT")
            continue
        seen.add(event_id)
        if raw.get("source_verified") is not True:
            errors.append("BROKER_EVENT_NOT_AUTHENTICATED")
            continue
        if not isinstance(when, datetime) or when.utcoffset() is None:
            errors.append("EVENT_TIMESTAMP_MISSING")
            continue
        if when > now or previous_time is not None and when < previous_time:
            errors.append("EVENT_OUT_OF_ORDER_OR_FROM_FUTURE")
            continue
        previous_time = when

        if kind == "ENTRY_UNKNOWN":
            entry_order_unknown = True
        elif kind == "STOP_UNKNOWN":
            stop_order_unknown = True
        elif kind == "ENTRY_REJECT":
            if entry_filled > 0:
                errors.append("REJECTED_AFTER_ENTRY_FILL")
            entry_rejected = True
        elif kind == "STOP_REJECT":
            stop_rejected = True
            stop_protected = 0
        elif kind == "ENTRY_FILL":
            try:
                n = _quantity(raw.get("cumulative_quantity"))
                if n <= entry_filled or n > planned_entry_quantity:
                    errors.append("INVALID_OR_REGRESSING_ENTRY_FILL")
                elif entry_rejected:
                    errors.append("FILL_AFTER_ENTRY_REJECTION")
                else:
                    entry_filled = n
                    if stop_ack_seen and stop_protected < entry_filled:
                        errors.append("NEW_FILL_EXCEEDS_STOP_COVERAGE")
            except ReplayError:
                errors.append("INVALID_ENTRY_FILL_QUANTITY")
        elif kind == "EXIT_FILL":
            try:
                n = _quantity(raw.get("cumulative_quantity"))
                if n <= exit_filled or n > entry_filled:
                    errors.append("EXIT_REPLAY_OR_POSSIBLE_NAKED_SHORT")
                else:
                    exit_filled = n
                    # A real trailing stop or target OCO needs fresh broker
                    # confirmation after an exit; never trust old stop coverage.
                    stop_order_unknown = True
            except ReplayError:
                errors.append("INVALID_EXIT_FILL_QUANTITY")
        elif kind == "STOP_ACK":
            try:
                n = _quantity(raw.get("protected_quantity"))
                net = entry_filled - exit_filled
                if n <= 0 or n > net:
                    errors.append("STOP_COVERAGE_INCONSISTENT_WITH_OPEN_POSITION")
                else:
                    stop_protected = n
                    stop_ack_seen = True
                    stop_rejected = False
                    stop_order_unknown = False
            except ReplayError:
                errors.append("INVALID_PROTECTION_QUANTITY")
        elif kind == "RECONCILED":
            # Explicit broker book + position comparison is the sole route
            # for clearing unknown ACKs. Check must be externally verified.
            if raw.get("full_orderbook_verified") is True and raw.get("position_verified") is True:
                entry_order_unknown = False
                stop_order_unknown = False
            else:
                errors.append("RECONCILIATION_NOT_VERIFIED")
        elif kind == "CANCEL_ACK":
            # Cancellation may race a fill; require a new broker snapshot.
            stop_order_unknown = True

    if restart_occurred and full_broker_reconciliation_after_restart is not True:
        errors.append("RESTART_REQUIRES_FULL_BROKER_RECONCILIATION")
    if events and previous_time is not None and not timedelta(0) <= now - previous_time <= MAX_EVIDENCE_AGE:
        errors.append("BROKER_EVIDENCE_STALE")
    net_open = entry_filled - exit_filled
    if net_open < 0:
        errors.append("IMPOSSIBLE_NEGATIVE_POSITION")
    if net_open > 0 and stop_protected < net_open:
        errors.append("OPEN_POSITION_WITHOUT_FULL_STOP_COVERAGE")
    if entry_order_unknown or stop_order_unknown:
        errors.append("UNKNOWN_BROKER_ORDER_OUTCOME")
    if stop_rejected and net_open:
        errors.append("BROKER_STOP_REJECTED")
    if entry_rejected and entry_filled:
        errors.append("BROKER_ENTRY_STATE_CONFLICT")
    if net_open == 0 and stop_protected:
        errors.append("POSSIBLE_ORPHAN_STOP_ORDER")

    return {
        "mode": "OFFLINE_OBSERVATION_ONLY",
        "plannedQuantity": planned_entry_quantity,
        "entryFilledQuantity": entry_filled,
        "exitFilledQuantity": exit_filled,
        "netOpenQuantity": net_open,
        "lastStopAcknowledgedQuantity": stop_protected,
        "observedEventCount": len(seen),
        "anomalies": sorted(set(errors)),
        "shadowEvidenceConsistent": not errors,
        "liveExecutionEnabled": False,
        "newEntriesBlocked": True,
        "canSubmitOrder": False,
        "notice": "Synthetic replay cannot guarantee stop execution or broker-side OCO behavior.",
    }
