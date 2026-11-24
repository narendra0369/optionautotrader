"""OptionX Angel One PRIVATE, SSH-only Orderbook + Positions read audit.

This module does NOT submit, modify, cancel or poll any real order. It fetches
only read-only owner-verified Angel snapshots through the existing explicit GET
allowlist and prints *counts only*, never symbols, order IDs or account details.
No broker credentials or session survive process exit.

Successful account snapshot reads are NOT authorization for real trading,
execution-grade fill reconciliation or exchange algo compliance.
"""
from __future__ import annotations

import argparse
from collections import Counter
import os
import pwd
import sys
from typing import Mapping

from ops.verify_angel_aws_readiness import verify as aws_precheck

OWNER = "optionx-ssh-local-operator"
KNOWN_STATUSES = frozenset({
    "COMPLETE", "OPEN", "PENDING", "PARTIALLY_FILLED",
    "CANCEL_REQUESTED", "REJECTED", "CANCELLED"
})


class AccountAuditError(RuntimeError):
    pass


def audit_snapshot(positions: Mapping, orderbook: Mapping) -> dict:
    """Compute privacy-preserving count-only account review.

    If either broker read is unavailable/malformed or a position/order is
    outstanding, this MUST NOT be presented as broker reconciliation or
    trading authorization. We only observe, never modify the account.
    """
    if not isinstance(positions, Mapping) or not isinstance(orderbook, Mapping):
        raise AccountAuditError("BROKER_SNAPSHOT_MISSING")
    for resource, payload in (("positions", positions), ("orderbook", orderbook)):
        if (payload.get("broker") != "Angel" or payload.get("resource") != resource
                or payload.get("trustedAccount") != "OWNER_PROFILE_MATCHED"
                or payload.get("canSubmitOrder") is not False
                or payload.get("orderExecutionEnabled") is not False):
            raise AccountAuditError("BROKER_READONLY_CONTRACT_MISMATCH")
        records = payload.get("records")
        if (not isinstance(records, list) or
                isinstance(payload.get("recordCount"), bool) or
                payload.get("recordCount") != len(records)):
            raise AccountAuditError("BROKER_SNAPSHOT_COUNT_MISMATCH")
        if any(not isinstance(r, dict) for r in records):
            raise AccountAuditError("BROKER_SNAPSHOT_ROW_MALFORMED")

    pos_rows = positions["records"]
    orders = orderbook["records"]
    if any(
        not isinstance(p.get("net_quantity"), int)
        or isinstance(p.get("net_quantity"), bool)
        for p in pos_rows
    ):
        raise AccountAuditError("POSITION_QUANTITY_UNVERIFIED")
    stats = Counter()
    for order in orders:
        status = order.get("status")
        if status not in KNOWN_STATUSES or order.get("statusKnown") is not True:
            raise AccountAuditError("UNKNOWN_BROKER_ORDER_STATE")
        stats[status] += 1
    active_positions = sum(p["net_quantity"] != 0 for p in pos_rows)
    open_orders = sum(stats[state] for state in (
        "OPEN", "PENDING", "PARTIALLY_FILLED", "CANCEL_REQUESTED"
    ))
    has_exposure = bool(open_orders or active_positions)
    return {
        "mode": "PRIVATE_BROKER_READONLY_ACCOUNT_OBSERVATION",
        "broker": "Angel",
        "positionRowsCount": len(pos_rows),
        "nonzeroNfoPositionRows": active_positions,
        "nfoOrderRowsCount": len(orders),
        "pendingOrOpenNfoOrderRows": open_orders,
        "historicalFinalOrderRows": len(orders) - open_orders,
        "historicalStatusCounts": dict(sorted(stats.items())),
        "accountHasUnresolvedOrdersOrPositions": has_exposure,
        "sourceOwnerVerifiedByExistingGateway": True,
        "sourceReadInSingleTemporaryAuthSession": True,
        "brokerOrderSubmissionTested": False,
        "brokerFillReconciliationCompleted": False,
        "exchangeAlgoApprovalVerified": False,
        "liveOrdersEnabled": False,
        "canSubmitOrder": False,
        "nextAction": (
            "MANUAL_REVIEW_BROKER_ORDERBOOK_AND_POSITIONS_REQUIRED" if has_exposure
            else "ACCOUNT_READS_SUCCEEDED_BUT_LIVE_EXECUTION_STILL_LOCKED"
        ),
    }


def run_owner_readonly(*, expected_ip: str):
    if os.name != "posix" or pwd.getpwuid(os.geteuid()).pw_name != "optionx":
        raise AccountAuditError("RESTRICTED_AWS_OPTIONX_USER_REQUIRED")
    if not (sys.stdin.isatty() and sys.stdout.isatty()):
        raise AccountAuditError("PRIVATE_SSH_INTERACTIVE_TERMINAL_REQUIRED")

    # Verify AWS egress, localhost API, auth gate and real-money order lock
    # before any broker credentials are requested from the operator.
    aws_precheck(expected_ip)
    print("PASS: AWS_IP_AND_REAL_ORDER_LOCKS_VERIFIED", flush=True)

    import angel_gateway
    from live_v7.read_only_bridge import (
        angel_owner_snapshot, ReadOnlyBridgeError,
    )
    from ops.angel_batch_readonly import _prompt_credentials

    os.environ["OPTIONX_OWNER_USER_ID"] = OWNER
    os.environ["ANGEL_EGRESS_PUBLIC_IPV4"] = expected_ip

    secrets = _prompt_credentials()
    try:
        profile = angel_gateway.connect(OWNER, secrets)
    finally:
        secrets.clear()

    if profile.get("connected") is not True:
        raise AccountAuditError("BROKER_PROFILE_NOT_VERIFIED")
    print("PASS: ANGEL_PROFILE_VERIFIED_TEMPORARY_SESSION", flush=True)

    try:
        # The only network calls below are owner-bound GET on allowlisted
        # read-only resources. No account modifications/order transmission.
        pos = angel_owner_snapshot(
            verified_optionx_user_id=OWNER, resource="positions",
            server_feature_flag_enabled=True,
        )
        orderbook = angel_owner_snapshot(
            verified_optionx_user_id=OWNER, resource="orderbook",
            server_feature_flag_enabled=True,
        )
        report = audit_snapshot(pos, orderbook)
        print("PASS: ANGEL_ORDERBOOK_AND_POSITIONS_GET_READONLY", flush=True)
        print("NFO_POSITION_ROWS=" + str(report["positionRowsCount"]), flush=True)
        print("NFO_NONZERO_POSITION_ROWS=" + str(report["nonzeroNfoPositionRows"]), flush=True)
        print("NFO_ORDER_ROWS=" + str(report["nfoOrderRowsCount"]), flush=True)
        print("NFO_OPEN_OR_PENDING_ORDER_ROWS=" +
              str(report["pendingOrOpenNfoOrderRows"]), flush=True)
        print("POSITION_OR_ORDER_MANUAL_REVIEW_REQUIRED=" +
              str(report["accountHasUnresolvedOrdersOrPositions"]), flush=True)
        print("ACCOUNT_READONLY_PILOT_COMPLETED: no broker orders sent", flush=True)
        print("LIVE_TRADING_NOT_APPROVED", flush=True)
        return report
    finally:
        angel_gateway.disconnect(OWNER)


def main(argv=None):
    parser = argparse.ArgumentParser(description="Private read-only Angel NFO orderbook/positions audit")
    parser.add_argument("--expected-ip", required=True, help="Expected AWS Mumbai registered static egress IPv4")
    args = parser.parse_args(argv)
    try:
        report = run_owner_readonly(expected_ip=args.expected_ip)
        return 0 if report["canSubmitOrder"] is False else 1
    except Exception as exc:
        # Never log sensitive broker HTTP payloads, headers, tokens or rows.
        safe_codes = {
            "BROKER_SNAPSHOT_MISSING", "BROKER_READONLY_CONTRACT_MISMATCH",
            "BROKER_SNAPSHOT_COUNT_MISMATCH", "BROKER_SNAPSHOT_ROW_MALFORMED",
            "POSITION_QUANTITY_UNVERIFIED", "UNKNOWN_BROKER_ORDER_STATE",
            "RESTRICTED_AWS_OPTIONX_USER_REQUIRED",
            "PRIVATE_SSH_INTERACTIVE_TERMINAL_REQUIRED",
            "BROKER_PROFILE_NOT_VERIFIED",
        }
        status = str(exc) if isinstance(exc, AccountAuditError) and str(exc) in safe_codes else "BROKER_PRIVATE_READ_UNAVAILABLE_OR_NOT_PERMITTED"
        print("BLOCKED: " + status, file=sys.stderr)
        print("LIVE_REAL_ORDERS_OFF", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
