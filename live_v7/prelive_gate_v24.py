"""OptionX V24 production preflight admissibility assessment.

Pure fail-closed report. This module CANNOT authorize an execution. Real
orders require a separately reviewed/approved release and user-approved
bounded real-money test. The source-level broker transport lock stays in place.

Broker policy checked against Angel One's 13-Mar-2026 article: registered
static IPv4, client-owned DIY tech-savvy hosting exemption vs vendor hosting,
10 OPS threshold with generic ID below threshold, market/IOC prohibited.
These are policy assumptions requiring broker confirmation for the EXACT
account and order route; do not infer approval from static IP or GET success.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping, Any


class PreflightError(ValueError):
    pass


@dataclass(frozen=True)
class RetailAlgoAttestation:
    client_self_coded: bool
    hosted_on_own_registered_static_ip: bool
    broker_writing_enabled_for_api_key: bool
    broker_confirmed_generic_algo_tag: bool
    broker_confirmed_limit_and_sl_limit_for_nfo: bool
    broker_confirmed_order_rate_cap: bool
    broker_confirmed_session_order_rules: bool
    live_test_risk_authorized: bool
    broker_test_window_confirmed: bool


def check_order_contract(order: Mapping[str, Any]) -> list[str]:
    """LIMIT DAY ENTRY BUY / STOPLOSS_LIMIT DAY EXIT SELL ONLY."""
    reasons=[]
    if not isinstance(order,Mapping):
        return ["ORDER_CONTRACT_MISSING"]
    kind=order.get("kind")
    if order.get("exchange")!="NFO":
        reasons.append("ONLY_NFO_ALLOWED")
    if order.get("duration")!="DAY":
        reasons.append("IOC_AND_NON_DAY_NOT_ALLOWED")
    if kind=="ENTRY":
        if (order.get("side")!="BUY" or order.get("order_type")!="LIMIT"
                or order.get("variety")!="NORMAL"):
            reasons.append("ENTRY_BUY_LIMIT_REQUIRED")
    elif kind=="PROTECT":
        if (order.get("side")!="SELL" or order.get("order_type")!="STOPLOSS_LIMIT"
                or order.get("variety")!="STOPLOSS"):
            reasons.append("NATIVE_SELL_SL_LIMIT_REQUIRED")
    else:
        reasons.append("UNKNOWN_ORDER_INTENT")
    if (type(order.get("quantity")) is not int or order["quantity"]<=0):
        reasons.append("ORDER_QUANTITY_NOT_VALIDATED")
    if type(order.get("instrument_token")) is not str or not order["instrument_token"].isdigit():
        reasons.append("BROKER_CONTRACT_TOKEN_UNVERIFIED")
    if order.get("order_type")=="MARKET" or order.get("duration")=="IOC":
        reasons.append("ALGO_MARKET_OR_IOC_PROHIBITED")
    return sorted(set(reasons))


def evaluate_prelive(*, compliance:RetailAlgoAttestation,
                     read_only_audit:Mapping[str,Any],
                     durable_guard_state:str,
                     daily_reserved_auto_entries:int,
                     recent_broker_orders_per_second:int,
                     intended_entry:Mapping[str,Any],
                     intended_protection:Mapping[str,Any],
                     verified_account_exposure_count:int,
                     owner_authenticated:bool) -> dict[str,Any]:
    """Document every blocker, never return canSubmitOrder=True.

    Neither mocked attestations nor successful GETs prove real money safety.
    The live transport remains source locked even with zero reported blockers.
    """
    if not isinstance(compliance,RetailAlgoAttestation) or not isinstance(read_only_audit,Mapping):
        raise PreflightError("TRUSTED_ATTESTATION_AND_AUDIT_REQUIRED")
    blocks=set()
    if owner_authenticated is not True:
        blocks.add("OWNER_REAUTHENTICATION_REQUIRED")
    flags={
        "client_self_coded":"SELF_CODED_ACCOUNT_CLASSIFICATION_UNCONFIRMED",
        "hosted_on_own_registered_static_ip":"PRIMARY_STATIC_IP_APPROVAL_UNCONFIRMED",
        "broker_writing_enabled_for_api_key":"BROKER_ORDER_API_PERMISSION_UNCONFIRMED",
        "broker_confirmed_generic_algo_tag":"EXCHANGE_GENERIC_ALGO_TAG_UNCONFIRMED",
        "broker_confirmed_limit_and_sl_limit_for_nfo":"BROKER_NATIVE_LIMIT_STOP_API_UNCONFIRMED",
        "broker_confirmed_order_rate_cap":"BROKER_RATE_LIMIT_UNCONFIRMED",
        "broker_confirmed_session_order_rules":"SESSION_AND_AUCTION_GATE_UNCONFIRMED",
        "live_test_risk_authorized":"BOUNDED_REAL_MONEY_TEST_NOT_AUTHORIZED",
        "broker_test_window_confirmed":"BROKER_TEST_WINDOW_UNCONFIRMED",
    }
    for name,block in flags.items():
        if getattr(compliance,name) is not True:
            blocks.add(block)
    if durable_guard_state!="STOPPED":
        blocks.add("PRODUCTION_GUARD_NOT_FAIL_CLOSED")
    if type(daily_reserved_auto_entries) is not int or not 0<=daily_reserved_auto_entries<=2:
        blocks.add("DAILY_TWO_ENTRY_BUDGET_INVALID")
    elif daily_reserved_auto_entries>=2:
        blocks.add("DAILY_TWO_ENTRY_LIMIT_REACHED")
    if (type(recent_broker_orders_per_second) is not int
            or not 0<=recent_broker_orders_per_second<10):
        blocks.add("BROKER_OPS_THRESHOLD_REACHED_OR_UNKNOWN")
    if type(verified_account_exposure_count) is not int or verified_account_exposure_count!=0:
        blocks.add("ACCOUNT_MANUAL_OR_UNTRACKED_EXPOSURE_PRESENT")
    if read_only_audit.get("liveOrdersEnabled") is not False:
        blocks.add("BROKER_AUDIT_NOT_READ_ONLY")
    if read_only_audit.get("manualOrUntrackedOrders",1)!=0:
        blocks.add("MANUAL_OR_UNTRACKED_ORDERS_PRESENT")
    if read_only_audit.get("brokerSnapshotFreshAndAuthenticated") is not True:
        blocks.add("FRESH_AUTHENTICATED_BROKER_SNAPSHOT_REQUIRED")
    blocks.update(check_order_contract(intended_entry))
    blocks.update(check_order_contract(intended_protection))
    # Explicitly not a zero-block unlock: even with all external facts affirmed,
    # programmatic LIVE execution requires a separately certified code release.
    blocks.add("REAL_EXECUTION_SOURCE_LOCKED")
    blocks.add("NATIVE_STOP_AND_RECOVERY_E2E_NOT_CERTIFIED")
    return {
        "preliveReviewComplete":True,
        "blockedReasons": sorted(blocks),
        "canSubmitOrder":False,
        "canCancelOrder":False,
        "liveOrdersEnabled":False,
        "newEntriesBlocked":True,
        "manualPositionsModified":False,
        "databaseMutated":False,
    }
