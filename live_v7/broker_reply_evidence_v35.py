"""V35 broker-response evidence gate, PURE offline, NEVER an order sender.

Verifies an attestation packet's required checklist fields without treating it
as independent broker certification. LPP rejection/unknown outcome NEVER retries.
No Angel imports, network, credentials, database or live transports.
"""
from __future__ import annotations
from collections.abc import Mapping
from decimal import Decimal, InvalidOperation

SYMBOL="NIFTY29DEC2629000CE"
TOKEN="38158"
LOT=65
EXIT_LIMIT=Decimal("10.50")
MAX_BUDGET=Decimal("800")

def _decimal(value):
    if isinstance(value,bool) or not isinstance(value,(str,int,Decimal)):
        return None
    try:
        d=Decimal(str(value))
        return d if d.is_finite() and d>=0 else None
    except (ValueError,TypeError,InvalidOperation):
        return None

def review_broker_reply_evidence(packet):
    """No boolean claim here establishes real broker permission."""
    if not isinstance(packet,Mapping):
        packet={}
    blockers=[]
    expected={
       "written_reply_authenticated":"BROKER_REPLY_AUTHENTICITY_UNVERIFIED",
       "account_trading_api_entitlement_confirmed":"ACCOUNT_TRADING_API_PERMISSION_UNVERIFIED",
       "fno_segment_active":"FNO_SEGMENT_UNVERIFIED",
       "registered_static_ip_confirmed":"STATIC_IP_WHITELIST_UNVERIFIED",
       "self_declaration_undertaking_confirmed":"UNDERTAKING_UNVERIFIED",
       "algo_tagging_requirements_confirmed":"ALGO_TAGGING_UNVERIFIED",
       "same_account_producttype_broker_verified":"POSITION_PRODUCTTYPE_UNVERIFIED",
       "broker_current_position_and_orders_reconciled":"BROKER_POSITION_ORDERBOOK_STALE_OR_UNVERIFIED",
       "independent_live_order_journal_certified":"PRODUCTION_JOURNAL_UNCERTIFIED",
       "unknown_order_outcome_recovery_certified":"UNKNOWN_OUTCOME_RECOVERY_UNCERTIFIED",
       "actual_fees_and_taxes_verified":"BROKER_FEES_UNVERIFIED",
       "final_exact_order_authorization":"FINAL_ORDER_AUTHORIZATION_MISSING"
    }
    for key,reason in expected.items():
        if packet.get(key) is not True:
            blockers.append(reason)
    if packet.get("contract")!=SYMBOL or str(packet.get("token"))!=TOKEN:
        blockers.append("CONTRACT_TOKEN_MISMATCH")
    if type(packet.get("net_long_quantity")) is not int or packet["net_long_quantity"]!=LOT:
        blockers.append("QUANTITY_NOT_RECONFIRMED")
    if packet.get("order_type") not in ("LIMIT","STOPLOSS_LIMIT"):
        blockers.append("ORDER_TYPE_UNVERIFIED")
    if packet.get("market_session_verified") is not True:
        blockers.append("MARKET_SESSION_UNVERIFIED")
    if packet.get("lpp_band_broker_confirmed") is not True:
        blockers.append("DYNAMIC_LPP_UNVERIFIED")
    fees=_decimal(packet.get("all_in_fees"))
    if fees is None:
        blockers.append("FEES_VALUE_UNKNOWN")
    return {
        "brokerReplyChecklistComplete":not blockers,
        "blockers":sorted(set(blockers)),
        "stopLossAndLimitAreDistinct":True,
        "lppError17070RequiresFreshReconciliation":True,
        "automaticResubmitOn17070":False,
        "automaticRetryOnUnknownOutcome":False,
        "brokerPermissionIndependentlyProvenByThisModule":False,
        "manualPositionAutoAdopted":False,
        "canSubmitOrder":False,
        "canCancelOrder":False,
        "realOrdersEnabled":False,
        "status":"DOCUMENTARY_REVIEW_ONLY",
    }
