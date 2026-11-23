"""OptionX V7 — protective stop/target planner, NO ORDER EXECUTION.

This module only evaluates the protection *needed* after confirmed fills.
It never sends a stop, target or cancel request. A local quote crossing the
target is NOT proof of a fill, and a stop price is NOT a guaranteed exit.

For live use, brokerage/exchange-native protective order support and its
acknowledgement must be verified first. Unknown or partial fills require
broker reconciliation and fail closed.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from decimal import Decimal, InvalidOperation
from typing import Any, Mapping

MAX_FILL_VERIFICATION_AGE = timedelta(seconds=10)
MAX_PROTECTION_VERIFICATION_AGE = timedelta(seconds=10)


class ProtectionError(ValueError):
    pass


def _money(v: Any, name: str) -> Decimal:
    if isinstance(v, bool) or not isinstance(v, (int, str, Decimal)):
        raise ProtectionError(name + " must be exact decimal")
    try:
        result = Decimal(v)
    except (InvalidOperation, TypeError):
        raise ProtectionError(name + " invalid") from None
    if not result.is_finite():
        raise ProtectionError(name + " invalid")
    return result


def _now(v: Any, name: str) -> datetime:
    if not isinstance(v, datetime) or v.utcoffset() is None:
        raise ProtectionError(name + " requires timezone-aware datetime")
    return v


@dataclass(frozen=True)
class ConfirmedLongFill:
    owner_id: str
    broker: str
    broker_order_id: str
    contract_token: str
    contract_symbol: str
    purchased_quantity: int
    net_open_quantity: int
    average_fill_price: Decimal
    verified_at: datetime


def protection_requirements(
    *,
    fill: ConfirmedLongFill,
    stop_price: str,
    target_price: str,
    tick_size: str,
    contract_multiplier: str,
    lot_size: int,
    now: datetime,
    trusted: Mapping[str, Any],
) -> dict[str, Any]:
    """Describe a stop+target protection requirement for an existing LONG fill.

    A future broker-specific worker must independently verify it can place a
    broker-native protective stop and handle target/stop OCO races, fills,
    cancel rejects, network outage, liquidation, and manual orders.
    """
    now = _now(now, "now")
    reasons: list[str] = []
    if not isinstance(fill, ConfirmedLongFill):
        return _output(["CONFIRMED_LONG_FILL_MISSING"])
    if not isinstance(trusted, Mapping):
        return _output(["TRUSTED_BROKER_STATE_MISSING"])
    if (
        not isinstance(fill.owner_id, str) or not fill.owner_id or
        not isinstance(fill.broker_order_id, str) or not fill.broker_order_id or
        not isinstance(fill.contract_token, str) or not fill.contract_token
    ):
        reasons.append("FILL_IDENTITY_MISSING")
    if fill.broker not in ("Angel", "Delta"):
        reasons.append("UNKNOWN_BROKER")
    if not isinstance(fill.purchased_quantity, int) or isinstance(fill.purchased_quantity, bool):
        reasons.append("INVALID_PURCHASE_QUANTITY")
    if not isinstance(fill.net_open_quantity, int) or isinstance(fill.net_open_quantity, bool):
        reasons.append("INVALID_OPEN_QUANTITY")
    if not isinstance(lot_size, int) or isinstance(lot_size, bool) or lot_size <= 0:
        reasons.append("LOT_SIZE_UNVERIFIED")
        lot_size = 0
    if not reasons and (
        fill.purchased_quantity <= 0
        or fill.net_open_quantity <= 0
        or fill.net_open_quantity > fill.purchased_quantity
        or fill.net_open_quantity % lot_size != 0
    ):
        reasons.append("FILLED_QUANTITY_NOT_RECONCILED")
    try:
        entry = _money(fill.average_fill_price, "average fill")
        stop = _money(stop_price, "stop")
        target = _money(target_price, "target")
        tick = _money(tick_size, "tick")
        multiplier = _money(contract_multiplier, "multiplier")
        if not (entry > stop > 0 and target > entry and tick > 0 and multiplier > 0):
            reasons.append("INVALID_PRICE_RISK_STRUCTURE")
        if tick > 0 and (stop % tick != 0 or target % tick != 0):
            reasons.append("TICK_SIZE_MISMATCH")
    except ProtectionError:
        entry = stop = target = tick = multiplier = Decimal(0)
        reasons.append("UNVERIFIED_PRICE_DATA")
    try:
        stamp = _now(fill.verified_at, "fill verification time")
        if not timedelta(0) <= now - stamp <= MAX_FILL_VERIFICATION_AGE:
            reasons.append("FILL_SNAPSHOT_STALE")
    except ProtectionError:
        reasons.append("FILL_SNAPSHOT_TIMESTAMP_UNVERIFIED")
    for field in (
        "broker_source_authenticated",
        "account_owner_verified",
        "position_reconciled",
        "orderbook_reconciled",
        "protective_order_type_broker_verified",
        "stop_exit_supported_for_contract",
        "kill_switch_health_verified",
    ):
        if trusted.get(field) is not True:
            reasons.append("MISSING_" + field.upper())
    if trusted.get("broker_has_unresolved_orders") is not False:
        reasons.append("UNRESOLVED_ORDER_PRESENT")
    if trusted.get("live_exit_engine_approved_and_tested") is not True:
        reasons.append("EXIT_ENGINE_NOT_APPROVED_OR_TESTED")
    if fill.broker == "Delta" and trusted.get("reduce_only_enforced_by_exchange") is not True:
        reasons.append("DELTA_REDUCE_ONLY_UNVERIFIED")
    if fill.broker == "Angel" and trusted.get("angel_buy_to_sell_exit_rules_verified") is not True:
        reasons.append("ANGEL_EXIT_RULES_UNVERIFIED")

    exposure = str((entry - stop) * multiplier * fill.net_open_quantity) if (
        entry > stop > 0 and multiplier > 0 and isinstance(fill.net_open_quantity, int)
    ) else None
    return _output(reasons, {
        "symbol": fill.contract_symbol,
        "quantityToProtect": str(fill.net_open_quantity),
        "stopTrigger": str(stop),
        "targetLimit": str(target),
        "lossAtStopBeforeCosts": exposure,
        "warning": "Stop fills, gaps, option spread and broker rejection can exceed this estimate.",
    })


def verify_protection_ack(
    *,
    fill: ConfirmedLongFill,
    broker_snapshot: Mapping[str, Any],
    now: datetime,
) -> dict[str, Any]:
    """Read-only check that protective STOP acknowledgement really exists.

    The future trusted adapter must translate the broker's actual orderbook
    fields, verify the stop order is opposite-side, correct contract, covered
    quantity, active, and not already cancelled/rejected.
    """
    _now(now, "now")
    reasons = []
    if not isinstance(fill, ConfirmedLongFill) or not isinstance(broker_snapshot, Mapping):
        return _output(["PROTECTION_SNAPSHOT_MISSING"])
    if broker_snapshot.get("source_authenticated") is not True:
        reasons.append("BROKER_PROTECTION_STATUS_UNAUTHENTICATED")
    if broker_snapshot.get("broker") != fill.broker:
        reasons.append("PROTECTION_BROKER_MISMATCH")
    if broker_snapshot.get("contract_token") != fill.contract_token:
        reasons.append("PROTECTION_CONTRACT_MISMATCH")
    if broker_snapshot.get("action") != "EXIT_SELL":
        reasons.append("PROTECTION_SIDE_MISMATCH")
    if broker_snapshot.get("status") not in ("OPEN", "TRIGGER_PENDING"):
        reasons.append("PROTECTIVE_STOP_NOT_ACKNOWLEDGED")
    protected = broker_snapshot.get("protected_quantity")
    if not isinstance(protected, int) or isinstance(protected, bool) or protected != fill.net_open_quantity:
        reasons.append("PROTECTION_QUANTITY_MISMATCH")
    if broker_snapshot.get("broker_order_id") in ("", None):
        reasons.append("PROTECTIVE_STOP_ID_MISSING")
    stamp = broker_snapshot.get("as_of")
    if not isinstance(stamp, datetime) or stamp.utcoffset() is None or not timedelta(0) <= now - stamp <= MAX_PROTECTION_VERIFICATION_AGE:
        reasons.append("PROTECTIVE_STOP_SNAPSHOT_STALE")
    return _output(reasons, {"protectedQuantity": str(protected)})


def _output(blocks: list[str], details: dict[str, Any] | None = None) -> dict[str, Any]:
    return {
        "stage": "NON_EXECUTING_PROTECTIVE_EXIT_RESEARCH",
        "protectionAcceptedForShadowReview": not blocks,
        "canSendStopOrTarget": False,
        "liveExecutionEnabled": False,
        "blockedReasons": sorted(set(blocks)) if blocks else ["NO_BROKER_EXECUTION_ADAPTER"],
        "details": details or {},
    }
