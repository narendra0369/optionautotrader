"""OPTIONX V88 owner-facing dry-run preflight. Never grants trading capability.

Designed to expose remaining blockers; intentionally cannot activate a broker.
No I/O, credentials, database changes, signing or order SDK methods.
A display of READY_FOR_REVIEW is not a signed production authorization.
"""
from __future__ import annotations
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any, Mapping

@dataclass(frozen=True)
class ReadinessEvidence:
    owner_aal2_authenticated: bool = False
    worker_registered_verified: bool = False
    independent_attestation_current: bool = False
    attestation_revocation_checked: bool = False
    live_risk_policy_independently_approved: bool = False
    server_stop_transition_authorized: bool = False
    broker_owner_authenticated: bool = False
    broker_static_ip_accepted: bool = False
    order_lifecycle_certified: bool = False
    restart_recovery_certified: bool = False
    strategy_version_approved: bool = False
    broker_orderbook_tradebook_positionbook_reconciled: bool = False
    existing_manual_exposure_handled: bool = False
    existing_active_order_protection_verified: bool = False
    limit_sl_validation_certified: bool = False
    market_session_verified: bool = False

FIELDS = tuple(ReadinessEvidence.__dataclass_fields__)
LIMIT_TRADES_PER_DAY = 2

def assess(
    evidence: ReadinessEvidence,
    *,
    reconciliation: Mapping[str, Any] | None,
    active_entries_today: int,
    max_entries_per_day: int,
    remaining_daily_loss_budget: int | None,
    broker_snapshot_at: datetime | None,
    now: datetime,
) -> dict[str, Any]:
    if not isinstance(evidence, ReadinessEvidence):
        raise TypeError("Only typed local server evidence accepted")
    reasons = ["MISSING_" + field.upper() for field in FIELDS if getattr(evidence, field) is not True]
    if type(active_entries_today) is not int or active_entries_today < 0:
        reasons.append("TRADE_COUNT_UNVERIFIED")
    elif active_entries_today >= LIMIT_TRADES_PER_DAY:
        reasons.append("GLOBAL_TWO_ENTRY_LIMIT_REACHED")
    if type(max_entries_per_day) is not int or max_entries_per_day != LIMIT_TRADES_PER_DAY:
        reasons.append("GLOBAL_ENTRY_LIMIT_POLICY_MISMATCH")
    if type(remaining_daily_loss_budget) is not int or remaining_daily_loss_budget <= 0:
        reasons.append("DAILY_RISK_BUDGET_UNVERIFIED_OR_EXHAUSTED")
    if (not isinstance(now, datetime) or now.utcoffset() is None
        or not isinstance(broker_snapshot_at, datetime)
        or broker_snapshot_at.utcoffset() is None
        or not timedelta(0) <= now - broker_snapshot_at <= timedelta(seconds=10)):
        reasons.append("BROKER_SNAPSHOT_STALE_OR_MISSING")
    if not isinstance(reconciliation, Mapping) or reconciliation.get("scope") != "READ_ONLY_DIAGNOSTIC" or reconciliation.get("broker") != "Angel":
        reasons.append("RECONCILIATION_NOT_VERIFIED")
    else:
        if reconciliation.get("recoveryCertified") is not True:
            reasons.append("BROKER_RECOVERY_NOT_CERTIFIED")
        if reconciliation.get("reasons"):
            reasons.append("UNRESOLVED_RECONCILIATION_FLAGS")
        if reconciliation.get("manualPositionsTouched") is not False:
            reasons.append("MANUAL_POSITION_ISOLATION_UNVERIFIED")
    # This function is a diagnostics contract, NOT an order authorization.
    # Authorization requires a separate protected, DB-transactional lease
    # and atomic risk reservation after all valid signed evidence is approved.
    return {
        "gate": "V88_NONPRODUCTION_READINESS",
        "eligibleForFurtherReview": not reasons,
        "unresolved": sorted(set(reasons)),
        "newOrdersEnabled": False, "canBuy": False, "canSell": False,
        "canModify": False, "canCancel": False, "stopBypassed": False,
    }
