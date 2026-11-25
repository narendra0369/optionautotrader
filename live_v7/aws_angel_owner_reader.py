"""AWS-only Angel owner verification -> three broker GETs -> local shadow audit.

Run interactively under the dedicated optionx operating-system account on the
AWS Lightsail host. Credentials are read through a TTY without echo and remain
only in process RAM; no environment secrets, argv secrets, or credential files.
This is an AWS read-only *observer*, not a live order-execution worker.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import getpass
import os
import re
import sys
import time
from pathlib import Path

import angel_gateway
from live_v7.angel_books_readonly import read_three_books, AngelBookReadError
from live_v7.aws_shadow_observer import open_observer, observe

DEFAULT_JOURNAL = "/var/lib/optionx-v7/angel-shadow.sqlite3"
MIN_POLL_SECONDS = 60


class OwnerReaderError(ValueError):
    pass


def _config() -> tuple[str, str]:
    owner = os.getenv("OPTIONX_OWNER_USER_ID", "").strip()
    client = os.getenv("ANGEL_ALLOWED_CLIENT_CODE", "").strip().upper()
    if not re.fullmatch(r"[0-9a-fA-F-]{36}", owner):
        raise OwnerReaderError("OPTIONX_OWNER_USER_ID_MISSING_OR_INVALID")
    if not re.fullmatch(r"[A-Z0-9]{4,24}", client):
        raise OwnerReaderError("ANGEL_ALLOWED_CLIENT_CODE_MISSING_OR_INVALID")
    if os.geteuid() == 0:
        raise OwnerReaderError("MUST_NOT_RUN_AS_ROOT")
    if not (sys.stdin.isatty() and sys.stdout.isatty()):
        raise OwnerReaderError("INTERACTIVE_PRIVATE_TERMINAL_REQUIRED")
    return owner, client


def verify_login(owner: str, client: str, *, prompt=getpass.getpass,
                 login=angel_gateway.connect) -> dict:
    """Prompts are not printed to shell history, logs, environment or argv."""
    api_key = prompt("Angel API key (hidden): ").strip()
    pin = prompt("Angel PIN (hidden): ").strip()
    totp = prompt("Angel TOTP 6 digits (hidden): ").strip()
    if not (api_key and pin and re.fullmatch(r"\d{6}", totp)):
        raise OwnerReaderError("INVALID_PRIVATE_LOGIN_INPUT")
    response = login(owner, {
        "apiKey": api_key, "clientCode": client,
        "pin": pin, "totp": totp
    })
    if response.get("connected") is not True or response.get("ownerMatch") is not True:
        raise OwnerReaderError("BROKER_OWNER_PROFILE_NOT_VERIFIED")
    return {"connected": True, "ownerMatched": True, "orderExecutionEnabled": False}


def one_cycle(owner: str, conn, *, fetch_books=read_three_books,
              observe_snapshot=observe, clock=None) -> dict:
    """Reads 3 books within verified RAM session; records sanitized audit.

    Any malformed, unknown or partial response fails the entire cycle.
    No real-order operations are imported in this module.
    """
    now = datetime.now(timezone.utc) if clock is None else clock()
    if not isinstance(now, datetime) or now.utcoffset() is None:
        raise OwnerReaderError("INVALID_SERVER_CLOCK")
    if not angel_gateway._owner_bound(owner):
        raise OwnerReaderError("OWNER_BINDING_LOST")
    if not angel_gateway._clean_session(owner, now.timestamp()):
        raise OwnerReaderError("ANGEL_SESSION_EXPIRED")
    snapshot = fetch_books(owner, now=now)
    if snapshot.get("allReadsSucceeded") is not True:
        raise OwnerReaderError("BROKER_BOOK_READ_INCOMPLETE")
    result = observe_snapshot(conn, snapshot=snapshot, trusted_source=True, observed_at=now)
    if result.get("newEntriesBlocked") is not True or result.get("canSubmitOrder") is not False:
        raise OwnerReaderError("FAIL_CLOSED_INVARIANT_BROKEN")
    return result


def run_cli(argv=None) -> int:
    parser = argparse.ArgumentParser(description="AWS Angel owner-only three-book read-only observer")
    parser.add_argument("--journal", default=DEFAULT_JOURNAL)
    parser.add_argument("--poll-seconds", type=int, default=0,
                        help="0 = one cycle, >=60 = repeated reads in same RAM session")
    args = parser.parse_args(argv)
    if args.poll_seconds and not MIN_POLL_SECONDS <= args.poll_seconds <= 3600:
        parser.error("poll-seconds must be 0 or 60..3600")
    owner = None
    conn = None
    try:
        owner, client = _config()
        verify_login(owner, client)
        conn = open_observer(Path(args.journal))
        print("AWS_ANGEL_PROFILE_VERIFIED: YES", flush=True)
        print("LIVE_ORDERS: OFF | MANUAL_POSITIONS: UNTOUCHED", flush=True)
        while True:
            try:
                result = one_cycle(owner, conn)
            except (AngelBookReadError, OwnerReaderError, OSError, ValueError):
                print("BROKER_READ_FAILED: entries remain BLOCKED; no order sent", flush=True)
                return 2
            print("READ_ONLY_AUDIT_OK: orders=%d positions=%d | entries=BLOCKED | digest=%s" % (
                result["ordersObserved"], result["positionsObserved"],
                result["observationDigest"][:12]), flush=True)
            if args.poll_seconds == 0:
                return 0
            time.sleep(args.poll_seconds)
    except KeyboardInterrupt:
        print("OBSERVER_STOPPED: no orders sent", flush=True)
        return 0
    except (OwnerReaderError, angel_gateway.AuthError, PermissionError, OSError) as exc:
        safe = str(exc)
        if safe not in {
            "OPTIONX_OWNER_USER_ID_MISSING_OR_INVALID",
            "ANGEL_ALLOWED_CLIENT_CODE_MISSING_OR_INVALID",
            "MUST_NOT_RUN_AS_ROOT",
            "INTERACTIVE_PRIVATE_TERMINAL_REQUIRED",
            "INVALID_PRIVATE_LOGIN_INPUT",
            "BROKER_OWNER_PROFILE_NOT_VERIFIED",
            "ABSOLUTE_PRIVATE_PATH_REQUIRED",
            "AUDIT_DIRECTORY_MISSING",
            "AUDIT_FILE_PERMISSIONS_UNSAFE",
        }:
            safe = "OWNER_OR_BROKER_VERIFICATION_FAILED"
        print("BLOCKED: " + safe, flush=True)
        return 2
    finally:
        if conn:
            conn.close()
        if owner:
            angel_gateway.disconnect(owner)


if __name__ == "__main__":
    raise SystemExit(run_cli())
