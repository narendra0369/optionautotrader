"""Angel One order request contracts — OFFLINE ONLY, never submit.

This file builds strict data-only LIMIT-entry and STOPLOSS_LIMIT-exit payloads
for independent broker certification. It is NOT an order transport. No HTTP,
broker SDK, credentials, token storage, order dispatch or live gate is provided.
All trusted facts must come from authenticated backend adapters, NEVER browser
fields. Broker orders stay hard-locked until static IP, approval, durable
journal, broker-native protection and recovery tests are independently done.
"""
from __future__ import annotations

from datetime import datetime, timedelta
from decimal import Decimal, InvalidOperation
from typing import Any, Mapping
from zoneinfo import ZoneInfo

IST = ZoneInfo("Asia/Kolkata")
MAX_QUOTE_AGE = timedelta(seconds=10)
MAX_ORDERS_PER_DAY = 2
MARKETS = {"NIFTY", "BANKNIFTY"}
PRODUCTS = {"INTRADAY", "CARRYFORWARD"}


class OrderContractError(ValueError):
    """Safe fixed reason for an invalid potential order; no broker secrets."""


def money(raw: Any, field: str) -> Decimal:
    if isinstance(raw, bool) or not isinstance(raw, (int, str, Decimal)):
        raise OrderContractError("INVALID_" + field.upper())
    try:
        value = Decimal(raw)
    except (ValueError, InvalidOperation, TypeError):
        raise OrderContractError("INVALID_" + field.upper()) from None
    if not value.is_finite() or abs(value) > Decimal("1000000000"):
        raise OrderContractError("INVALID_" + field.upper())
    return value


def posint(raw: Any, field: str, *, minimum: int = 1) -> int:
    if isinstance(raw, bool) or not isinstance(raw, int) or raw < minimum or raw > 10_000_000:
        raise OrderContractError("INVALID_" + field.upper())
    return raw


def tick_aligned(price: Decimal, tick: Decimal, field: str) -> None:
    if tick <= 0 or price <= 0 or price % tick != 0:
        raise OrderContractError("INVALID_TICK_" + field.upper())


def require(condition: bool, code: str) -> None:
    if not condition:
        raise OrderContractError(code)


def standard_contract(contract: Mapping[str, Any]) -> tuple[str, str, int, Decimal]:
    require(isinstance(contract, Mapping), "BROKER_CONTRACT_MISSING")
    require(contract.get("broker") == "Angel" and contract.get("exchange") == "NFO", "WRONG_BROKER_EXCHANGE")
    require(contract.get("verified_from_broker") is True, "UNVERIFIED_BROKER_CONTRACT")
    symbol = contract.get("tradingsymbol")
    token = contract.get("symboltoken")
    require(isinstance(symbol, str) and symbol.isascii() and 8 <= len(symbol) <= 72
            and all(ch.isupper() or ch.isdigit() or ch in "._-" for ch in symbol),
            "INVALID_CONTRACT_SYMBOL")
    require(isinstance(token, str) and token.isdigit() and 1 <= len(token) <= 24,
            "INVALID_CONTRACT_TOKEN")
    lot = posint(contract.get("lot_size"), "LOT_SIZE")
    tick = money(contract.get("tick_size"), "TICK_SIZE")
    require(tick > 0, "INVALID_TICK_SIZE")
    return symbol, token, lot, tick


def certified_owner(snapshot: Mapping[str, Any], *, now: datetime) -> None:
    require(isinstance(snapshot, Mapping), "TRUSTED_ACCOUNT_SNAPSHOT_MISSING")
    for field in (
        "owner_account_verified", "broker_session_verified", "broker_orders_reconciled",
        "static_ip_registered_with_angel", "algo_api_approved_by_broker",
        "kill_switch_healthy", "margin_verified", "contract_master_fresh",
        "trade_day_calendar_verified", "risk_limits_approved_by_owner",
    ):
        require(snapshot.get(field) is True, "NOT_VERIFIED_" + field.upper())
    require(snapshot.get("emergency_stop") is False, "EMERGENCY_STOP_ACTIVE")
    require(snapshot.get("unresolved_or_unknown_orders") is False, "UNRESOLVED_ORDER")
    require(snapshot.get("existing_market_exposure") is False, "EXISTING_MARKET_EXPOSURE")
    require(isinstance(now, datetime) and now.utcoffset() is not None, "INVALID_SERVER_TIME")
    quote_at = snapshot.get("quote_at")
    require(isinstance(quote_at, datetime) and quote_at.utcoffset() is not None
            and timedelta(0) <= now - quote_at <= MAX_QUOTE_AGE, "QUOTE_STALE_OR_MISSING")
    local = now.astimezone(IST)
    require(local.weekday() < 5 and (local.hour, local.minute) >= (9, 15)
            and (local.hour, local.minute) < (14, 45), "OUTSIDE_VERIFIED_ENTRY_WINDOW")
    count = posint(snapshot.get("entries_reserved_today"), "DAILY_ENTRIES", minimum=0)
    require(count < MAX_ORDERS_PER_DAY, "DAILY_TWO_ENTRIES_EXHAUSTED")
    require(snapshot.get("unique_intent_reserved_durably") is True,
            "DURABLE_IDEMPOTENCY_RESERVATION_MISSING")


def limit_entry(*, market: str, contract: Mapping[str, Any],
                quote: Mapping[str, Any], quantity: int,
                limit_price: str, owner_snapshot: Mapping[str, Any],
                now: datetime, producttype: str = "INTRADAY") -> dict[str, Any]:
    """Build LIMIT DAY BUY payload for a verified NFO option; NO ORDER SEND."""
    require(market in MARKETS, "UNSUPPORTED_MARKET")
    require(producttype in PRODUCTS, "UNSUPPORTED_PRODUCT")
    certified_owner(owner_snapshot, now=now)
    symbol, token, lot, tick = standard_contract(contract)
    require(contract.get("market") == market and contract.get("kind") in ("CE", "PE"),
            "CONTRACT_MARKET_OR_KIND_UNVERIFIED")
    qty = posint(quantity, "QUANTITY")
    require(qty % lot == 0, "QUANTITY_NOT_MULTIPLE_OF_LOT")
    require(isinstance(quote, Mapping) and quote.get("broker") == "Angel"
            and quote.get("symboltoken") == token and quote.get("authenticated") is True,
            "AUTHENTICATED_BROKER_QUOTE_MISSING")
    ask, bid = money(quote.get("ask"), "ASK"), money(quote.get("bid"), "BID")
    price = money(limit_price, "ENTRY_LIMIT_PRICE")
    tick_aligned(price, tick, "ENTRY")
    require(bid > 0 and ask >= bid and price >= bid, "INVALID_QUOTE_OR_ENTRY")
    require(price <= ask * Decimal("1.02"), "ENTRY_PRICE_ABOVE_2_PERCENT_ASK_BUFFER")
    # A verified entry must have a protective-exit plan BEFORE an order is
    # considered. Estimated downside is a risk bound, not a guaranteed SL fill.
    require(owner_snapshot.get("broker_native_stop_supported") is True,
            "NATIVE_STOP_CAPABILITY_UNVERIFIED")
    stop = money(owner_snapshot.get("planned_stop_trigger"), "PLANNED_STOP_TRIGGER")
    tick_aligned(stop, tick, "PLANNED_STOP")
    require(0 < stop < price, "INVALID_PLANNED_STOP")
    estimated_cost = money(owner_snapshot.get("estimated_fees_and_gap_reserve"), "COST_RESERVE")
    approved_risk = money(owner_snapshot.get("approved_max_trade_risk"), "MAX_TRADE_RISK")
    require(estimated_cost >= 0 and approved_risk > 0
            and (price-stop)*qty + estimated_cost <= approved_risk,
            "RISK_EXCEEDS_OWNER_BUDGET")
    budget = money(owner_snapshot.get("approved_max_notional"), "MAX_NOTIONAL")
    require(budget > 0 and price * qty <= budget, "NOTIONAL_EXCEEDS_OWNER_BUDGET")
    payload = {
        "variety": "NORMAL", "tradingsymbol": symbol, "symboltoken": token,
        "transactiontype": "BUY", "exchange": "NFO", "ordertype": "LIMIT",
        "producttype": producttype, "duration": "DAY",
        "price": str(price), "quantity": str(qty),
    }
    return {"stage": "DATA_ONLY_ORDER_CONTRACT", "canSubmitOrder": False,
            "liveExecutionEnabled": False, "payload": payload,
            "requiredNext": "BROKER_SUBMISSION_AND_ACK_UNIMPLEMENTED"}


def protective_stop(*, contract: Mapping[str, Any],
                    confirmed_fill: Mapping[str, Any],
                    broker_state: Mapping[str, Any],
                    trigger_price: str, limit_price: str,
                    now: datetime, producttype: str = "INTRADAY") -> dict[str, Any]:
    """Build SELL STOPLOSS_LIMIT for a verified filled LONG position only."""
    require(producttype in PRODUCTS, "UNSUPPORTED_PRODUCT")
    symbol, token, lot, tick = standard_contract(contract)
    require(isinstance(confirmed_fill, Mapping), "CONFIRMED_FILL_MISSING")
    require(confirmed_fill.get("authenticated") is True
            and confirmed_fill.get("broker") == "Angel"
            and confirmed_fill.get("side") == "BUY"
            and confirmed_fill.get("symboltoken") == token, "BROKER_FILL_NOT_VERIFIED")
    qty = posint(confirmed_fill.get("net_open_quantity"), "OPEN_QUANTITY")
    filled_qty = posint(confirmed_fill.get("filled_quantity"), "FILLED_QUANTITY")
    require(qty == filled_qty and qty % lot == 0, "PARTIAL_OR_MISMATCHED_FILL")
    require(isinstance(confirmed_fill.get("order_id"), str)
            and len(confirmed_fill["order_id"]) >= 4, "BROKER_FILL_ORDER_ID_MISSING")
    fill_at = confirmed_fill.get("verified_at")
    require(isinstance(now, datetime) and now.utcoffset() is not None
            and isinstance(fill_at, datetime) and fill_at.utcoffset() is not None
            and timedelta(0) <= now - fill_at <= MAX_QUOTE_AGE,
            "BROKER_FILL_STALE")
    require(isinstance(broker_state, Mapping)
            and broker_state.get("owner_account_verified") is True
            and broker_state.get("orderbook_reconciled") is True
            and broker_state.get("existing_exit_orders") is False
            and broker_state.get("emergency_stop") is False
            and broker_state.get("stoploss_limit_supported_for_contract") is True,
            "PROTECTIVE_EXIT_BROKER_STATE_UNVERIFIED")
    entry = money(confirmed_fill.get("average_price"), "FILL_PRICE")
    trigger = money(trigger_price, "STOP_TRIGGER")
    price = money(limit_price, "STOP_LIMIT_PRICE")
    tick_aligned(trigger, tick, "STOP_TRIGGER")
    tick_aligned(price, tick, "STOP_LIMIT")
    require(0 < price <= trigger < entry, "INVALID_SELL_STOP_LIMIT_STRUCTURE")
    require(trigger - price <= trigger * Decimal("0.02"), "STOP_LIMIT_SPREAD_TOO_WIDE")
    payload = {
        "variety": "STOPLOSS", "tradingsymbol": symbol, "symboltoken": token,
        "transactiontype": "SELL", "exchange": "NFO",
        "ordertype": "STOPLOSS_LIMIT", "producttype": producttype,
        "duration": "DAY", "triggerprice": str(trigger),
        "price": str(price), "quantity": str(qty),
    }
    return {"stage": "DATA_ONLY_STOP_CONTRACT", "canSubmitOrder": False,
            "liveExecutionEnabled": False, "payload": payload,
            "requiredNext": "BROKER_NATIVE_STOP_ACK_AND_RECONCILIATION_UNIMPLEMENTED",
            "warning": "A stop-limit can remain unfilled after a gap; no guaranteed exit."}
