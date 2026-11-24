"""OptionX broker lifecycle synthetic failure matrix — OFFLINE ONLY.

Replay fixed synthetic broker events with pure V7 shadow recovery. Never
connect to a broker, open a socket, submit/cancel orders, import private keys,
create a live ledger, or authorize real-money trading. Fail the run when
an unsafe anomaly stops being detected or any new entry is enabled.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timedelta, timezone
import json
from typing import Any

from live_v7.shadow_recovery import replay
from live_gateway import hard_block_order

NOW = datetime(2026, 11, 24, 10, 30, tzinfo=timezone.utc)
QTY = 65


def _event(kind: str, serial: int, seconds=0, **kwargs):
    return {
        "event_id": f"shadowEvt{serial:04d}",
        "kind": kind,
        "as_of": NOW - timedelta(seconds=seconds),
        "source_verified": True,
        **kwargs,
    }


def scenarios() -> list[dict[str, Any]]:
    """Each scenario documents exact expected anomaly, not trading efficacy."""
    fill = _event("ENTRY_FILL", 1, cumulative_quantity=QTY)
    stop = _event("STOP_ACK", 2, protected_quantity=QTY)
    return [
        {"name": "entry_ack_only", "events": [_event("ENTRY_ACK", 1)],
         "expected": [], "quantity": QTY},
        {"name": "complete_stop_ack_shadow_consistent", "events": [fill, stop],
         "expected": [], "quantity": QTY},
        {"name": "entry_partial_fill_unprotected", "events": [
            _event("ENTRY_FILL", 1, cumulative_quantity=20)],
         "expected": ["OPEN_POSITION_WITHOUT_FULL_STOP_COVERAGE"], "quantity": QTY},
        {"name": "stop_ack_only_partial", "events": [
            _event("ENTRY_FILL", 1, cumulative_quantity=20),
            _event("STOP_ACK", 2, protected_quantity=20)],
         "expected": [], "quantity": QTY},
        {"name": "missing_stop", "events": [fill],
         "expected": ["OPEN_POSITION_WITHOUT_FULL_STOP_COVERAGE"], "quantity": QTY},
        {"name": "stop_unknown", "events": [fill, _event("STOP_UNKNOWN", 2)],
         "expected": ["UNKNOWN_BROKER_ORDER_OUTCOME"], "quantity": QTY},
        {"name": "stop_rejected", "events": [fill, _event("STOP_REJECT", 2)],
         "expected": ["BROKER_STOP_REJECTED"], "quantity": QTY},
        {"name": "cancel_race", "events": [fill, stop, _event("CANCEL_ACK", 3)],
         "expected": ["UNKNOWN_BROKER_ORDER_OUTCOME"], "quantity": QTY},
        {"name": "partial_fill_after_stop", "events": [
            _event("ENTRY_FILL", 1, cumulative_quantity=20),
            _event("STOP_ACK", 2, protected_quantity=20),
            _event("ENTRY_FILL", 3, cumulative_quantity=QTY)],
         "expected": ["NEW_FILL_EXCEEDS_STOP_COVERAGE"], "quantity": QTY},
        {"name": "duplicate_event_id", "events": [
            _event("ENTRY_FILL", 1, cumulative_quantity=20),
            _event("ENTRY_FILL", 1, cumulative_quantity=20)],
         "expected": ["DUPLICATE_EVENT"], "quantity": QTY},
        {"name": "broker_evidence_stale", "events": [
            _event("ENTRY_ACK", 1, seconds=25)],
         "expected": ["BROKER_EVIDENCE_STALE"], "quantity": QTY},
        {"name": "restart_without_full_reconciliation", "events": [fill, stop],
         "expected": ["RESTART_REQUIRES_FULL_BROKER_RECONCILIATION"],
         "quantity": QTY, "restart_occurred": True},
        {"name": "restart_reconciled_shadow_only", "events": [fill, stop],
         "expected": [], "quantity": QTY, "restart_occurred": True,
         "full_broker_reconciliation_after_restart": True},
        {"name": "unauthenticated_broker_snapshot", "events": [fill, stop],
         "expected": ["OWNER_ACCOUNT_NOT_VERIFIED"], "quantity": QTY, "verified_account": False},
        {"name": "entry_acknowledgement_unknown", "events": [_event("ENTRY_UNKNOWN", 1)],
         "expected": ["UNKNOWN_BROKER_ORDER_OUTCOME"], "quantity": QTY},
        {"name": "unknown_reconciliation_unverified", "events": [
            _event("ENTRY_UNKNOWN", 1), _event("RECONCILED", 2)],
         "expected": ["RECONCILIATION_NOT_VERIFIED"], "quantity": QTY},
        {"name": "unknown_followed_verified_reconciliation", "events": [
            _event("ENTRY_UNKNOWN", 1),
            _event("RECONCILED", 2, full_orderbook_verified=True, position_verified=True)],
         "expected": [], "quantity": QTY},
        {"name": "oversize_exit", "events": [
            fill, _event("EXIT_FILL", 2, cumulative_quantity=80)],
         "expected": ["EXIT_REPLAY_OR_POSSIBLE_NAKED_SHORT"], "quantity": QTY},
        {"name": "filled_then_exit_stop_orphan", "events": [
            fill, stop, _event("EXIT_FILL", 3, cumulative_quantity=QTY)],
         "expected": ["POSSIBLE_ORPHAN_STOP_ORDER"], "quantity": QTY},
        {"name": "entry_rejected_after_fill", "events": [
            fill, _event("ENTRY_REJECT", 2)],
         "expected": ["REJECTED_AFTER_ENTRY_FILL"], "quantity": QTY},
        {"name": "future_event_not_accepted", "events": [
            _event("ENTRY_FILL", 1, seconds=-20, cumulative_quantity=QTY)],
         "expected": ["EVENT_OUT_OF_ORDER_OR_FROM_FUTURE"], "quantity": QTY},
    ]


def run_suite() -> dict:
    lock = hard_block_order()
    if lock.get("error") != "REAL_ORDERS_HARD_LOCKED" or lock.get("orderSent") is not False:
        raise AssertionError("BROKER_LIVE_ORDER_LOCK_MISSING")
    report = []
    for item in scenarios():
        result = replay(
            item["events"], planned_entry_quantity=item["quantity"], now=NOW,
            verified_account=item.get("verified_account", True),
            restart_occurred=item.get("restart_occurred", False),
            full_broker_reconciliation_after_restart=item.get(
                "full_broker_reconciliation_after_restart", False),
        )
        anomalies = set(result["anomalies"])
        expected = set(item["expected"])
        if not expected <= anomalies:
            raise AssertionError(item["name"] + ": REQUIRED_ANOMALY_NOT_DETECTED")
        if not expected and anomalies:
            raise AssertionError(item["name"] + ": UNEXPECTED_ANOMALY")
        if (result["canSubmitOrder"] is not False or result["liveExecutionEnabled"] is not False
                or result["newEntriesBlocked"] is not True):
            raise AssertionError(item["name"] + ": LIVE_ENTRY_UNEXPECTEDLY_ENABLED")
        report.append({"scenario": item["name"],
                       "syntheticAnomalies": sorted(anomalies),
                       "newEntriesBlocked": True,
                       "brokerOrdersSent": 0,
                       "result": "PASS"})
    return {
        "mode": "SYNTHETIC_BROKER_EVENT_REPLAY_ONLY",
        "scenarioCount": len(report),
        "passed": len(report),
        "realBrokerOrderTestsPerformed": False,
        "liveTradingApproved": False,
        "realOrderEndpointsStillLocked": True,
        "scenarios": report,
        "pending": [
            "BROKER_AUTHENTICATED_ORDERBOOK_TRADEBOOK_POSITION_RECONCILIATION",
            "OFFICIAL_BROKER_ORDER_TYPE_AND_EXCHANGE_APPROVAL",
            "ACTUAL_PARTIAL_FILL_REJECT_CANCEL_RESTART_LIFECYCLE",
            "EXECUTION_GRADE_QUOTES_MARGIN_FEES_SLIPPAGE",
            "PRODUCTION_OWNER_AUTH_HTTPS_AND_SECURE_VAULT",
            "24H_UNATTENDED_MONITORING_AND_FAILURE_ALERTS",
            "EXPLICIT_SEPARATE_LIVE_RISK_AND_LIVE_ORDER_APPROVAL",
        ],
    }


def main(argv=None):
    p = argparse.ArgumentParser(description="Local-only synthetic broker lifecycle safety matrix")
    p.add_argument("--json", action="store_true", help="Print sanitized machine-readable JSON")
    args = p.parse_args(argv)
    try:
        result = run_suite()
    except (AssertionError, ValueError) as exc:
        print("BLOCKED: SYNTHETIC_LIFECYCLE_GATE_FAILED")
        return 1
    if args.json:
        print(json.dumps(result, indent=2))
    else:
        print("PASS: " + str(result["passed"]) + "/" + str(result["scenarioCount"]) +
              " offline broker lifecycle failure scenarios")
        print("PASS: every scenario remains fail-closed, real-money orders LOCKED")
        print("PENDING: authenticated broker order lifecycle tests NOT PERFORMED")
        for gate in result["pending"]:
            print("PENDING: " + gate)
        print("LIVE_TRADING_NOT_APPROVED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
