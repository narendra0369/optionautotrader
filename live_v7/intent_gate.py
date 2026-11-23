"""OptionX V7: PURE, NON-EXECUTING order-intent safety gate.

Development stage only. This file does not import a broker SDK, create an
HTTP client, call any broker, or enable actual order execution. All context
must come from separately authenticated/verified backend services, NOT
browser-submitted booleans. Do not expose this module as an order endpoint.

This is a preflight sketch; it has NOT passed integration or recovery tests.
"""
from __future__ import annotations

from datetime import datetime, timedelta, time
from decimal import Decimal, InvalidOperation
from typing import Any, Mapping
from zoneinfo import ZoneInfo

IST = ZoneInfo("Asia/Kolkata")
MAX_QUOTE_AGE = timedelta(seconds=10)
MAX_CONTRACT_AGE = timedelta(hours=24)
ENTRY_CUTOFF = time(14, 45)
SESSION_START = time(9, 15)
SESSION_END = time(15, 30)
MAX_TRADES_PER_DAY_HARD = 2

MARKET_BROKERS = {
    "NIFTY": ("Angel", "NFO"),
    "BANKNIFTY": ("Angel", "NFO"),
    "BTC": ("Delta", "DERIVATIVES"),
}
ALLOWED_INTENT_KEYS = {
    "intent_id", "market", "broker", "action", "symbol", "quantity",
    "entry_price", "stop_price", "target_price", "estimated_cost",
    "slippage_reserve", "strategy_id",
}


def dec(value: Any, label: str) -> Decimal:
    """Reject floats and other ambiguous representations in financial math."""
    if isinstance(value, bool) or not isinstance(value, (str, int, Decimal)):
        raise ValueError(label + " must be a decimal string or integer")
    try:
        result = Decimal(value)
    except (InvalidOperation, TypeError):
        raise ValueError(label + " is invalid") from None
    if not result.is_finite():
        raise ValueError(label + " must be finite")
    return result


def int_strict(value: Any, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(label + " must be an integer")
    return value


def aware(value: Any, label: str) -> datetime:
    if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(label + " needs an aware datetime")
    return value


def _result(reasons: list[str], calculated: dict[str, str]) -> dict[str, Any]:
    """Never return a can-send/execute flag, even when checks pass."""
    return {
        "mode": "OFFLINE_PREFLIGHT_ONLY",
        "liveExecutionEnabled": False,
        "canSubmitOrder": False,
        "readyForLaterIntegrationTests": not reasons,
        "blockedReasons": sorted(set(reasons)) or ["NO_EXECUTION_IMPLEMENTATION"],
        "calculated": calculated,
        "notice": "This does not validate a broker quote or authorize any real order.",
    }


def evaluate(
    intent: Mapping[str, Any],
    trusted: Mapping[str, Any],
    *,
    now: datetime | None = None,
) -> dict[str, Any]:
    """Validate one prospective LONG option/futures trade; never submit it.

    trusted must eventually be assembled from server-verified account/session,
    contract master, positions, exchange calendar, broker quotes and ledger.
    A client-controlled dict is NOT an acceptable trusted source.
    """
    reasons: list[str] = []
    calc: dict[str, str] = {}
    if now is None:
        now = datetime.now(IST)
    aware(now, "now")
    local = now.astimezone(IST)

    if not isinstance(intent, Mapping) or not isinstance(trusted, Mapping):
        return _result(["INVALID_INPUT"], calc)
    if set(intent) - ALLOWED_INTENT_KEYS:
        reasons.append("UNKNOWN_INTENT_KEYS")
    market = intent.get("market")
    broker = intent.get("broker")
    expected = MARKET_BROKERS.get(market)
    if not expected or broker != expected[0]:
        reasons.append("MARKET_BROKER_MISMATCH")

    if intent.get("action") != "ENTRY_BUY":
        # EXIT_SELL needs independently verified holdings and a dedicated
        # emergency-exit lifecycle; refusing it here prevents short selling.
        reasons.append("ENTRY_BUY_ONLY_AT_THIS_STAGE")

    ident = intent.get("intent_id")
    if not isinstance(ident, str) or not (8 <= len(ident) <= 96) or not ident.isascii() or not all(
        c.isalnum() or c in "-_" for c in ident
    ):
        reasons.append("INVALID_INTENT_ID")

    symbol = intent.get("symbol")
    if not isinstance(symbol, str) or not (4 <= len(symbol) <= 72) or not symbol.isascii() or not all(
        c.isupper() or c.isdigit() or c in "-_." for c in symbol
    ):
        reasons.append("INVALID_CONTRACT_LABEL")

    try:
        qty = int_strict(intent.get("quantity"), "quantity")
        if qty <= 0:
            reasons.append("INVALID_QUANTITY")
    except ValueError:
        qty = 0
        reasons.append("INVALID_QUANTITY")

    amounts = {}
    for name in ("entry_price", "stop_price", "target_price", "estimated_cost", "slippage_reserve"):
        try:
            amounts[name] = dec(intent.get(name), name)
        except ValueError:
            reasons.append("INVALID_" + name.upper())
            amounts[name] = Decimal("0")
    entry = amounts["entry_price"]
    stop = amounts["stop_price"]
    target = amounts["target_price"]
    costs = amounts["estimated_cost"]
    slippage = amounts["slippage_reserve"]
    if not (entry > 0 and stop > 0 and target > 0 and stop < entry < target):
        reasons.append("INVALID_LONG_TRADE_PRICES")
    if costs < 0 or slippage < 0:
        reasons.append("INVALID_COST_RESERVE")

    try:
        strategy_id = int_strict(intent.get("strategy_id"), "strategy_id")
        if not (1 <= strategy_id <= 200000):
            reasons.append("INVALID_STRATEGY_ID")
    except ValueError:
        reasons.append("INVALID_STRATEGY_ID")

    # Broker and exchange eligibility are externally verifiable prerequisites.
    for key in (
        "authenticated_owner", "broker_account_matches_owner", "broker_session_current",
        "broker_api_permission_confirmed", "registered_static_ip_confirmed",
        "exchange_or_algo_requirements_confirmed", "kill_switch_healthy",
        "broker_orderbook_reconciled", "no_pending_or_unknown_orders",
        "no_open_position_in_market", "strategy_approved_by_owner",
        "market_data_is_exchange_grade", "broker_quote_authenticated",
        "contract_master_verified", "margin_verified",
    ):
        if trusted.get(key) is not True:
            reasons.append("MISSING_" + key.upper())

    if trusted.get("emergency_stop") is not False:
        reasons.append("EMERGENCY_STOP_ACTIVE_OR_UNKNOWN")

    if trusted.get("intent_id_already_seen") is not False:
        reasons.append("DUPLICATE_OR_UNKNOWN_INTENT")

    if expected:
        contract = trusted.get("contract")
        if not isinstance(contract, Mapping):
            reasons.append("CONTRACT_UNVERIFIED")
        else:
            if contract.get("broker") != broker or contract.get("exchange") != expected[1]:
                reasons.append("CONTRACT_EXCHANGE_MISMATCH")
            if contract.get("symbol") != symbol:
                reasons.append("CONTRACT_SYMBOL_MISMATCH")
            token = contract.get("token")
            if not isinstance(token, str) or not token:
                reasons.append("CONTRACT_TOKEN_MISSING")
            try:
                lot = int_strict(contract.get("lot_size"), "lot_size")
                tick = dec(contract.get("tick_size"), "tick_size")
                if lot < 1 or qty < lot or qty % lot != 0:
                    reasons.append("QUANTITY_NOT_FULL_LOTS")
                if tick <= 0 or any(p % tick != 0 for p in (entry, stop, target)):
                    reasons.append("INVALID_TICK_ROUNDING")
            except ValueError:
                reasons.append("INVALID_CONTRACT_LOT_OR_TICK")
            try:
                at = aware(contract.get("verified_at"), "contract verified_at")
                if not timedelta(0) <= now - at <= MAX_CONTRACT_AGE:
                    reasons.append("STALE_CONTRACT_MASTER")
                expiry = aware(contract.get("expiry"), "contract expiry")
                if expiry <= now:
                    reasons.append("EXPIRED_CONTRACT")
            except ValueError:
                reasons.append("CONTRACT_TIMESTAMPS_NOT_VERIFIED")

    # Server-verified execution quote should be neither stale nor inconsistent
    # with the intended entry price. Actual tradeable bid/ask needs validation.
    quote = trusted.get("quote")
    if not isinstance(quote, Mapping):
        reasons.append("QUOTE_MISSING")
    else:
        try:
            quoted_at = aware(quote.get("as_of"), "quote as_of")
            if not timedelta(0) <= now - quoted_at <= MAX_QUOTE_AGE:
                reasons.append("QUOTE_STALE_OR_FUTURE")
            ask = dec(quote.get("ask"), "ask")
            bid = dec(quote.get("bid"), "bid")
            max_spread_pct = dec(trusted.get("max_spread_pct", "0.02"), "max_spread_pct")
            if bid <= 0 or ask <= 0 or bid > ask or max_spread_pct <= 0:
                reasons.append("QUOTE_INVALID")
            elif (ask - bid) / ask > max_spread_pct:
                reasons.append("SPREAD_TOO_WIDE")
            if ask > entry:
                reasons.append("INTENDED_LIMIT_BELOW_ASK")
        except ValueError:
            reasons.append("QUOTE_INVALID")

    if market in ("NIFTY", "BANKNIFTY"):
        if local.weekday() >= 5 or not (SESSION_START <= local.time() < ENTRY_CUTOFF):
            reasons.append("ENTRY_OUTSIDE_EXCHANGE_WINDOW")
        if trusted.get("exchange_session_verified_for_today") is not True:
            reasons.append("EXCHANGE_CALENDAR_NOT_VERIFIED")
    elif market == "BTC":
        if trusted.get("btc_contract_currently_tradable") is not True:
            reasons.append("BTC_TRADING_STATUS_UNVERIFIED")

    try:
        risk_budget = dec(trusted.get("risk_budget"), "risk_budget")
        daily_loss_limit = dec(trusted.get("daily_loss_limit"), "daily_loss_limit")
        today_pnl = dec(trusted.get("today_realized_pnl"), "today_realized_pnl")
        available_margin = dec(trusted.get("available_margin"), "available_margin")
        required_margin = dec(trusted.get("required_margin"), "required_margin")
        today_trade_count = int_strict(trusted.get("today_trade_count"), "today_trade_count")
        max_trades = int_strict(trusted.get("max_trades_per_day"), "max_trades_per_day")
        if risk_budget <= 0 or daily_loss_limit <= 0:
            reasons.append("INVALID_RISK_BUDGET")
        if not (1 <= max_trades <= MAX_TRADES_PER_DAY_HARD):
            reasons.append("EXCEEDS_HARD_TRADE_CAP")
        if today_trade_count < 0 or today_trade_count >= max_trades:
            reasons.append("DAILY_TRADE_CAP_REACHED")
        if today_pnl <= -daily_loss_limit:
            reasons.append("DAILY_STOP_ALREADY_BREACHED")
        if required_margin <= 0 or available_margin < required_margin:
            reasons.append("INSUFFICIENT_OR_UNKNOWN_MARGIN")
        if entry > stop and qty and costs >= 0 and slippage >= 0:
            loss_if_stopped = (entry - stop) * qty + costs + slippage
            calc["lossIfStoppedEstimate"] = str(loss_if_stopped)
            calc["rewardBeforeCosts"] = str((target - entry) * qty)
            if loss_if_stopped > risk_budget:
                reasons.append("TRADE_RISK_CAP_EXCEEDED")
            if today_pnl - loss_if_stopped < -daily_loss_limit:
                reasons.append("DAILY_LOSS_CAP_WOULD_BE_BREACHED")
        else:
            reasons.append("RISK_NOT_COMPUTABLE")
    except ValueError:
        reasons.append("INCOMPLETE_VERIFIED_RISK_SNAPSHOT")

    # This module deliberately never yields permission to transmit an order.
    return _result(reasons, calc)
