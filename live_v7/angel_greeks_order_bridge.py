"""Pure offline Greeks -> Angel LIMIT/STOPLOSS_LIMIT contract bridge.

No broker order submission, credentials, network or owner approval issuance.
All authenticated broker inputs must originate independently on AWS; browser
data MUST NEVER be used as an authority for contract, quote or risk snapshot.
The target is deliberately a research level: NOT a simultaneous SELL order
while a broker STOPLOSS_LIMIT may still be open.
"""
from __future__ import annotations

from decimal import Decimal, ROUND_CEILING, ROUND_FLOOR
from typing import Any, Mapping

from live_v7.angel_order_contracts import (
    OrderContractError, limit_entry, money, protective_stop, standard_contract,
)

RR = Decimal("3")


def _price(value: Any, tick: Decimal, *, rounding: str) -> Decimal:
    raw = money(value, "PRICE")
    if tick <= 0:
        raise OrderContractError("INVALID_TICK_SIZE")
    return (raw / tick).to_integral_value(rounding=rounding) * tick


def _validated_plan(*, selected: Mapping[str, Any], plan: Mapping[str, Any],
                    contract: Mapping[str, Any], quantity: int) -> tuple[Decimal, Decimal, Decimal]:
    if not isinstance(selected, Mapping) or not isinstance(plan, Mapping):
        raise OrderContractError("GREEKS_PLAN_MISSING")
    symbol, token, lot, tick = standard_contract(contract)
    if (selected.get("realOrdersEnabled") is not False
            or selected.get("symbol") != symbol
            or selected.get("token") != token
            or selected.get("side") != contract.get("kind")
            or selected.get("market") != contract.get("market")
            or selected.get("lotSize") != lot
            or selected.get("selection") != "nearest_actual_strike_nearest_expiry"):
        raise OrderContractError("ATM_CONTRACT_IDENTITY_MISMATCH")
    if (plan.get("mode") != "AUTO_PAPER_RESEARCH_NO_ORDERS"
            or plan.get("contract") != symbol
            or plan.get("side") != selected.get("side")
            or plan.get("quantity") != quantity
            or plan.get("canSubmitOrder") is not False):
        raise OrderContractError("GREEKS_PLAN_IDENTITY_MISMATCH")
    premium = money(plan.get("entryPremium"), "PREMIUM")
    stop = money(plan.get("stopTrigger"), "STOP")
    target = money(plan.get("targetLimit"), "TARGET")
    stop_limit = money(plan.get("stopLimit"), "STOP_LIMIT")
    if (not 0 < stop_limit <= stop < premium < target
            or not all(p % tick == 0 for p in (premium, stop, stop_limit, target))):
        raise OrderContractError("INVALID_GREEKS_EXIT_LEVELS")
    # Exit level must respect the user's chosen 1:3 research target; no
    # broker fill guarantee, costs/gaps are separately accounted for.
    if target - premium < RR * (premium - stop):
        raise OrderContractError("GREEKS_TARGET_BELOW_RR3")
    return stop, stop_limit, target


def preview_entry(*, selected: Mapping[str, Any], plan: Mapping[str, Any],
                  contract: Mapping[str, Any], quote: Mapping[str, Any],
                  owner_snapshot: Mapping[str, Any], now,
                  producttype: str = "INTRADAY") -> dict:
    """Build an offline LIMIT proposal; never allow its dispatch."""
    _, _, _, tick = standard_contract(contract)
    quantity = plan.get("quantity") if isinstance(plan, Mapping) else None
    stop, stop_limit, target = _validated_plan(
        selected=selected, plan=plan, contract=contract, quantity=quantity)
    if not isinstance(quote, Mapping):
        raise OrderContractError("BROKER_QUOTE_MISSING")
    # Bid/ask are authenticated execution quotes, not LTP.
    ask = money(quote.get("ask"), "ASK")
    entry = _price(ask, tick, rounding=ROUND_CEILING)
    if entry <= stop or target <= entry:
        raise OrderContractError("GREEKS_LEVELS_INVALID_FOR_CURRENT_ASK")
    # The original theoretical RR3 must still hold at the actual offer;
    # otherwise a moved premium invalidates the paper research plan.
    if target - entry < RR * (entry - stop):
        raise OrderContractError("RR3_NOT_POSSIBLE_AT_CURRENT_ASK")
    if not isinstance(owner_snapshot, Mapping):
        raise OrderContractError("OWNER_SNAPSHOT_MISSING")
    if (money(owner_snapshot.get("planned_stop_trigger"), "STOP") != stop
            or owner_snapshot.get("broker_native_stop_supported") is not True):
        raise OrderContractError("BROKER_STOP_PLAN_MISMATCH")
    entry_contract = limit_entry(
        market=selected["market"], contract=contract, quote=quote,
        quantity=quantity, limit_price=str(entry), owner_snapshot=owner_snapshot,
        now=now, producttype=producttype)
    return {
        "mode": "GREeks_RR3_LIMIT_PREVIEW_ONLY",
        "entry": entry_contract,
        "plannedStopTrigger": str(stop),
        "plannedStopLimit": str(stop_limit),
        "plannedTargetLimit": str(target),
        "theoreticalRR": "1:3",
        "targetOrderDispatchAllowed": False,
        "requiresBrokerConfirmedEntryFill": True,
        "requiresFreshBrokerPositionAndStopAck": True,
        "estimatedFillTimeSeconds": None,
        "canSubmitOrder": False,
        "liveExecutionEnabled": False,
    }


def preview_protective_stop(*, selected: Mapping[str, Any], plan: Mapping[str, Any],
                            contract: Mapping[str, Any], confirmed_fill: Mapping[str, Any],
                            broker_state: Mapping[str, Any], now,
                            producttype: str = "INTRADAY") -> dict:
    """Broker STOP proposal ONLY after independently verified full fill."""
    quantity = plan.get("quantity") if isinstance(plan, Mapping) else None
    stop, stop_limit, _ = _validated_plan(
        selected=selected, plan=plan, contract=contract, quantity=quantity)
    result = protective_stop(
        contract=contract, confirmed_fill=confirmed_fill,
        broker_state=broker_state, trigger_price=str(stop),
        limit_price=str(stop_limit), now=now, producttype=producttype)
    return {**result,
            "mode": "GREEKS_RR3_STOP_PREVIEW_ONLY",
            "canSubmitOrder": False, "liveExecutionEnabled": False,
            "targetOrderDispatchAllowed": False}
