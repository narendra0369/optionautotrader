"""V42 independent exact-order readiness review, no execution capability.

This is an offline safety contract for a separately reviewed future order
writer; no broker transport, network, DB access, or live authorization.
Do NOT interpret any returned status as permission to submit an order.
"""
from __future__ import annotations
from collections.abc import Mapping
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation

def _age_ok(stamp, now, limit=10):
    if not isinstance(stamp, datetime) or not isinstance(now, datetime):
        return False
    if stamp.utcoffset() is None or now.utcoffset() is None:
        return False
    age=(now.astimezone(timezone.utc)-stamp.astimezone(timezone.utc)).total_seconds()
    return 0 <= age <= limit

def _dec(v):
    if isinstance(v,bool) or not isinstance(v,(str,int,Decimal)):
        return None
    try:
        d=Decimal(str(v))
        return d if d.is_finite() and d>0 else None
    except (ValueError,TypeError,InvalidOperation):
        return None

def evaluate_exact_order(*, order, evidence, now):
    """Fail-closed documented assessment; NEVER permit an order.

    Input fields are provided by caller and cannot prove original broker
    authenticity; future production design needs signed durable provenance.
    """
    reasons={"LIVE_ORDER_TRANSPORT_SOURCE_LOCKED",
             "PRODUCTION_BROKER_JOURNAL_NOT_CERTIFIED",
             "CALLER_EVIDENCE_NOT_INDEPENDENTLY_AUTHENTICATED"}
    if not isinstance(order,Mapping):
        order={}
    if not isinstance(evidence,Mapping):
        evidence={}
    if not isinstance(now,datetime) or now.utcoffset() is None:
        reasons.add("AWARE_CURRENT_TIME_REQUIRED")
    if order.get("exchange")!="NFO" or order.get("side")!="SELL":
        reasons.add("NFO_SELL_ONLY")
    if order.get("type") not in ("LIMIT","STOPLOSS_LIMIT"):
        reasons.add("UNSUPPORTED_EXIT_TYPE")
    if order.get("duration")!="DAY":
        reasons.add("DAY_ONLY")
    if order.get("variety")!=("STOPLOSS" if order.get("type")=="STOPLOSS_LIMIT" else "NORMAL"):
        reasons.add("VARIETY_ORDER_TYPE_MISMATCH")
    if not isinstance(order.get("symbol"),str) or not order["symbol"].startswith("NIFTY"):
        reasons.add("SYMBOL_NOT_VERIFIED")
    if not isinstance(order.get("token"),str) or not order["token"].isdigit():
        reasons.add("INSTRUMENT_TOKEN_INVALID")
    if type(order.get("quantity")) is not int or order["quantity"]<=0:
        reasons.add("QUANTITY_INVALID")
    limit=_dec(order.get("price"))
    tick=_dec(evidence.get("master_tick"))
    if limit is None or tick is None or (limit is not None and tick is not None and limit%tick):
        reasons.add("PRICE_OR_TICK_NOT_VERIFIED")
    if order.get("type")=="STOPLOSS_LIMIT":
        trigger=_dec(order.get("trigger"))
        if trigger is None or limit is None or limit>trigger:
            reasons.add("SELL_STOP_LIMIT_TRIGGER_INVALID")
    elif order.get("trigger") not in (None,""):
        reasons.add("NORMAL_LIMIT_HAS_TRIGGER")

    exact_quantity=evidence.get("net_long_quantity")
    if (type(exact_quantity) is not int or exact_quantity<=0 or
        type(order.get("quantity")) is not int or order.get("quantity")>exact_quantity):
        reasons.add("FRESH_POSITION_QUANTITY_INSUFFICIENT")
    if (evidence.get("symbol")!=order.get("symbol")
        or evidence.get("token")!=order.get("token")
        or evidence.get("producttype")!=order.get("producttype")
        or order.get("producttype") not in ("INTRADAY","CARRYFORWARD")):
        reasons.add("POSITION_IDENTITY_OR_PRODUCTTYPE_MISMATCH")
    if evidence.get("active_or_unknown_sell_count")!=0:
        reasons.add("ACTIVE_OR_UNKNOWN_SELL_ORDER")
    if evidence.get("books_complete") is not True or not _age_ok(evidence.get("books_at"),now):
        reasons.add("FRESH_ORDER_POSITION_TRADEBOOK_REQUIRED")
    if evidence.get("quote_complete") is not True or not _age_ok(evidence.get("quote_at"),now):
        reasons.add("FRESH_BID_ASK_REQUIRED")
    if evidence.get("broker_technical_and_compliance_final_approval") is not True:
        reasons.add("FINAL_BROKER_AUTHORIZATION_UNVERIFIED")
    if evidence.get("account_trading_entitlement_verified") is not True:
        reasons.add("ACCOUNT_WRITE_ENTITLEMENT_UNVERIFIED")
    if evidence.get("durable_pre_send_intent_committed") is not True:
        reasons.add("DURABLE_PRE_SEND_INTENT_MISSING")
    if evidence.get("unknown_outcome_recovery_certified") is not True:
        reasons.add("UNKNOWN_BROKER_ACK_RECOVERY_MISSING")
    if evidence.get("owner_exact_order_consent") is not True:
        reasons.add("EXACT_ORDER_CONSENT_MISSING")
    if evidence.get("fee_and_risk_limit_verified") is not True:
        reasons.add("FEES_AND_RISK_NOT_VERIFIED")
    if evidence.get("lpp_and_exchange_constraints_checked") is not True:
        reasons.add("LPP_AND_EXCHANGE_CONSTRAINTS_UNVERIFIED")
    return {"blockedReasons":sorted(reasons),
            "canSubmitOrder":False,"canRetryUnknownOrder":False,
            "canReplaceAfterLpp17070":False,"manualPositionAdopted":False,
            "liveOrdersEnabled":False,"status":"REVIEW_ONLY_LOCKED"}
