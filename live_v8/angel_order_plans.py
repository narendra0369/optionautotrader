"""Angel One SmartAPI NFO order payload builder — STRICT OFFLINE / NO SEND.

Docs: https://smartapi.angelone.in/docs/Orders
No SDK, HTTP requests, token reading or account connection. These payloads
must be checked against broker/exchange contract specs before any future use.
No Market, IOC, ROBO or naked SELL orders. Real orders remain hard locked.
"""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from typing import Literal
import re

EXECUTION_MODE = "OFFLINE_PREVIEW_ONLY"
REAL_ORDER_METHODS_IMPLEMENTED = False


class OrderPlanError(ValueError):
    pass


def decimal(value, field):
    if isinstance(value, bool) or not isinstance(value, (str, int, Decimal)):
        raise OrderPlanError(field + ": exact decimal string required")
    try:
        n = Decimal(value)
    except (TypeError, InvalidOperation):
        raise OrderPlanError(field + ": invalid decimal") from None
    if not n.is_finite() or n <= 0:
        raise OrderPlanError(field + ": positive finite decimal required")
    return n


def price_str(price):
    return format(price, "f")


def _validate_amount(n, tick, field):
    v = decimal(n, field)
    t = decimal(tick, "tick_size")
    if v % t != 0:
        raise OrderPlanError(field + ": not aligned to tick size")
    return v


@dataclass(frozen=True)
class BrokerContract:
    symbol: str
    token: str
    lot_size: int
    tick_size: str
    segment: str = "NFO"
    contract_master_verified: bool = False
    owner_account_verified: bool = False

    def validate(self):
        if (self.segment != "NFO" or self.contract_master_verified is not True
                or self.owner_account_verified is not True):
            raise OrderPlanError("NFO contract and account must be broker-verified")
        if not isinstance(self.symbol, str) or not re.fullmatch(r"[A-Z0-9.-]{6,72}", self.symbol):
            raise OrderPlanError("Invalid NFO tradingsymbol")
        if not isinstance(self.token, str) or not re.fullmatch(r"\d{2,16}", self.token):
            raise OrderPlanError("Invalid broker symboltoken")
        if isinstance(self.lot_size, bool) or not isinstance(self.lot_size, int) or self.lot_size <= 0:
            raise OrderPlanError("Unverified contract lot_size")
        decimal(self.tick_size, "tick_size")


@dataclass(frozen=True)
class OfflineOrderPlan:
    role: Literal["ENTRY_BUY", "PROTECTIVE_STOP_SELL", "TARGET_EXIT_SELL"]
    intent_id: str
    payload: dict
    mode: str = EXECUTION_MODE

    @property
    def can_submit_real_order(self):
        return False


def _base(contract, qty, intent_id, side):
    if not isinstance(contract, BrokerContract):
        raise OrderPlanError("Trusted contract object required")
    contract.validate()
    if type(qty) is not int or qty <= 0 or qty > 100_000 or qty % contract.lot_size:
        raise OrderPlanError("Quantity must be a positive whole number of verified lots")
    if not isinstance(intent_id, str) or not re.fullmatch(r"[A-Za-z0-9_-]{8,32}", intent_id):
        raise OrderPlanError("Opaque idempotency intent required")
    if side not in ("BUY", "SELL"):
        raise OrderPlanError("Invalid side")
    return {
        "tradingsymbol": contract.symbol, "symboltoken": contract.token,
        "transactiontype": side, "exchange": "NFO",
        "producttype": "INTRADAY", "duration": "DAY",
        "quantity": str(qty),
        # Deliberately omit ordertag: exchange-side dedup is NOT guaranteed.
    }


def preview_entry(*, contract, qty, limit_price, intent_id):
    """Plan an entry BUY LIMIT. Not evidence of margin, quote or broker support."""
    fields = _base(contract, qty, intent_id, "BUY")
    fields.update({"variety": "NORMAL", "ordertype": "LIMIT",
                   "price": price_str(_validate_amount(limit_price, contract.tick_size, "limit_price"))})
    return OfflineOrderPlan("ENTRY_BUY", intent_id, fields)


def preview_protective_stop(*, contract, filled_open_qty, trigger_price, limit_price,
                            intent_id, fill_verified, position_verified, exit_rules_verified):
    """Plan broker SL-LIMIT for already filled & reconciled LONG NFO position.

    No implicit broker-native OCO. An accepted stop LIMIT may still not fill.
    """
    if (fill_verified is not True or position_verified is not True
            or exit_rules_verified is not True):
        raise OrderPlanError("Fill, open position and exchange-specific exit rules unverified")
    fields = _base(contract, filled_open_qty, intent_id, "SELL")
    trigger = _validate_amount(trigger_price, contract.tick_size, "stop_trigger")
    limit = _validate_amount(limit_price, contract.tick_size, "stop_limit")
    if not 0 < limit <= trigger:
        raise OrderPlanError("For SELL STOPLOSS_LIMIT, limit must not exceed trigger")
    fields.update({"variety": "STOPLOSS", "ordertype": "STOPLOSS_LIMIT",
                   "triggerprice": price_str(trigger), "price": price_str(limit)})
    return OfflineOrderPlan("PROTECTIVE_STOP_SELL", intent_id, fields)


def preview_target_exit(*, contract, net_open_qty, limit_price, intent_id,
                        stop_cancel_confirmed, fresh_position_verified, no_other_sell_orders):
    """Target SELL may be planned only after stop CANCEL and fresh position read.

    This is a manual/controlled EXIT rehearsal, not broker-side atomic OCO.
    It does not claim the limit price or exit can execute.
    """
    if (stop_cancel_confirmed is not True or fresh_position_verified is not True
            or no_other_sell_orders is not True):
        raise OrderPlanError("Target exit blocked: stop cancel or fresh position unverified")
    fields = _base(contract, net_open_qty, intent_id, "SELL")
    fields.update({"variety": "NORMAL", "ordertype": "LIMIT",
                   "price": price_str(_validate_amount(limit_price, contract.tick_size, "limit_price"))})
    return OfflineOrderPlan("TARGET_EXIT_SELL", intent_id, fields)


def send_real_order(*args, **kwargs):
    """Hard lock cannot be unlocked using flags, session or a preview."""
    raise PermissionError("REAL_ORDERS_HARD_LOCKED: adapter is offline-only")
