"""AWS Angel broker lifecycle observer: read-only, fail-closed, durable audit.

Designed to run beside the production HTTP service on AWS. It never reads
broker credentials, sends HTTP orders, or activates the live execution lock.
Only accepts snapshots supplied by a trusted, authenticated server adapter.
SQLite is an AWS-local diagnostic journal, NOT the production authoritative
PostgreSQL ledger required before any real order activation.
"""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
import hashlib
import json
import os
import sqlite3
from typing import Mapping, Any

from live_v7.reconciliation import compare

SCHEMA = """
CREATE TABLE IF NOT EXISTS observations (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  recorded_utc TEXT NOT NULL,
  digest TEXT NOT NULL UNIQUE,
  previous_digest TEXT NOT NULL,
  source_authenticated INTEGER NOT NULL CHECK (source_authenticated IN (0,1)),
  reconciled INTEGER NOT NULL CHECK (reconciled IN (0,1)),
  new_entries_blocked INTEGER NOT NULL CHECK (new_entries_blocked = 1),
  order_count INTEGER NOT NULL CHECK (order_count >= 0),
  position_count INTEGER NOT NULL CHECK (position_count >= 0),
  block_reasons TEXT NOT NULL
);
CREATE TRIGGER IF NOT EXISTS no_observation_update
  BEFORE UPDATE ON observations BEGIN SELECT RAISE(ABORT,'IMMUTABLE_AUDIT'); END;
CREATE TRIGGER IF NOT EXISTS no_observation_delete
  BEFORE DELETE ON observations BEGIN SELECT RAISE(ABORT,'IMMUTABLE_AUDIT'); END;
"""

class ObserverError(ValueError):
    pass


def open_observer(path: str | Path) -> sqlite3.Connection:
    """A dedicated diagnostic file must reside in a persistent, private folder."""
    dest = Path(path)
    if not dest.is_absolute() or dest.is_symlink():
        raise ObserverError("ABSOLUTE_PRIVATE_PATH_REQUIRED")
    if not dest.parent.is_dir():
        raise ObserverError("AUDIT_DIRECTORY_MISSING")
    if dest.exists() and (dest.stat().st_mode & 0o077):
        raise ObserverError("AUDIT_FILE_PERMISSIONS_UNSAFE")
    cn = sqlite3.connect(dest, timeout=8, isolation_level=None)
    cn.execute("PRAGMA journal_mode=WAL")
    cn.execute("PRAGMA synchronous=FULL")
    cn.executescript(SCHEMA)
    os.chmod(dest, 0o600)
    return cn


def observe(conn: sqlite3.Connection, *, snapshot: Mapping[str, Any],
            trusted_source: bool, observed_at: datetime) -> dict[str, Any]:
    """Persist one digest-chained, sanitized broker observation, never an order.

    Broker session and ownership checks must happen outside this function.
    An empty book does not prove the absence of outstanding broker orders.
    If books are unauthenticated, incomplete, or tradebook not fill-verified,
    no new entries are allowed.
    """
    if not isinstance(observed_at, datetime) or observed_at.utcoffset() is None:
        raise ObserverError("AWARE_TIME_REQUIRED")
    if not isinstance(snapshot, Mapping):
        raise ObserverError("SNAPSHOT_REQUIRED")
    books = snapshot.get("books")
    if not isinstance(books, Mapping):
        raise ObserverError("BROKER_BOOKS_MISSING")
    ob, tb, pos = (books.get(k) for k in ("orderbook","tradebook","positions"))
    if not all(isinstance(x, Mapping) for x in (ob,tb,pos)):
        raise ObserverError("ALL_THREE_BOOKS_REQUIRED")
    orders, positions = ob.get("orders"), pos.get("positions")
    if not isinstance(orders, list) or not isinstance(positions, list):
        raise ObserverError("NORMALIZED_BOOKS_REQUIRED")
    if len(orders) > 500 or len(positions) > 500:
        raise ObserverError("TOO_MANY_BROKER_RECORDS")
    remote = compare(
        tracked_orders=[], broker_orders=orders, broker_positions=positions,
        local_positions={}, source_authenticated=trusted_source is True,
        snapshot_time=observed_at, now=observed_at,
    )
    blocks = set(remote.get("blocks") or [])
    # No certified PostgreSQL ledger or verified local exposure is wired yet.
    blocks.add("AUTHORITATIVE_POSTGRES_LEDGER_NOT_CONNECTED")
    blocks.add("LIVE_EXECUTION_WORKER_NOT_CERTIFIED")
    if tb.get("fillsBrokerVerified") is not True or tb.get("reconciliationPending") is not False:
        blocks.add("TRADEBOOK_FILL_NOT_VERIFIED")
    if snapshot.get("allReadsSucceeded") is not True:
        blocks.add("BROKER_BOOK_READ_INCOMPLETE")
    if trusted_source is not True:
        blocks.add("BROKER_SOURCE_NOT_AUTHENTICATED")
    timestamp = observed_at.astimezone(timezone.utc).isoformat()
    reasons = sorted(blocks)
    conn.execute("BEGIN IMMEDIATE")
    try:
        previous = conn.execute(
            "SELECT digest FROM observations ORDER BY id DESC LIMIT 1"
        ).fetchone()
        prior = previous[0] if previous else "0"*64
        # Never persist contract symbols, trade rows, client IDs, tokens or keys.
        content = json.dumps({
            "timestamp":timestamp,"source_authenticated":trusted_source is True,
            "order_count":len(orders),"position_count":len(positions),
            "reconciled":False,"blocks":reasons,
        }, sort_keys=True, separators=(",",":"))
        digest = hashlib.sha256((prior + content).encode("utf8")).hexdigest()
        conn.execute(
            """INSERT INTO observations(
                recorded_utc,digest,previous_digest,source_authenticated,
                reconciled,new_entries_blocked,order_count,position_count,block_reasons
            ) VALUES(?,?,?,?,0,1,?,?,?)""",
            (timestamp,digest,prior,int(trusted_source is True),
             len(orders),len(positions),json.dumps(reasons)),
        )
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    return {
        "mode":"AWS_READ_ONLY_SHADOW_OBSERVER",
        "observationDigest":digest,
        "ordersObserved":len(orders),"positionsObserved":len(positions),
        "blocks":reasons,"newEntriesBlocked":True,
        "canSubmitOrder":False,"canCancelOrder":False,
        "liveOrdersEnabled":False,"productionLedgerCertified":False,
    }


def audit_chain(conn: sqlite3.Connection) -> bool:
    """Detect an interrupted sequence or reordered/missing digest link.

    Each row links to prior digest, but complete content authentication also
    requires independent anchoring and is not claimed by this local check.
    """
    rows = conn.execute(
        "SELECT previous_digest,digest FROM observations ORDER BY id"
    ).fetchall()
    prev = "0"*64
    for prior, digest in rows:
        if prior != prev or not isinstance(digest,str) or len(digest)!=64:
            return False
        prev=digest
    return True
