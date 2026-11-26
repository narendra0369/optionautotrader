"""V62 isolated fail-closed readiness evaluator. Never signs, issues or sends orders."""
from __future__ import annotations
from dataclasses import dataclass
from typing import Mapping
from uuid import UUID

REQUIRED = (
    "owner_mfa_attested", "angel_write_entitlement_attested",
    "static_ip_whitelist_attested", "algo_compliance_attested",
    "journal_atomicity_attested", "risk_reservation_attested",
    "leader_fence_attested", "broker_three_books_fresh_attested",
    "fill_reconciliation_attested", "protective_sl_lifecycle_attested",
    "unknown_outcome_recovery_attested", "manual_exposure_excluded_attested",
)

@dataclass(frozen=True)
class GateState:
    owner_stop: bool
    activation_count: int
    guard_state: str
    manual_positions: int
    daily_entries: int
    daily_limit: int
    risk_reserved: bool
    journal_durable: bool
    fence_valid: bool
    snapshot_age_seconds: int

def assess(*, owner_id: str, state: GateState,
           attestations: Mapping[str, bool] | None = None) -> dict:
    """Audit only: caller-provided attestations are NOT independent proof."""
    if type(state) is not GateState:
        raise TypeError("GATE_STATE_REQUIRED")
    blocks = []
    try:
        UUID(owner_id)
    except (ValueError, TypeError, AttributeError):
        blocks.append("OWNER_UUID_INVALID")
    if state.owner_stop is not False:
        blocks.append("OWNER_STOP_ACTIVE")
    if type(state.activation_count) is not int or state.activation_count != 1:
        blocks.append("ACTIVATION_UNVERIFIED")
    if state.guard_state != "RUNNING_VERIFIED":
        blocks.append("ENGINE_GUARD_DENY")
    if type(state.manual_positions) is not int or state.manual_positions != 0:
        blocks.append("MANUAL_EXPOSURE_PRESENT")
    if (type(state.daily_entries) is not int or type(state.daily_limit) is not int
        or state.daily_limit != 2 or not 0 <= state.daily_entries < 2):
        blocks.append("DAILY_TWO_TRADE_GATE")
    if state.risk_reserved is not True:
        blocks.append("RISK_NOT_RESERVED")
    if state.journal_durable is not True:
        blocks.append("JOURNAL_NOT_VERIFIED")
    if state.fence_valid is not True:
        blocks.append("LEADER_FENCE_NOT_VERIFIED")
    if type(state.snapshot_age_seconds) is not int or not 0 <= state.snapshot_age_seconds <= 10:
        blocks.append("BROKER_BOOKS_NOT_FRESH")
    a = attestations if isinstance(attestations, Mapping) else {}
    for key in REQUIRED:
        if a.get(key) is not True:
            blocks.append("ATTESTATION_MISSING:" + key)
    return {"mode": "STAGING_AUDIT_NO_SIGNING",
            "candidateConditionsMet": not blocks,
            "blockedReasons": sorted(set(blocks)),
            "canIssue": False, "canSubmitOrder": False, "canCancelOrder": False,
            "liveOrdersEnabled": False, "brokerCalls": 0}
