"""V31 pure broker/risk evidence audit for manual LIMIT exit.

No broker imports, network, credentials, execution transport, or order writes.
All evidence must be externally verified; caller-provided flags are not proof.
This is a checklist calculator, not authority to submit a trade.
"""
from __future__ import annotations
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from typing import Mapping

CONTRACT = "NIFTY29DEC2629000CE"
TOKEN = "38158"
QUANTITY = 65
LIMIT = Decimal("10.50")
OWNER_DECLARED_ENTRY = Decimal("12.92")
OWNER_DECLARED_BUDGET = Decimal("800")
MAX_QUOTE_AGE_SECONDS = 10


def _money(value):
    if isinstance(value, bool):
        return None
    try:
        d = Decimal(str(value))
    except (TypeError, ValueError, InvalidOperation):
        return None
    return d if d.is_finite() and d >= 0 else None


def audit_manual_limit_exit(evidence: Mapping, *, now: datetime | None = None) -> dict:
    """Return explicitly non-executable evidence assessment.

    Evidence must come from trusted private AWS checks, not a browser or LTP
    receipt alone. Missing values fail closed, never filled by assumptions.
    """
    blockers = []
    if not isinstance(evidence, Mapping):
        evidence = {}
        blockers.append("EVIDENCE_MISSING")
    now = now or datetime.now(timezone.utc)
    if not isinstance(now, datetime) or now.utcoffset() is None:
        raise ValueError("AWARE_UTC_NOW_REQUIRED")

    if evidence.get("owner_verified") is not True:
        blockers.append("OWNER_NOT_VERIFIED")
    if evidence.get("contract") != CONTRACT or str(evidence.get("token")) != TOKEN:
        blockers.append("CONTRACT_TOKEN_MISMATCH")
    if type(evidence.get("net_quantity")) is not int or evidence["net_quantity"] != QUANTITY:
        blockers.append("POSITION_NOT_EXACT")
    if type(evidence.get("active_sell_quantity")) is not int or evidence["active_sell_quantity"] != 0:
        blockers.append("ACTIVE_SELL_CONFLICT_OR_UNKNOWN")
    if evidence.get("orderbook_states_reconciled") is not True:
        blockers.append("ORDERBOOK_UNRECONCILED")

    ltp, bid, ask = (_money(evidence.get(k)) for k in ("ltp", "best_bid", "best_ask"))
    if ltp is None or ltp == 0:
        blockers.append("LTP_INVALID")
    if bid is None or bid == 0 or ask is None or ask == 0 or bid > ask:
        blockers.append("LIVE_BID_ASK_UNVERIFIED_OR_INVALID")
    # A SELL LIMIT may rest unfilled if the executable bid is below its limit.
    elif bid < LIMIT:
        blockers.append("BID_BELOW_SELL_LIMIT_NO_IMMEDIATE_FILL_ASSUMPTION")

    feed_time = evidence.get("broker_feed_timestamp_utc")
    if not isinstance(feed_time, datetime) or feed_time.utcoffset() is None:
        blockers.append("EXCHANGE_FEED_TIMESTAMP_NOT_VERIFIED")
    else:
        age = (now.astimezone(timezone.utc) - feed_time.astimezone(timezone.utc)).total_seconds()
        if not 0 <= age <= MAX_QUOTE_AGE_SECONDS:
            blockers.append("EXCHANGE_FEED_STALE_OR_FUTURE")
    if evidence.get("feed_timestamp_independently_verified") is not True:
        blockers.append("FEED_SOURCE_NOT_VERIFIED")

    tick = _money(evidence.get("official_tick_size"))
    if tick is None or tick <= 0 or evidence.get("official_tick_verified") is not True:
        blockers.append("OFFICIAL_TICK_NOT_VERIFIED")
    elif LIMIT % tick != 0:
        blockers.append("SELL_LIMIT_OFF_TICK")

    lower = _money(evidence.get("lpp_lower"))
    upper = _money(evidence.get("lpp_upper"))
    if (lower is None or upper is None or lower > upper
            or evidence.get("lpp_verified") is not True):
        blockers.append("BROKER_EXCHANGE_LPP_UNVERIFIED")
    elif not lower <= LIMIT <= upper:
        blockers.append("SELL_LIMIT_OUTSIDE_LPP")

    for field, message in (
        ("nfo_sell_limit_entitlement_verified", "SELL_LIMIT_ENTITLEMENT_UNVERIFIED"),
        ("order_fields_verified", "ORDER_FIELDS_UNVERIFIED"),
        ("product_type_verified", "PRODUCT_TYPE_UNVERIFIED"),
        ("market_session_verified", "MARKET_SESSION_UNVERIFIED"),
        ("durable_order_journal_certified", "DURABLE_JOURNAL_UNCERTIFIED"),
        ("restart_and_unknown_ack_recovery_certified", "RECOVERY_UNCERTIFIED"),
        ("final_order_specific_user_authorization", "FINAL_ORDER_AUTHORIZATION_MISSING"),
    ):
        if evidence.get(field) is not True:
            blockers.append(message)

    fees = _money(evidence.get("total_exit_and_entry_fees"))
    if fees is None or evidence.get("fees_broker_verified") is not True:
        blockers.append("ACTUAL_CHARGES_UNVERIFIED")

    premium_loss_at_limit = (OWNER_DECLARED_ENTRY - LIMIT) * QUANTITY
    estimated_loss = premium_loss_at_limit + fees if fees is not None else None
    if estimated_loss is None:
        blockers.append("ALL_IN_RISK_UNKNOWN")
    elif estimated_loss > OWNER_DECLARED_BUDGET:
        blockers.append("OWNER_DECLARED_BUDGET_EXCEEDED")
    if evidence.get("actual_average_entry_broker_verified") is not True:
        blockers.append("COST_BASIS_OWNER_DECLARED_ONLY")

    return {
        "contract": CONTRACT, "token": TOKEN, "quantity": QUANTITY,
        "side": "SELL", "orderType": "LIMIT", "limit": str(LIMIT),
        "premiumLossAtLimitExCharges": str(premium_loss_at_limit),
        "estimatedLossIncludingProvidedFees": str(estimated_loss) if estimated_loss is not None else None,
        "ownerDeclaredBudget": str(OWNER_DECLARED_BUDGET),
        "stopLossOrder": False,
        "limitOrderMayRemainUnfilled": True,
        "lossIsGuaranteedCapped": False,
        "evidenceBlockers": sorted(set(blockers)),
        "allEvidenceChecksPassed": not blockers,
        # Deliberate V31 source lock. Never wire this into live transport.
        "canSubmitOrder": False, "submittedOrder": False,
        "realOrdersEnabled": False, "status": "READ_ONLY_RISK_AUDIT",
    }
