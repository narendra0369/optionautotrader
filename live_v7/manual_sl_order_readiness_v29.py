"""OptionX V29: STOPLOSS_LIMIT readiness declaration, NEVER an execution route.

Pure library to validate proposed broker order fields and estimated charges.
Source/owner-bound checks from V28 remain mandatory before using this draft.
NSE LPP and broker RMS are dynamic, unavailable via V28's LTP-only feed;
this module cannot certify these or make a LIVE order.

No HTTP, broker SDK, database IO, keys, config, place/modify/cancel routes.
"""
from __future__ import annotations
from decimal import Decimal, InvalidOperation, ROUND_DOWN
from dataclasses import dataclass
from typing import Mapping

CONTRACT = "NIFTY29DEC2629000CE"
TOKEN = "38158"
QTY = 65
TICK = Decimal("0.05")
ENTRY = Decimal("12.92")
TRIGGER = Decimal("10.00")
LIMIT = Decimal("9.95")
BUDGET = Decimal("800.00")

class ReadinessBlocked(ValueError):
    pass

def exact_rupees(value, key: str) -> Decimal:
    if isinstance(value, bool) or not isinstance(value, (str, int, Decimal)):
        raise ReadinessBlocked(key + "_INVALID")
    try:
        result = Decimal(str(value))
    except (ValueError, TypeError, InvalidOperation):
        raise ReadinessBlocked(key + "_INVALID") from None
    if not result.is_finite() or result < 0:
        raise ReadinessBlocked(key + "_INVALID")
    return result

def draft_packet(*, contract: str = CONTRACT, token: str = TOKEN, quantity: int = QTY,
                 trigger: Decimal = TRIGGER, limit: Decimal = LIMIT,
                 product_type: str | None = None) -> dict:
    """Review-only field map. producttype MUST come from authenticated user
    position's verified trading-product field; no default inference."""
    if contract != CONTRACT or token != TOKEN or type(quantity) is not int or quantity != QTY:
        raise ReadinessBlocked("CONTRACT_OR_QUANTITY_MISMATCH")
    if product_type not in ("INTRADAY", "CARRYFORWARD"):
        raise ReadinessBlocked("PRODUCT_TYPE_NOT_BROKER_VERIFIED")
    t = exact_rupees(trigger, "TRIGGER")
    l = exact_rupees(limit, "LIMIT")
    if t <= 0 or l <= 0 or l >= t or t % TICK or l % TICK:
        raise ReadinessBlocked("INVALID_STOP_TICK_OR_RELATION")
    return {"variety":"STOPLOSS", "tradingsymbol":contract,
            "symboltoken":token, "transactiontype":"SELL", "exchange":"NFO",
            "ordertype":"STOPLOSS_LIMIT", "producttype":product_type,
            "duration":"DAY", "price":str(l), "triggerprice":str(t),
            "quantity":str(quantity),
            "submissionAuthorized":False,
            "canSubmitOrder":False}

def assess_risk(*, verified_avg_buy, verified_quantity, broker_ltp,
                quoted_exit_fees=None, estimated_tax=None) -> dict:
    """No unverified fee estimates. Never treats stop-limit as guaranteed exit."""
    buy=exact_rupees(verified_avg_buy, "BUY")
    price=exact_rupees(broker_ltp, "LTP")
    if buy!=ENTRY or type(verified_quantity) is not int or verified_quantity!=QTY or price<=0:
        raise ReadinessBlocked("POSITION_OR_LTP_CHANGED")
    base=(buy-LIMIT)*QTY
    ltp_pnl=(price-buy)*QTY
    fees_known=quoted_exit_fees is not None and estimated_tax is not None
    if fees_known:
        fees=exact_rupees(quoted_exit_fees,"FEES")+exact_rupees(estimated_tax,"TAX")
        at_limit=base+fees
    else:
        fees=None
        at_limit=None
    return {
      "premiumPaid":str(buy*QTY),
      "ltpSnapshot":str(price),
      "unrealizedPnlBeforeCosts":str(ltp_pnl),
      "premiumLossIfFilledExactlyAtLimit":str(base),
      "estimatedFeesAndTax":None if fees is None else str(fees),
      "estimatedLossAtLimitIncludingFees":None if at_limit is None else str(at_limit),
      "wouldExceedBudgetAtExactLimit":None if at_limit is None else at_limit>BUDGET,
      "brokerOrderWritePermissionConfirmed":False,
      "exchangeFeedTimestampVerified":False,
      "liveBidAskVerified":False,
      "exchangeLppAtTriggerVerified":False,
      "brokerStopAckVerified":False,
      "stopFillGuaranteed":False,
      "realOrdersEnabled":False, "canSubmitOrder":False,
    }

def format_preflight_report(*, product_type:str | None,
                            verified_avg_buy=ENTRY,
                            verified_quantity=QTY,
                            broker_ltp="11.25",
                            quoted_exit_fees=None, estimated_tax=None) -> str:
    risk=assess_risk(verified_avg_buy=verified_avg_buy,
        verified_quantity=verified_quantity,broker_ltp=broker_ltp,
        quoted_exit_fees=quoted_exit_fees,estimated_tax=estimated_tax)
    packet=draft_packet(product_type=product_type)
    lines=["V29_DRAFT_VALIDATION: PASS",
      "BROKER: Angel One | EXCHANGE: NFO | CONTRACT: "+CONTRACT,
      "QUANTITY: "+str(QTY)+" | TICK: "+str(TICK),
      "PRODUCT_TYPE: "+packet["producttype"],
      "ACTION: SELL | ORDER_TYPE: STOPLOSS_LIMIT | VARIETY: STOPLOSS | DURATION: DAY",
      "TRIGGER: "+packet["triggerprice"]+" | LIMIT: "+packet["price"],
      "PREMIUM_LOSS_AT_EXACT_LIMIT_EX_FEES: "+risk["premiumLossIfFilledExactlyAtLimit"],
      "CURRENT_BROKER_LTP_INPUT: "+risk["ltpSnapshot"],
      "FEES_AND_TAX_VERIFIED: "+str(risk["estimatedFeesAndTax"] is not None).upper(),
      "BROKER_ACCOUNT_WRITE_PERMISSION: UNCONFIRMED",
      "BROKER_LIVE_BID_ASK_AND_DYNAMIC_LPP: UNCONFIRMED",
      "BROKER_NATIVE_STOP_ACK: NOT_TESTED",
      "STOP_LIMIT_FILL_GUARANTEED: NO",
      "LIVE_ORDERS: OFF | NO_ORDER_SUBMITTED | SOURCE_LOCK_INTACT"]
    return "\n".join(lines)
