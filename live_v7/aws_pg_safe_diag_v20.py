"""OptionX V20 staged safe diagnostics for AWS Angel+Supabase reconciliation.

Owner terminal only. PostgreSQL credentials are entered as a hidden password,
not as URI, avoiding percent-encoding. TLS is verify-full with a pinned local
Supabase CA supplied by an already verified AWS administrator.

IMPORTANT: prompts happen BEFORE the last broker snapshot is collected; this
avoids incorrectly rejecting authenticated snapshots as stale while the user
types the database password.

NO broker order/cancel/stop routes, no database mutations. Live remains OFF.
"""
from __future__ import annotations

from datetime import datetime, timezone
import getpass
import os
from pathlib import Path
import sys

import angel_gateway
from live_v7.aws_angel_owner_reader import _config, verify_login
from live_v7.angel_books_readonly import read_three_books
from live_v7.aws_pg_recovery_v19 import read_recovery

PG_HOST = "aws-1-ap-southeast-1.pooler.supabase.com"
PG_USER = "postgres.yghijfzwsvmzaffllszl"
PG_CERT = "/etc/optionx-v7/supabase-ca.crt"


class DiagnosticError(ValueError):
    pass


def connect_readonly(*, prompt=getpass.getpass, driver=None, ca_path=PG_CERT):
    """Use separate db password, never interpolate secrets into URL or argv."""
    if os.geteuid() == 0 or not (sys.stdin.isatty() and sys.stdout.isatty()):
        raise DiagnosticError("PRIVATE_OPTIONX_TTY_REQUIRED")
    path = Path(ca_path)
    if not path.is_file() or not os.access(path, os.R_OK):
        raise DiagnosticError("SUPABASE_CA_NOT_READABLE")
    if driver is None:
        import psycopg
        driver = psycopg
    password = prompt("Supabase DB password (hidden): ")
    if not isinstance(password, str) or not password:
        raise DiagnosticError("SUPABASE_PASSWORD_MISSING")
    try:
        db = driver.connect(
            host=PG_HOST, port=5432, dbname="postgres", user=PG_USER,
            password=password, sslmode="verify-full",
            sslrootcert=str(path), connect_timeout=10,
            autocommit=False, options="-c default_transaction_read_only=on",
        )
    finally:
        password = None
    if getattr(db, "autocommit", True) is not False:
        db.close()
        raise DiagnosticError("POSTGRES_TRANSACTION_MODE_INVALID")
    return db


def stage_name(exc: BaseException, stage: str) -> str:
    """Allowlisted classifications only; never leak credential/error text."""
    if isinstance(exc, DiagnosticError):
        return str(exc)
    if stage == "PG_CONNECT":
        # No DB driver error printed: SQL errors sometimes echo private DSNs.
        sqlstate = getattr(exc, "sqlstate", None)
        if sqlstate in ("28P01", "28000"):
            return "SUPABASE_AUTH_REJECTED"
        if sqlstate == "3D000":
            return "SUPABASE_DB_NOT_FOUND"
        return "SUPABASE_TLS_OR_CONNECTION_FAILED"
    if stage == "OWNER_CONFIG":
        return "OWNER_TTY_OR_ENV_INVALID"
    if stage == "ANGEL_LOGIN":
        return "ANGEL_AUTH_OR_OWNER_VERIFICATION_FAILED"
    if stage == "BROKER_BOOKS":
        return "ANGEL_BOOK_READ_FAILED"
    if stage == "RECONCILE":
        return "LEDGER_RECONCILIATION_BLOCKED"
    return "UNKNOWN_DIAGNOSTIC_STAGE"


def run() -> int:
    owner = None
    db = None
    stage = "OWNER_CONFIG"
    try:
        owner, client = _config()
        print("OWNER_CONFIG: PASS", flush=True)
        stage = "PG_CONNECT"
        db = connect_readonly()
        print("SUPABASE_TLS_POSTGRES: PASS", flush=True)

        stage = "ANGEL_LOGIN"
        verify_login(owner, client)
        print("ANGEL_OWNER_LOGIN: PASS", flush=True)

        stage = "BROKER_BOOKS"
        # Capture the clock close to the actual broker GET, not before a prompt.
        snapshot = read_three_books(owner)
        observed_at = datetime.now(timezone.utc)
        print("ANGEL_THREE_BOOK_READ: PASS", flush=True)

        stage = "RECONCILE"
        result = read_recovery(
            db, verified_owner_id=owner, owner_authenticated=True,
            broker_authenticated=True, snapshot=snapshot,
            snapshot_at=observed_at, now=datetime.now(timezone.utc),
        )
        print("SUPABASE_LEDGER_READ: PASS", flush=True)
        print("BROKER_ORDERS:", result["brokerOrderCount"])
        print("MANUAL_OR_UNTRACKED_ORDERS:", result["manualOrUntrackedOrderCount"])
        print("POSITIONS_WITH_EXPOSURE:", result["positionsWithExposure"])
        print("BLOCKED_REASONS:", ",".join(result["blockedReasons"]))
        return 0
    except Exception as exc:
        print("BLOCKED_STAGE:", stage, flush=True)
        print("SAFE_REASON:", stage_name(exc, stage), flush=True)
        return 2
    finally:
        print("REAL_ORDERS: OFF | MANUAL_POSITIONS: UNTOUCHED", flush=True)
        if db is not None:
            try:
                db.close()
            except Exception:
                pass
        if owner is not None:
            try:
                angel_gateway.disconnect(owner)
            except Exception:
                pass


if __name__ == "__main__":
    raise SystemExit(run())
