"""One-shot AWS Mumbai OptionX safety gate: source tests + actual read-only Angel pilot.

This code CANNOT place, modify, cancel or reconcile broker orders. No unattended
trading is started. Credentials are entered solely through a private SSH TTY,
never printed, stored, passed on command lines or uploaded to CI/GitHub.
"""
from __future__ import annotations

import argparse
import getpass
import ipaddress
import os
from pathlib import Path
import pwd
import subprocess
import sys

from ops.verify_angel_aws_readiness import ReadinessError, verify as verify_aws
from live_gateway import hard_block_order
from live_v7.kill_switch import startup_state
from live_v7.ledger_store import public_ledger_status
from live_v7.risk_policy import live_risk_readiness, stepped_paper_plan

DEFAULT_DB = "/var/lib/optionx-paper/paper-v1.sqlite3"
OFFLINE_SUITES = (
    "live_v7.test_future_safety",
    "test_market_api",
    "test_angel_gateway",
    "test_live_gateway",
    "live_v7.test_angel_marketdata",
    "live_v7.test_angel_readonly_http",
    "live_v7.test_angel_snapshot_contract",
    "live_v7.test_extended_offline",
    "ops.test_verify_angel_aws_readiness",
    "ops.test_angel_ssh_readonly_pilot",
    "ops.test_paper_ledger_v1",
)


def _step(label: str, func):
    try:
        func()
    except Exception:
        print("BLOCKED: " + label + " — see locally generated test diagnostics; real orders OFF", flush=True)
        raise
    print("PASS: " + label, flush=True)


def offline_suite():
    # Runs only source/unit tests. No broker credentials, external orders,
    # database persistence, file mutation or service restart.
    run = subprocess.run(
        [sys.executable, "-B", "-m", "unittest", "-q", *OFFLINE_SUITES],
        cwd=str(Path(__file__).resolve().parent.parent),
        env={**os.environ, "OPTIONX_LIVE_ORDERS_ENABLED": "0",
             "OPTIONX_REAL_ORDERS_ENABLED": "0", "PYTHONDONTWRITEBYTECODE": "1"},
        capture_output=True, text=True, timeout=100, check=False,
    )
    if run.returncode != 0:
        # Don't dump unknown child stdout/stderr which may contain sensitive
        # environment-derived values. Developer can inspect locally.
        raise RuntimeError("OFFLINE_REGRESSION_FAILURE")
    import re
    count = re.search(r"Ran\s+(\d+)\s+tests?", run.stderr)
    print("PASS: Python offline regression suite — " +
          (count.group(1) + " tests" if count else "exit status 0"))


def safety_gates():
    locked = hard_block_order()
    if locked.get("error") != "REAL_ORDERS_HARD_LOCKED" or locked.get("orderSent") is not False:
        raise RuntimeError("HARD_ORDER_GATE_NOT_LOCKED")
    switch = startup_state()
    if switch.new_entries_blocked is not True or switch.live_execution_enabled is not False:
        raise RuntimeError("KILL_SWITCH_NOT_STOPPED")
    journal = public_ledger_status()
    if journal.get("liveOrderExecutionEnabled") is not False or journal.get("newOrdersBlocked") is not True:
        raise RuntimeError("LIVE_LEDGER_FAIL_OPEN")
    plan = stepped_paper_plan("500000")
    if plan.get("illustrativeLots") != 12 or plan.get("maxTradesPerDay") != 2 or plan.get("canSubmitOrder") is not False:
        raise RuntimeError("PAPER_RISK_TIER_REGRESSION")
    live_kwargs = dict(
        user_approved_live_budget=False, confirmed_contract_lot_size=False,
        execution_grade_quote=False, verified_margin_available=False,
        max_loss_includes_costs_and_slippage=False,
        daily_loss_broker_reconciled=False, broker_risk_approval=False,
    )
    live = live_risk_readiness(**live_kwargs)
    if live.get("canSubmitOrder") is not False or live.get("liveExecutionEnabled") is not False:
        raise RuntimeError("UNSAFE_LIVE_RISK_STATUS")
    print("PASS: real-order hard lock + emergency stop + paper 12-lot tier model")
    print("PASS: live risk policy refuses unverified margin, execution price, costs and approval")
    print("BLOCKED_PENDING: real order lifecycle, cancellation/partial fills, margin, regulatory approval")
    print("BLOCKED_PENDING: public AWS HTTPS owner-bound connection and 24h monitoring")


def paper_state(path):
    from ops.paper_ledger_v1 import PaperError, status
    p = Path(path)
    if not p.exists():
        print("PENDING: private paper journal not initialized; offline paper tests PASSED")
        print("NOTE: Do not auto-open a paper position or create broker orders during checks")
        return
    if not p.is_file() or p.is_symlink():
        raise RuntimeError("PRIVATE_PAPER_JOURNAL_PATH_UNSAFE")
    try:
        s = status(p)
    except PaperError:
        raise RuntimeError("PRIVATE_PAPER_JOURNAL_UNREADABLE") from None
    print("PASS: persisted paper journal readable")
    print("PAPER_STATUS: trades_today=" + str(s["tradesToday"]) +
          " open_virtual_position=" + str(bool(s["openPosition"])) +
          " equity_before_charges=" + s["realizedEquityBeforeChargesINR"])
    print("NOTE: journal is virtual-only; no unattended quote monitoring")


def broker_once(args) -> int:
    if pwd.getpwuid(os.geteuid()).pw_name != "optionx":
        raise RuntimeError("BROKER_TTY_MUST_RUN_AS_RESTRICTED_OPTIONX_USER")
    if not (sys.stdin.isatty() and sys.stdout.isatty()):
        raise RuntimeError("BROKER_REQUIRES_INTERACTIVE_SSH_TTY")
    # Exactly one credential prompt and one short-lived RAM broker session.
    from ops.angel_ssh_readonly_pilot import main as broker_pilot_main
    cmd = ["--expected-ip", args.expected_ip, "--connect", "--market", args.market,
           "--side", args.side, "--days", str(args.days), "--paper-preview"]
    if args.strike:
        cmd.extend(["--strike", args.strike])
    result = broker_pilot_main(cmd)
    if result != 0:
        raise RuntimeError("READONLY_BROKER_PILOT_UNVERIFIED")
    print("PASS: one authenticated Angel profile + verified NFO contract + LTP + 15m history")
    print("NOTE: broker session discarded; no real or virtual positions opened")
    return 0


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="All safe checks in one run; real orders always OFF")
    parser.add_argument("--expected-ip", required=True)
    parser.add_argument("--with-broker", action="store_true", help="Single private credential prompt and read-only broker test")
    parser.add_argument("--market", choices=("NIFTY", "BANKNIFTY"), default="NIFTY")
    parser.add_argument("--side", choices=("CE", "PE"), default="CE")
    parser.add_argument("--strike", default="26000", help="Example only; choose a relevant strike for your market")
    parser.add_argument("--days", type=int, choices=(1, 2, 3, 5, 7), default=3)
    parser.add_argument("--paper-db", default=DEFAULT_DB)
    args = parser.parse_args(argv)
    try:
        ip = ipaddress.ip_address(args.expected_ip)
        if ip.version != 4 or not ip.is_global:
            raise RuntimeError("EXPECTED_PUBLIC_IPV4_INVALID")
        print("OPTIONX_AWS_BATCH_START: research mode, live money orders OFF", flush=True)
        _step("AWS outbound static IPv4 + local health + HTTP order/auth gates",
              lambda: verify_aws(args.expected_ip))
        _step("Python offline safety tests", offline_suite)
        _step("live-order kill switch and tiered risk limits", safety_gates)
        _step("private persistent virtual paper journal", lambda: paper_state(args.paper_db))
        if args.with_broker:
            print("BROKER_CHECK: provide secrets only in your own AWS SSH terminal")
            _step("Angel One verified read-only profile, LTP and 15m candles",
                  lambda: broker_once(args))
        else:
            print("PENDING: authenticated Angel One read-only check not requested")
        print("OPTIONX_AWS_BATCH_CHECKS_COMPLETED: only safe checks; real orders remain OFF")
        print("LIVE_TRADING_NOT_APPROVED: no real orders may be submitted")
        return 0
    except (RuntimeError, ReadinessError, ValueError, OSError, subprocess.TimeoutExpired) as exc:
        # Avoid printing SDK/HTTP exceptions that might contain broker secrets.
        message = str(exc)
        safe_codes = (
            "EXPECTED_PUBLIC_IPV4_INVALID", "OFFLINE_REGRESSION_FAILURE",
            "HARD_ORDER_GATE_NOT_LOCKED", "KILL_SWITCH_NOT_STOPPED",
            "LIVE_LEDGER_FAIL_OPEN", "PAPER_RISK_TIER_REGRESSION",
            "UNSAFE_LIVE_RISK_STATUS", "PRIVATE_PAPER_JOURNAL_PATH_UNSAFE",
            "PRIVATE_PAPER_JOURNAL_UNREADABLE",
            "BROKER_TTY_MUST_RUN_AS_RESTRICTED_OPTIONX_USER",
            "BROKER_REQUIRES_INTERACTIVE_SSH_TTY", "READONLY_BROKER_PILOT_UNVERIFIED",
        )
        if message not in safe_codes:
            message = "UNEXPECTED_CHECK_FAILURE"
        print("OPTIONX_AWS_BATCH_BLOCKED: " + message, file=sys.stderr)
        print("LIVE_REAL_ORDERS_ENABLED: false", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
