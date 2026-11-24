"""Foreground-only Angel One paper-position quote monitor; NO real order methods.

Runs from the user's PRIVATE interactive SSH session for at most 12 minutes.
Secrets/JWT stay in one Python process RAM, never stored, printed or reused
on the next session. No background daemon, no automated entries, and no
real broker buys, sells, modifications or stop orders.
"""
from __future__ import annotations

import argparse
from datetime import datetime, time as dtime, timezone
import os
from pathlib import Path
import pwd
import sys
import time
from zoneinfo import ZoneInfo

from ops.paper_ledger_v1 import DB_PATH, PaperError, monitor_paper, status
from ops.verify_angel_aws_readiness import ReadinessError, verify as verify_aws

IST = ZoneInfo("Asia/Kolkata")
OWNER = "optionx-ssh-local-operator"
MAX_SESSION_SECONDS = 12 * 60


class MonitorError(RuntimeError):
    pass


def exchange_hours(now: datetime) -> bool:
    """Conservative NSE weekday clock gate; holiday calendar NOT verified."""
    if not isinstance(now, datetime) or now.tzinfo is None:
        return False
    local = now.astimezone(IST)
    return (local.weekday() < 5 and
            dtime(9, 15) <= local.time().replace(tzinfo=None) < dtime(15, 30))


def read_virtual_position(db_path, *, now=None):
    snapshot = status(db_path, now=now)
    pos = snapshot.get("openPosition")
    if not isinstance(pos, dict):
        raise MonitorError("NO_OPEN_VIRTUAL_POSITION")
    if pos.get("status") != "OPEN" or not str(pos.get("token", "")).isdigit():
        raise MonitorError("INVALID_VIRTUAL_POSITION")
    return pos


def verified_contract_for_position(position, *, master):
    token = position.get("token")
    if not isinstance(master, dict) or token not in master:
        raise MonitorError("OPTION_CONTRACT_NOT_IN_CURRENT_MASTER")
    verified = master[token]
    for stored, live in (
        ("symbol", "symbol"), ("token", "token"), ("side", "side"),
        ("market", "market"), ("lot_size", "lotSize")
    ):
        if str(position.get(stored)) != str(verified.get(live)):
            raise MonitorError("BROKER_CONTRACT_DOES_NOT_MATCH_VIRTUAL_POSITION")
    if verified.get("exchange") != "NFO" or verified.get("side") not in ("CE", "PE"):
        raise MonitorError("NOT_VERIFIED_NFO_OPTION")
    return verified


def observe_once(db_path, position, verified_contract, quote, *, clock=None):
    """One explicit virtual-only observation; never submit a broker order."""
    if quote.get("contract") != verified_contract:
        raise MonitorError("BROKER_QUOTE_CONTRACT_CHANGED")
    result = monitor_paper(db_path, verified_contract, quote, now=clock)
    if result.get("brokerOrdersSent") != 0 or result.get("canSubmitOrder") is not False:
        raise MonitorError("PAPER_RESULT_NOT_SAFE")
    return result


def run_foreground(args) -> int:
    # Never run this with cron/systemd or without the private human SSH TTY.
    if not (sys.stdin.isatty() and sys.stdout.isatty()):
        raise MonitorError("INTERACTIVE_SSH_TTY_REQUIRED")
    if pwd.getpwuid(os.geteuid()).pw_name != "optionx":
        raise MonitorError("UNPRIVILEGED_OPTIONX_USER_REQUIRED")
    if not exchange_hours(datetime.now(timezone.utc)):
        raise MonitorError("OUTSIDE_NSE_WEEKDAY_TRADING_SESSION")
    pos = read_virtual_position(args.paper_db)
    # Static IP, live order gate, healthy loopback backend and owner auth.
    verify_aws(args.expected_ip)
    print("PAPER_MONITOR_MODE: FOREGROUND_ONLY; no automatic entries or real orders")
    print("PAPER_MONITOR_LIMIT: " + str(args.minutes) + " minutes max; stops when SSH ends")
    print("PAPER_MONITOR_WARNING: Angel LTP lacks independently verified exchange time; "
          "SL/target triggers are illustrative only; no broker protection.")
    print("PAPER_POSITION: " + pos["symbol"] + " qty=" + str(pos["quantity"]))
    import angel_gateway
    from live_v7.angel_marketdata import _get_master, quote_ltp
    from ops.angel_ssh_readonly_pilot import _prompt_credentials

    os.environ["OPTIONX_OWNER_USER_ID"] = OWNER
    os.environ["ANGEL_EGRESS_PUBLIC_IPV4"] = args.expected_ip
    credentials = _prompt_credentials()
    try:
        connected = angel_gateway.connect(OWNER, credentials)
    finally:
        credentials.clear()
    if not connected.get("connected"):
        raise MonitorError("ANGEL_PROFILE_NOT_VERIFIED")
    start = time.monotonic()
    try:
        master, _ = _get_master()
        contract = verified_contract_for_position(pos, master=master)
        while time.monotonic() - start < min(args.minutes * 60, MAX_SESSION_SECONDS):
            now = datetime.now(timezone.utc)
            if not exchange_hours(now):
                raise MonitorError("NSE_TIME_WINDOW_ENDED_HOLIDAYS_NOT_CHECKED")
            current = read_virtual_position(args.paper_db, now=now)
            if current["id"] != pos["id"]:
                raise MonitorError("VIRTUAL_POSITION_CHANGED_OR_CLOSED")
            quote = quote_ltp(OWNER, contract["token"])
            # quote observedAt is server-side request time, NOT exchange-time proof.
            result = observe_once(args.paper_db, current, contract, quote)
            print("PAPER_LTP_OBSERVED: " + result["quoteLtp"]
                  + " virtual_close=" + str(result["paperClosed"])
                  + " trigger=" + result["trigger"], flush=True)
            if result["paperClosed"]:
                print("VIRTUAL_POSITION_CLOSED: paper only, no broker order sent", flush=True)
                return 0
            time.sleep(args.interval)
        print("PAPER_MONITOR_ENDED: session window expired; virtual position stays OPEN")
        print("IMPORTANT: neither SL nor target is monitored after this SSH session.")
        return 0
    except KeyboardInterrupt:
        print("PAPER_MONITOR_STOPPED_BY_OPERATOR: virtual position preserved; no broker orders")
        return 0
    finally:
        angel_gateway.disconnect(OWNER)


def main(argv=None):
    p = argparse.ArgumentParser(description="Short-lived, SSH-only quote polling of an already-open virtual paper position")
    p.add_argument("--expected-ip", required=True)
    p.add_argument("--paper-db", default=str(DB_PATH))
    p.add_argument("--interval", type=int, default=20)
    p.add_argument("--minutes", type=int, default=8)
    args = p.parse_args(argv)
    if not 15 <= args.interval <= 120 or not 1 <= args.minutes <= 12:
        print("PAPER_MONITOR_BLOCKED: UNSAFE_DURATION_OR_POLL_INTERVAL", file=sys.stderr)
        return 1
    try:
        return run_foreground(args)
    except (MonitorError, PaperError, ReadinessError) as exc:
        # These are local, fixed-code diagnostics; no broker token or key.
        safe = str(exc)
        if not (safe.isascii() and safe.replace("_", "").isalnum()):
            safe = "FAIL_CLOSED"
        print("PAPER_MONITOR_BLOCKED: " + safe, file=sys.stderr)
    except Exception:
        # Do not display broker/transport exceptions or HTTP payloads.
        print("PAPER_MONITOR_BLOCKED: BROKER_OR_LOCAL_CHECK_FAILED", file=sys.stderr)
    print("VIRTUAL_POSITION_PRESERVED_UNLESS_JOURNAL_ALREADY_RECORDED_AN_EXIT", file=sys.stderr)
    print("REAL_MONEY_ORDERS_OFF", file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
