"""V34 durable SHADOW journal for offline lifecycle simulations only.

This journal is NOT an order-send journal and never proves a live broker outcome.
No network, broker SDK, credentials, or production database access. All entries
are SIMULATED. The API cannot return authorization to send an order.
"""
from __future__ import annotations
import hashlib
import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from uuid import UUID
import re

STATES = {"DRAFT", "SIMULATED_SEND_UNKNOWN", "SIMULATED_ACK", "REVIEW_REQUIRED"}
EVENTS = {
    "DRAFT": {"SIMULATE_UNKNOWN": "SIMULATED_SEND_UNKNOWN",
              "SIMULATE_ACK": "SIMULATED_ACK",
              "HOLD": "REVIEW_REQUIRED"},
    "SIMULATED_SEND_UNKNOWN": {"RECONCILE_REVIEW": "REVIEW_REQUIRED"},
    "SIMULATED_ACK": {"RECONCILE_REVIEW": "REVIEW_REQUIRED"},
    "REVIEW_REQUIRED": {},
}


class ShadowBlocked(ValueError):
    pass


def _owner(value):
    try:
        return str(UUID(value))
    except (TypeError, ValueError, AttributeError):
        raise ShadowBlocked("OWNER_UUID_INVALID") from None


def _key(value):
    if not isinstance(value, str) or not re.fullmatch(r"[A-Za-z0-9_-]{8,96}", value):
        raise ShadowBlocked("IDEMPOTENCY_KEY_INVALID")
    return value


def _time(now):
    if not isinstance(now, datetime) or now.utcoffset() is None:
        raise ShadowBlocked("AWARE_TIME_REQUIRED")
    return now.astimezone(timezone.utc).isoformat()


def _validate_draft(draft):
    if not isinstance(draft, dict):
        raise ShadowBlocked("DRAFT_INVALID")
    expected = {"contract": "NIFTY29DEC2629000CE", "token": "38158",
                "quantity": 65, "side": "SELL", "orderType": "LIMIT",
                "limit": "10.50", "canSubmitOrder": False,
                "submittedOrder": False, "realOrdersEnabled": False}
    for name, value in expected.items():
        if draft.get(name) != value or type(draft.get(name)) is not type(value):
            raise ShadowBlocked("DRAFT_MISMATCH_OR_EXECUTION_FLAG")
    # Never persist credentials or broker client/account identifiers.
    if set(draft) != set(expected):
        raise ShadowBlocked("EXTRA_DRAFT_FIELDS_BLOCKED")
    return json.dumps(draft, sort_keys=True, separators=(",", ":"))


def open_shadow(path):
    """Only caller-provisioned local simulation DB. Never production DB."""
    target = Path(path)
    if str(target) == ":memory:":
        # tests can use in-memory database, not a production connection.
        target_name = ":memory:"
    else:
        if not target.is_absolute() or target.is_symlink():
            raise ShadowBlocked("ABSOLUTE_SHADOW_PATH_REQUIRED")
        if not target.parent.is_dir() or target.parent.is_symlink():
            raise ShadowBlocked("SHADOW_DIRECTORY_INVALID")
        target_name = str(target)
    db = sqlite3.connect(target_name, isolation_level=None, timeout=10)
    db.execute("PRAGMA busy_timeout=10000")
    db.execute("PRAGMA synchronous=FULL")
    db.execute("PRAGMA journal_mode=DELETE")
    db.execute("""CREATE TABLE IF NOT EXISTS shadow_intents (
        owner_digest TEXT NOT NULL,
        idempotency_key TEXT NOT NULL,
        draft_json TEXT NOT NULL,
        status TEXT NOT NULL CHECK(status IN (
          'DRAFT','SIMULATED_SEND_UNKNOWN','SIMULATED_ACK','REVIEW_REQUIRED')),
        PRIMARY KEY(owner_digest, idempotency_key))""")
    db.execute("""CREATE TABLE IF NOT EXISTS shadow_events (
        event_id INTEGER PRIMARY KEY AUTOINCREMENT,
        owner_digest TEXT NOT NULL,
        idempotency_key TEXT NOT NULL,
        event TEXT NOT NULL,
        recorded_utc TEXT NOT NULL)""")
    return db


def stage(db, *, owner_id, idempotency_key, draft, now):
    digest = hashlib.sha256(_owner(owner_id).encode()).hexdigest()
    key = _key(idempotency_key)
    when = _time(now)
    doc = _validate_draft(draft)
    db.execute("BEGIN IMMEDIATE")
    try:
        existing = db.execute(
            "SELECT draft_json,status FROM shadow_intents WHERE owner_digest=? AND idempotency_key=?",
            (digest, key)).fetchone()
        if existing:
            if existing[0] != doc:
                raise ShadowBlocked("IDEMPOTENCY_CONFLICT")
            state = existing[1]
            result = "EXISTING_SHADOW_NO_RESEND"
        else:
            db.execute("INSERT INTO shadow_intents VALUES(?,?,?,?)",
                       (digest, key, doc, "DRAFT"))
            db.execute("INSERT INTO shadow_events(owner_digest,idempotency_key,event,recorded_utc) VALUES(?,?,?,?)",
                       (digest, key, "DRAFT_CREATED", when))
            state = "DRAFT"
            result = "NEW_SHADOW_ONLY"
        db.commit()
    except Exception:
        db.rollback()
        raise
    return {"status": state, "result": result, "canSubmitOrder": False,
            "canRetryBrokerSend": False, "realOrdersEnabled": False}


def transition(db, *, owner_id, idempotency_key, event, now):
    digest = hashlib.sha256(_owner(owner_id).encode()).hexdigest()
    key = _key(idempotency_key)
    when = _time(now)
    db.execute("BEGIN IMMEDIATE")
    try:
        row = db.execute(
            "SELECT status FROM shadow_intents WHERE owner_digest=? AND idempotency_key=?",
            (digest, key)).fetchone()
        if not row:
            raise ShadowBlocked("SHADOW_INTENT_NOT_FOUND")
        nxt = EVENTS.get(row[0], {}).get(event)
        if not nxt:
            raise ShadowBlocked("SHADOW_TRANSITION_NOT_ALLOWED")
        db.execute(
            "UPDATE shadow_intents SET status=? WHERE owner_digest=? AND idempotency_key=?",
            (nxt, digest, key))
        db.execute(
            "INSERT INTO shadow_events(owner_digest,idempotency_key,event,recorded_utc) VALUES(?,?,?,?)",
            (digest, key, event, when))
        db.commit()
    except Exception:
        db.rollback()
        raise
    return {"status": nxt, "canSubmitOrder": False,
            "canRetryBrokerSend": False, "realOrdersEnabled": False}


def recover(db, *, owner_id, idempotency_key):
    digest = hashlib.sha256(_owner(owner_id).encode()).hexdigest()
    key = _key(idempotency_key)
    row = db.execute(
        "SELECT status FROM shadow_intents WHERE owner_digest=? AND idempotency_key=?",
        (digest, key)).fetchone()
    if row is None:
        raise ShadowBlocked("SHADOW_INTENT_NOT_FOUND")
    return {"status": row[0], "requiresBrokerIndependentReconciliation": True,
            "canSubmitOrder": False, "canRetryBrokerSend": False,
            "canCancelBrokerOrder": False, "realOrdersEnabled": False}
