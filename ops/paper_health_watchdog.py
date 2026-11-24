"""OptionX permanent, no-credentials, read-only PAPER WATCHDOG (24x7).

It supervises *the health and staleness* of the private virtual ledger,
NOT the broker price feed, brokerage sessions, trade entries or real orders.
No network imports, broker key, live order, strategy execution or credential
persistence. Intended as an unprivileged 24x7 systemd service.
"""
from __future__ import annotations

import argparse
from datetime import datetime, time as clock_time, timezone
import json
import os
from pathlib import Path
import pwd
import signal
import stat
import sys
import time
from zoneinfo import ZoneInfo

from ops.paper_ledger_v1 import DB_PATH
from ops.paper_recovery_audit import integrity_report
from ops.paper_ledger_v1 import status as ledger_status

IST = ZoneInfo("Asia/Kolkata")
HEALTH_PATH = DB_PATH.parent / "watchdog-health.json"
DEFAULT_INTERVAL_SECONDS = 30
MAX_LOCAL_QUOTE_AGE_SECONDS = 120

class WatchdogError(RuntimeError):
    pass


def _age_seconds(observed, now):
    if not isinstance(observed, str):
        return None
    try:
        t = datetime.fromisoformat(observed)
        if t.tzinfo is None or t.utcoffset() is None:
            return None
        age = (now.astimezone(timezone.utc) - t.astimezone(timezone.utc)).total_seconds()
        return int(age) if 0 <= age <= 86400 * 365 else None
    except (TypeError, ValueError, OverflowError):
        return None


def market_clock_session(now):
    if not isinstance(now, datetime) or now.tzinfo is None or now.utcoffset() is None:
        raise WatchdogError("AWARE_CLOCK_REQUIRED")
    local = now.astimezone(IST)
    tm = local.time().replace(tzinfo=None)
    # This is a CLOCK-only approximation. Exchange holidays remain unknown.
    return local.weekday() < 5 and clock_time(9, 15) <= tm < clock_time(15, 30)


def inspect_one(db_path=DB_PATH, *, now=None, audit=None, snapshot=None):
    """Never mutates the virtual trade database or treats a price as a fill."""
    now = now or datetime.now(timezone.utc)
    if not isinstance(now, datetime) or now.tzinfo is None or now.utcoffset() is None:
        raise WatchdogError("AWARE_CLOCK_REQUIRED")
    ok_audit = audit if audit is not None else integrity_report(db_path, strict_ownership=True)
    snap = snapshot if snapshot is not None else ledger_status(db_path, now=now)
    if (ok_audit.get("audit") != "PASS" or
        snap.get("canSubmitOrder") is not False or
        snap.get("liveExecutionEnabled") is not False):
        raise WatchdogError("PRIVATE_PAPER_LEDGER_UNSAFE_OR_CORRUPT")
    pos = snap.get("openPosition")
    session_clock = market_clock_session(now)
    result = {
        "service": "OPTIONX_24H_PAPER_HEALTH_WATCHDOG",
        "observedAtUTC": now.astimezone(timezone.utc).isoformat(),
        "status": "HEALTHY_PAPER_LEDGER",
        "privatePaperDbHealthy": True,
        "marketClockSession": session_clock,
        "exchangeHolidayCalendarVerified": False,
        "openVirtualPosition": isinstance(pos, dict),
        "indicativeQuoteAgeSeconds": None,
        "brokerQuoteFreshnessVerified": False,
        "angelSessionConnected": False,
        "automaticPaperEntryEnabled": False,
        "automaticPaperExitGuaranteed": False,
        "liveMoneyOrdersEnabled": False,
        "brokerOrdersSent": 0,
        "continuousBrokerPriceStreaming": False,
        "warnings": [],
    }
    if pos is not None:
        age = _age_seconds(pos.get("last_observed_utc"), now)
        result["indicativeQuoteAgeSeconds"] = age
        result["status"] = "VIRTUAL_POSITION_UNMONITORED"
        result["warnings"].append("NO_CONTINUOUS_ANGEL_SESSION_OR_EXCHANGE_STOP")
        if age is None:
            result["warnings"].append("VIRTUAL_LTP_AGE_UNKNOWN")
        elif age > MAX_LOCAL_QUOTE_AGE_SECONDS:
            result["warnings"].append("VIRTUAL_LAST_LTP_STALE")
        else:
            result["warnings"].append("RECENT_LOCAL_LTP_IS_NOT_BROKER_STOP_COVERAGE")
    if not session_clock:
        result["warnings"].append("OUTSIDE_APPROXIMATE_NSE_WEEKDAY_SESSION")
    return result


def write_private_health(report, path=HEALTH_PATH):
    """Owner-only atomic replacement, with no partial or world-readable JSON."""
    p = Path(path)
    if p.parent.is_symlink() or not p.parent.is_dir():
        raise WatchdogError("WATCHDOG_PRIVATE_DIR_UNAVAILABLE")
    if p.exists() and p.is_symlink():
        raise WatchdogError("WATCHDOG_OUTPUT_SYMLINK_NOT_ALLOWED")
    if p.parent.stat().st_uid != os.geteuid():
        raise WatchdogError("WATCHDOG_PRIVATE_DIR_NOT_OWNED_BY_SERVICE")
    if stat.S_IMODE(p.parent.stat().st_mode) & 0o077:
        raise WatchdogError("WATCHDOG_PRIVATE_DIR_PERMISSIONS_UNSAFE")
    payload = (json.dumps(report, ensure_ascii=True, separators=(",", ":")) + "\n").encode("utf-8")
    if len(payload) > 8192:
        raise WatchdogError("WATCHDOG_REPORT_TOO_LONG")
    tmp = p.parent / ("." + p.name + "." + str(os.getpid()) + ".tmp")
    if tmp.exists() or tmp.is_symlink():
        raise WatchdogError("WATCHDOG_TEMP_ALREADY_EXISTS")
    fd = os.open(str(tmp), os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0), 0o600)
    try:
        with os.fdopen(fd, "wb") as out:
            out.write(payload)
            out.flush()
            os.fsync(out.fileno())
        os.replace(tmp, p)
    finally:
        if tmp.exists():
            tmp.unlink()
    return p


def run_loop(path=DB_PATH, health=HEALTH_PATH, *, interval=DEFAULT_INTERVAL_SECONDS, once=False):
    if os.name != "posix" or pwd.getpwuid(os.geteuid()).pw_name != "optionx":
        raise WatchdogError("OPTIONX_UNPRIVILEGED_ACCOUNT_REQUIRED")
    if not 10 <= interval <= 300:
        raise WatchdogError("INVALID_WATCHDOG_INTERVAL")
    stopping = False
    def shutdown(*_):
        nonlocal stopping
        stopping = True
    signal.signal(signal.SIGTERM, shutdown)
    signal.signal(signal.SIGINT, shutdown)
    while not stopping:
        try:
            report = inspect_one(path)
        except Exception:
            # Read errors are sanitized, never allow a heartbeat falsely healthy.
            report = {
                "service": "OPTIONX_24H_PAPER_HEALTH_WATCHDOG",
                "observedAtUTC": datetime.now(timezone.utc).isoformat(),
                "status": "BLOCKED_PAPER_HEALTH_UNVERIFIED",
                "privatePaperDbHealthy": False,
                "openVirtualPosition": None,
                "automaticPaperEntryEnabled": False,
                "automaticPaperExitGuaranteed": False,
                "liveMoneyOrdersEnabled": False,
                "brokerOrdersSent": 0,
                "continuousBrokerPriceStreaming": False,
                "warnings": ["PRIVATE_PAPER_DB_READ_FAILED_OR_UNVERIFIED"],
            }
        write_private_health(report, health)
        print("WATCHDOG " + report["status"] +
              " LIVE_ORDERS_OFF BROKER_SESSION_DISABLED", flush=True)
        if once:
            return 0 if report["privatePaperDbHealthy"] else 1
        end = time.monotonic() + interval
        while not stopping and time.monotonic() < end:
            time.sleep(min(1, max(0, end - time.monotonic())))
    return 0


def main(argv=None):
    parser = argparse.ArgumentParser(description="24x7 private paper-health watchdog, NO broker credentials or orders")
    parser.add_argument("--db", default=str(DB_PATH))
    parser.add_argument("--health-file", default=str(HEALTH_PATH))
    parser.add_argument("--interval", type=int, default=DEFAULT_INTERVAL_SECONDS)
    parser.add_argument("--once", action="store_true")
    args = parser.parse_args(argv)
    if not 10 <= args.interval <= 300:
        print("BLOCKED: WATCHDOG_INTERVAL_UNSAFE", file=sys.stderr)
        return 1
    try:
        return run_loop(args.db, args.health_file, interval=args.interval, once=args.once)
    except Exception:
        print("BLOCKED: WATCHDOG_BOOT_OR_RUNTIME_FAILED; REAL_ORDERS_OFF", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
