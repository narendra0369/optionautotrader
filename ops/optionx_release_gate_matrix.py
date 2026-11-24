"""OptionX multi-broker V8 release gate report (read-only, no secrets/orders).

Distinguishes independently checked runtime evidence from unverified broker,
exchange, production HTTPS, mobile/Android and unattended monitoring
requirements. A PASS in research checks NEVER translates to live authorization.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
import os

from live_gateway import hard_block_order
from live_v7.kill_switch import startup_state
from live_v7.ledger_store import public_ledger_status
from live_v7.risk_policy import stepped_paper_plan
from ops.synthetic_live_lifecycle_matrix import run_suite


class GateError(RuntimeError):
    pass


def assess(*, paper_db=None, verify_aws_ip=None) -> dict:
    gates = []
    def gate(key, state, evidence, *, required_for_live=True):
        gates.append({"gate": key, "state": state, "evidence": evidence,
                      "requiredForLive": required_for_live})

    hard_locked = hard_block_order()
    if hard_locked.get("error") != "REAL_ORDERS_HARD_LOCKED" or hard_locked.get("orderSent") is not False:
        raise GateError("REAL_ORDER_HARD_LOCK_REGRESSED")
    gate("REAL_ORDER_ENDPOINT_HARD_LOCK", "PASS",
         "Local code-level hard gate returns 423-compatible denial; no order sent")
    stop = startup_state()
    if stop.new_entries_blocked is not True or stop.live_execution_enabled is not False:
        raise GateError("KILL_SWITCH_FAIL_OPEN")
    gate("EMERGENCY_STOP_DEFAULT", "PASS",
         "Offline default STOPPED; no automatic arm/enable state")
    plan = stepped_paper_plan("500000")
    if plan["illustrativeLots"] != 12 or plan["maxTradesPerDay"] != 2:
        raise GateError("PAPER_RISK_POLICY_REGRESSION")
    gate("PAPER_RESEARCH_RISK_TIER", "PASS",
         "₹500,000 research tier: 12 virtual lots maximum, 2 paper entries per IST day",
         required_for_live=False)
    synthetic = run_suite()
    gate("SYNTHETIC_ORDER_LIFECYCLE_FAILURES", "PASS",
         str(synthetic["passed"]) + " offline synthetic cases exercised; not authenticated broker fills",
         required_for_live=False)
    if public_ledger_status().get("durableLedgerDeployed") is not False:
        raise GateError("LIVE_LEDGER_STATE_INVALID")
    gate("PRIVATE_LIVE_LEDGER", "BLOCKED",
         "Private live Postgres durable journal not deployed; paper SQLite is not an order journal")
    if verify_aws_ip is not None:
        from ops.verify_angel_aws_readiness import verify
        verify(verify_aws_ip)
        gate("AWS_MUMBAI_LOOPBACK_HEALTH_AND_EGRESS_IP", "PASS",
             "Observed outbound static IP and paper-only loopback service verified in this run")
    else:
        gate("AWS_MUMBAI_LOOPBACK_HEALTH_AND_EGRESS_IP", "UNVERIFIED_THIS_RUN",
             "Run with --verify-aws-ip only from the configured restricted AWS operator session")
    if paper_db is not None:
        from ops.paper_recovery_audit import integrity_report
        report = integrity_report(paper_db, strict_ownership=True)
        gate("VIRTUAL_PAPER_JOURNAL_INTEGRITY", "PASS",
             "Verified SQLite quick_check, schema, account and one-open-position limit",
             required_for_live=False)
        if report["virtualOpenPositions"]:
            gate("PAPER_POSITION_CONTINUOUS_PROTECTION", "BLOCKED",
                 "A virtual position is open but no continuous broker-native protective stop exists",
                 required_for_live=False)
        else:
            gate("PAPER_POSITION_CONTINUOUS_PROTECTION", "NOT_APPLICABLE",
                 "No open virtual position observed",
                 required_for_live=False)
    else:
        gate("VIRTUAL_PAPER_JOURNAL_INTEGRITY", "UNVERIFIED_THIS_RUN",
             "Run with --paper-db on the AWS paper host",
             required_for_live=False)
    remaining = [
        ("BROKER_EXECUTION_SCOPE_AND_REGULATORY_APPROVAL",
         "Angel exchange + algorithmic trading permission and static IP registration for execution are not confirmed by login alone"),
        ("AUTHENTICATED_ANGEL_ORDERBOOK_TRADEBOOK_POSITIONS",
         "Broker orderbook, tradebook, positions and authenticated owner matching need independent read-only reconciliation"),
        ("EXECUTION_GRADE_BID_ASK_TIMESTAMP_MARGIN_FEES",
         "NFO LTP lacks independently verified exchange timestamp/executable bid-ask; margin, charges and slippage unverified"),
        ("REAL_ORDER_LIFECYCLE_AND_RESTART_RECOVERY",
         "No actual order tests of LIMIT buy/sell, reject, partial fill, cancel/modify, unknown ACK, reconciliation and reboot"),
        ("BROKER_NATIVE_STOP_TARGET_PROTECTION",
         "No real protective order acknowledged, reconciled or tested with gaps and failures"),
        ("PRODUCTION_OWNER_AUTH_TLS_ACCESS_CONTROL",
         "No public authenticated HTTPS gateway between Render/Android and AWS"),
        ("ENCRYPTED_BROKER_SESSION_VAULT_AND_RENEWAL",
         "Short-lived interactive SSH TOTP session only; no approved encrypted unattended credential renewal"),
        ("24H_UNATTENDED_PAPER_FEED_AND_FAIL_CLOSED_MONITORING",
         "Current foreground monitor is at most 12 minutes; no overnight autonomous broker session or watchdog alerts"),
        ("PERMANENT_DAILY_RISK_BROKER_RECONCILIATION",
         "Paper max two trades cannot be copied to live account without owner budget, durable broker P&L + risk"),
        ("DELTA_STOXKART_SEPARATE_OWNER_VERIFICATION",
         "Other broker live connections and exchange permissions unverified here"),
        ("ANDROID_APPLICATION_SIGNING_DISTRIBUTION",
         "No Android installable release build tested from this branch"),
        ("15M_OPTION_BACKTEST_DATA_COMPLETENESS",
         "Previous sample of 26 complete candles cannot support strategies requiring >=120 candles"),
    ]
    for key, evidence in remaining:
        gate(key, "BLOCKED", evidence)
    return {
        "mode": "READ_ONLY_RELEASE_GATE_REPORT",
        "checkedAtUTC": datetime.now(timezone.utc).isoformat(),
        "realMoneyOrdersEnabled": False,
        "liveTradingAuthorized": False,
        "researchPaperAccountLiveOrderEquivalent": False,
        "syntheticLifecycleCasesPassed": synthetic["passed"],
        "gateCount": len(gates),
        "blockedCount": sum(g["state"] == "BLOCKED" for g in gates),
        "runtimeEvidenceNotAssumed": True,
        "gates": gates,
        "nextAction": "Continue paper-only. Verify authenticated read-only broker positions/market data and secure owner HTTPS; no real orders.",
    }


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description="One-shot read-only OptionX deployment and live readiness matrix")
    p.add_argument("--paper-db", help="Private paper SQLite file on restricted AWS host")
    p.add_argument("--verify-aws-ip", help="Expected registered AWS static public IP")
    p.add_argument("--json", action="store_true")
    args = p.parse_args(argv)
    try:
        result = assess(paper_db=args.paper_db, verify_aws_ip=args.verify_aws_ip)
    except Exception:
        # Sanitize diagnostics: external transport exceptions may contain secrets.
        print("BLOCKED: READONLY_RELEASE_GATE_CHECK_FAILED; REAL_MONEY_ORDERS_OFF")
        return 1
    if args.json:
        print(json.dumps(result, indent=2, ensure_ascii=False))
    else:
        print("OPTIONX ONE-SHOT RELEASE GATES — PAPER/RESEARCH ONLY")
        for g in result["gates"]:
            print(g["state"] + ": " + g["gate"])
        print("SYNTHETIC_LIFECYCLE_TESTS: " + str(result["syntheticLifecycleCasesPassed"]))
        print("BLOCKED_RELEASE_GATES: " + str(result["blockedCount"]))
        print("LIVE_TRADING_NOT_APPROVED; BROKER_ORDERS_SENT: 0")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
