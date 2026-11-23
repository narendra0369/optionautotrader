"""OptionX V7 contract verification models — DEV DRAFT, NOT EXECUTION APPROVAL.

Accept ONLY server-authenticated instrument-master records and quotes. The
caller MUST establish authenticated provenance; this code cannot prove it.
No network requests, credentials or broker order methods exist here.

Important: NIFTY/BANKNIFTY *index* candles cannot be treated as tradable CE/PE
contracts. Delta futures, options, contract multipliers and inverse settlement
need broker-specific verification; this module does not infer them.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from decimal import Decimal, InvalidOperation
from typing import Mapping, Any

MAX_MASTER_AGE = timedelta(hours=24)
MAX_QUOTE_AGE = timedelta(seconds=10)
ALLOWED = {
    "Angel": {"NIFTY": {"CE", "PE", "FUT"}, "BANKNIFTY": {"CE", "PE", "FUT"}},
    "Delta": {"BTC": {"CALL", "PUT", "FUT", "PERPETUAL"}},
}
CURRENCIES = {"Angel": {"INR"}, "Delta": {"USD", "INR"}}


class ContractVerificationError(ValueError):
    pass


def _decimal(x: Any, label: str) -> Decimal:
    if isinstance(x, bool) or not isinstance(x, (str, int, Decimal)):
        raise ContractVerificationError(label + " requires exact decimal text")
    try:
        value = Decimal(x)
    except (InvalidOperation, ValueError, TypeError):
        raise ContractVerificationError(label + " is invalid") from None
    if not value.is_finite():
        raise ContractVerificationError(label + " is not finite")
    return value


def _stamp(x: Any, label: str) -> datetime:
    if not isinstance(x, datetime) or x.utcoffset() is None:
        raise ContractVerificationError(label + " must be a timezone-aware datetime")
    return x


def _strict_int(x: Any, label: str) -> int:
    if isinstance(x, bool) or not isinstance(x, int):
        raise ContractVerificationError(label + " must be an integer")
    return x


@dataclass(frozen=True)
class Contract:
    broker: str
    market: str
    kind: str
    exchange: str
    token: str
    symbol: str
    lot_size: int
    tick_size: Decimal
    multiplier: Decimal
    currency: str
    expires_at: datetime
    master_verified_at: datetime
    broker_source_verified: bool
    currently_tradable: bool
    trading_status_verified_at: datetime


@dataclass(frozen=True)
class Quote:
    contract_token: str
    broker: str
    bid: Decimal
    ask: Decimal
    as_of: datetime
    source_authenticated: bool


def contract_from_verified_master(raw: Mapping[str, Any], *, now: datetime) -> Contract:
    """Fail closed on missing, stale, expired, synthetic or invented tokens.

    This only validates a caller's claims. Trust comes from an authenticated
    broker transport and independently verified owner account binding.
    """
    _stamp(now, "now")
    if not isinstance(raw, Mapping):
        raise ContractVerificationError("Master record missing")
    broker = raw.get("broker")
    market = raw.get("market")
    kind = raw.get("kind")
    if broker not in ALLOWED or market not in ALLOWED[broker] or kind not in ALLOWED[broker][market]:
        raise ContractVerificationError("Unsupported market/contract mapping")
    if raw.get("broker_source_verified") is not True or raw.get("currently_tradable") is not True:
        raise ContractVerificationError("Trusted broker master/tradability is required")
    token, symbol = raw.get("token"), raw.get("symbol")
    if not isinstance(token, str) or not 1 <= len(token) <= 64 or any(c.isspace() for c in token):
        raise ContractVerificationError("Invalid broker token/product id")
    if not isinstance(symbol, str) or not 4 <= len(symbol) <= 72 or any(ord(c) < 33 or ord(c) > 126 for c in symbol):
        raise ContractVerificationError("Invalid contract label")
    exchange = raw.get("exchange")
    if exchange != ("NFO" if broker == "Angel" else "DELTA_INDIA"):
        raise ContractVerificationError("Wrong exchange")
    currency = raw.get("currency")
    if currency not in CURRENCIES[broker]:
        raise ContractVerificationError("Unknown contract settlement currency")
    lot = _strict_int(raw.get("lot_size"), "lot size")
    tick = _decimal(raw.get("tick_size"), "tick size")
    multiplier = _decimal(raw.get("multiplier"), "contract multiplier")
    if not (1 <= lot <= 100000 and Decimal("0") < tick <= Decimal("1000000") and multiplier > 0):
        raise ContractVerificationError("Invalid lot/tick/multiplier")
    expiry_raw = raw.get("expires_at")
    if broker == "Delta" and kind == "PERPETUAL":
        # Perpetual futures usually do not have an expiry. The instrument
        # master must explicitly say this is a verified perpetual contract.
        if raw.get("perpetual_confirmed_by_broker") is not True or expiry_raw is not None:
            raise ContractVerificationError("Perpetual status not verified")
        expiry = datetime.max.replace(tzinfo=now.tzinfo)
    else:
        expiry = _stamp(expiry_raw, "expiry")
    master_at = _stamp(raw.get("master_verified_at"), "master timestamp")
    tradable_at = _stamp(raw.get("trading_status_verified_at"), "trading timestamp")
    if expiry <= now:
        raise ContractVerificationError("Expired contract")
    if not timedelta(0) <= now - master_at <= MAX_MASTER_AGE:
        raise ContractVerificationError("Stale instrument master")
    if not timedelta(0) <= now - tradable_at <= MAX_QUOTE_AGE:
        raise ContractVerificationError("Stale trading status")
    if broker == "Angel" and kind in ("CE", "PE") and market not in symbol.upper():
        raise ContractVerificationError("Option symbol not mapped to expected index")
    return Contract(broker, market, kind, exchange, token, symbol, lot, tick,
                    multiplier, currency, expiry, master_at, True, True, tradable_at)


def quote_from_verified_broker(raw: Mapping[str, Any], contract: Contract, *, now: datetime) -> Quote:
    """Require exact token-specific bid/ask and authenticated quote source."""
    _stamp(now, "now")
    if not isinstance(raw, Mapping) or raw.get("source_authenticated") is not True:
        raise ContractVerificationError("Authenticated quote missing")
    if raw.get("token") != contract.token or raw.get("broker") != contract.broker:
        raise ContractVerificationError("Broker quote/contract mismatch")
    bid = _decimal(raw.get("bid"), "bid")
    ask = _decimal(raw.get("ask"), "ask")
    as_of = _stamp(raw.get("as_of"), "quote timestamp")
    if not timedelta(0) <= now - as_of <= MAX_QUOTE_AGE:
        raise ContractVerificationError("Quote stale or from future")
    if bid <= 0 or ask < bid or any(x % contract.tick_size for x in (bid, ask)):
        raise ContractVerificationError("Invalid bid/ask or tick rounding")
    return Quote(contract.token, contract.broker, bid, ask, as_of, True)


def quote_health(quote: Quote, *, max_spread_fraction: str = "0.02") -> dict[str, object]:
    spread_limit = _decimal(max_spread_fraction, "spread limit")
    spread = (quote.ask - quote.bid) / quote.ask
    ok = spread_limit > 0 and spread <= spread_limit
    return {
        "quoteValidForResearch": ok,
        "spreadFraction": str(spread),
        "maxSpreadFraction": str(spread_limit),
        "liveExecutionEnabled": False,
        "canSubmitOrder": False,
    }
