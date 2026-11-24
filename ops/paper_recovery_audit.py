"""Read-only Paper SQLite integrity/recovery audit, with optional PRIVATE backup.

Never restores, deletes, inserts or changes a paper trade. Does not import any
broker, live order, network, HTTPS client or risk-activation path.
A backed-up journal is NOT equivalent to broker-position reconciliation.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
from pathlib import Path
import json
import os
import sqlite3
import stat
from urllib.parse import quote

from ops.paper_ledger_v1 import DB_PATH, PaperError, status as paper_status

REQUIRED_TABLES = frozenset({"account", "trades"})
REQUIRED_INDEXES = frozenset({"one_open_paper_trade"})
_MAX_BACKUPS = 100


class AuditError(RuntimeError):
    pass


def _validated_db_file(database):
    path = Path(database)
    if path.is_symlink() or not path.exists() or not path.is_file():
        raise AuditError("PAPER_DB_MISSING_OR_UNSAFE")
    if not path.parent.is_dir() or path.parent.is_symlink():
        raise AuditError("PAPER_DIR_MISSING_OR_UNSAFE")
    return path


def _connect_ro(path):
    uri = "file:" + quote(str(path.resolve()), safe="/") + "?mode=ro"
    return sqlite3.connect(uri, uri=True, timeout=10)


def integrity_report(database=DB_PATH, *, now=None, strict_ownership=False):
    """Tests non-mutating integrity and paper-specific state invariants."""
    path = _validated_db_file(database)
    st = path.stat()
    if strict_ownership:
        if st.st_uid != os.geteuid() or (stat.S_IMODE(st.st_mode) & 0o077) != 0:
            raise AuditError("PAPER_DB_NOT_PRIVATE_TO_OWNER")
        directory = path.parent.stat()
        if directory.st_uid != os.geteuid() or (stat.S_IMODE(directory.st_mode) & 0o077) != 0:
            raise AuditError("PAPER_DIRECTORY_NOT_PRIVATE_TO_OWNER")
    with _connect_ro(path) as db:
        quick = db.execute("PRAGMA quick_check").fetchone()
        if quick != ("ok",):
            raise AuditError("SQLITE_INTEGRITY_CHECK_FAILED")
        tables = {r[0] for r in db.execute(
            "SELECT name FROM sqlite_master WHERE type='table'")}
        indexes = {r[0] for r in db.execute(
            "SELECT name FROM sqlite_master WHERE type='index'")}
        if not REQUIRED_TABLES <= tables or not REQUIRED_INDEXES <= indexes:
            raise AuditError("PAPER_DB_SCHEMA_INCOMPLETE")
        count = db.execute("SELECT count(*) FROM trades WHERE status='OPEN'").fetchone()[0]
        if count not in (0, 1):
            raise AuditError("MORE_THAN_ONE_OPEN_PAPER_POSITION")
        malformed = db.execute("""SELECT count(*) FROM trades WHERE
            status NOT IN ('OPEN','CLOSED') OR quantity<=0 OR lots<=0
            OR lot_size<=0 OR quantity != lots * lot_size""").fetchone()[0]
        if malformed:
            raise AuditError("MALFORMED_PAPER_TRADE_ROWS")
        account_count = db.execute("SELECT count(*) FROM account").fetchone()[0]
        if account_count != 1:
            raise AuditError("INVALID_VIRTUAL_ACCOUNT_ROW_COUNT")
    try:
        snap = paper_status(path, now=now)
    except (PaperError, sqlite3.DatabaseError):
        raise AuditError("PAPER_LEDGER_SNAPSHOT_UNREADABLE") from None
    if snap["canSubmitOrder"] is not False or snap["liveExecutionEnabled"] is not False:
        raise AuditError("PAPER_LEDGER_UNSAFE_EXECUTION_FLAG")
    pos = snap["openPosition"]
    warnings = [
        "NO_REAL_BROKER_POSITION_RECONCILIATION",
        "NO_EXCHANGE_TIMESTAMP_VERIFICATION",
        "PAPER_ILLUSTRATIVE_STOPS_NOT_EXECUTABLE",
        "GROSS_PNL_EXCLUDES_TRADING_CHARGES_AND_SLIPPAGE",
    ]
    if pos is not None:
        # Paper quotes do not protect a position between operator sessions.
        warnings.append("OPEN_VIRTUAL_POSITION_REQUIRES_ACTIVE_MANUAL_MONITORING")
    return {
        "audit": "PASS",
        "mode": "READONLY_PAPER_RECOVERY_AUDIT",
        "sqliteQuickCheck": "ok",
        "virtualCapitalINR": snap["initialCapitalINR"],
        "virtualRealizedEquityBeforeChargesINR": snap["realizedEquityBeforeChargesINR"],
        "virtualOpenPositions": count,
        "virtualTradesToday": snap["tradesToday"],
        "maxTradesPerDay": snap["maxTradesPerDay"],
        "virtualIllustrativeLotCap": snap["paperPlan"]["illustrativeLots"],
        "warnings": warnings,
        "brokerOrdersSent": 0,
        "liveOrdersEnabled": False,
    }


def backup_private(database=DB_PATH, *, now=None, strict_ownership=False):
    """Create a consistent SQLite online backup with owner-only permissions.

    No destructive restore or overwrites. Backups are private copies of
    virtual-only journal data; they cannot recover a real exchange position.
    """
    source = _validated_db_file(database)
    integrity_report(source, strict_ownership=strict_ownership)
    backups = source.parent / "backups"
    if backups.is_symlink():
        raise AuditError("BACKUP_DIRECTORY_SYMLINK_NOT_ALLOWED")
    if backups.exists() and not backups.is_dir():
        raise AuditError("BACKUP_DIRECTORY_INVALID")
    backups.mkdir(mode=0o700, exist_ok=True)
    if stat.S_IMODE(backups.stat().st_mode) & 0o077:
        raise AuditError("BACKUP_DIRECTORY_NOT_PRIVATE")
    if len(tuple(backups.glob("optionx-paper-*.sqlite3"))) >= _MAX_BACKUPS:
        raise AuditError("BACKUP_RETENTION_LIMIT_REACHED_MANUAL_CLEANUP_REQUIRED")
    now = now or datetime.now(timezone.utc)
    if now.tzinfo is None:
        raise AuditError("AWARE_BACKUP_TIMESTAMP_REQUIRED")
    label = now.astimezone(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    target = backups / f"optionx-paper-{label}.sqlite3"
    if target.exists() or target.is_symlink():
        raise AuditError("BACKUP_ALREADY_EXISTS")
    temp = backups / f".{target.name}.{os.getpid()}.partial"
    if temp.exists() or temp.is_symlink():
        raise AuditError("TEMP_BACKUP_ALREADY_EXISTS")
    old_mask = os.umask(0o077)
    try:
        with _connect_ro(source) as src:
            with sqlite3.connect(str(temp)) as dest:
                src.backup(dest)
        temp.chmod(0o600)
        with _connect_ro(temp) as b:
            if b.execute("PRAGMA quick_check").fetchone() != ("ok",):
                raise AuditError("BACKUP_INTEGRITY_FAILED")
        temp.rename(target)
        return {"backup": "PASS", "file": str(target),
                "privatePermissions": "0600", "restoreAttempted": False,
                "brokerOrdersSent": 0, "liveOrdersEnabled": False}
    finally:
        os.umask(old_mask)
        if temp.exists():
            temp.unlink()


def main(argv=None):
    p = argparse.ArgumentParser(description="Read-only virtual paper DB integrity audit")
    p.add_argument("--db", default=str(DB_PATH))
    p.add_argument("--backup", action="store_true", help="Opt-in 0600 private backup of virtual-only journal")
    p.add_argument("--strict-owner", action="store_true")
    args = p.parse_args(argv)
    try:
        result = integrity_report(args.db, strict_ownership=args.strict_owner)
        print("PASS: private SQLite quick_check, schema, account and paper position integrity")
        print("VIRTUAL_LEDGER: balance=" + result["virtualRealizedEquityBeforeChargesINR"]
              + " trades_today=" + str(result["virtualTradesToday"])
              + " open_paper_positions=" + str(result["virtualOpenPositions"])
              + " max_virtual_lots=" + str(result["virtualIllustrativeLotCap"]))
        for warning in result["warnings"]:
            print("PENDING: " + warning)
        if args.backup:
            dest = backup_private(args.db, strict_ownership=args.strict_owner)
            print("PASS: PRIVATE_PAPER_BACKUP_CREATED (virtual account only)")
            # Keep absolute local disk path out of public dashboard, but show
            # on the private operator's terminal.
            print("BACKUP_PATH: " + dest["file"])
        print("LIVE_REAL_ORDERS: OFF")
        return 0
    except (AuditError, OSError, sqlite3.DatabaseError, PaperError) as exc:
        safe = str(exc)
        if not safe.replace("_", "").isupper():
            safe = "RECOVERY_AUDIT_FAILED"
        print("BLOCKED: " + safe)
        print("LIVE_REAL_ORDERS: OFF")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
