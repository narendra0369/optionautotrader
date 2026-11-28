"""OptionX V7 DEV ONLY: durable order-intent journal and state machine.

NO broker adapters or outgoing network calls. This is a preparation module only.
It cannot be wired to production until persistence, crash recovery, idempotency,
reconciliation, partial-fill, and owner-authorization tests are completed.

SQLite here is for local developer rehearsal; a Render free/ephemeral disk is
NOT an approved authoritative store for live brokerage order state.
"""
from __future__ import annotations

import sqlite3
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

IST = ZoneInfo("Asia/Kolkata")
STATES = frozenset({
    "PREPARED", "LOCAL_REJECTED", "LOCAL_CANCELLED",
    "AWAITING_BROKER_ACK", "BROKER_REJECTED", "BROKER_ACCEPTED",
    "PARTIALLY_FILLED", "FILLED", "CANCEL_REQUESTED",
    "CANCELLED", "UNKNOWN_BROKER_OUTCOME", "MANUAL_REVIEW",
})
TRANSITIONS = {
    "PREPARED": {"LOCAL_REJECTED", "LOCAL_CANCELLED", "AWAITING_BROKER_ACK"},
    "AWAITING_BROKER_ACK": {"BROKER_REJECTED", "BROKER_ACCEPTED", "PARTIALLY_FILLED", "FILLED", "UNKNOWN_BROKER_OUTCOME"},
    "BROKER_ACCEPTED": {"PARTIALLY_FILLED", "FILLED", "CANCEL_REQUESTED", "UNKNOWN_BROKER_OUTCOME"},
    "PARTIALLY_FILLED": {"FILLED", "CANCEL_REQUESTED", "CANCELLED", "UNKNOWN_BROKER_OUTCOME"},
    "CANCEL_REQUESTED": {"CANCELLED", "PARTIALLY_FILLED", "FILLED", "UNKNOWN_BROKER_OUTCOME"},
    "UNKNOWN_BROKER_OUTCOME": {"MANUAL_REVIEW"},
    "MANUAL_REVIEW": {"BROKER_REJECTED", "BROKER_ACCEPTED", "PARTIALLY_FILLED", "FILLED", "CANCELLED"},
    "LOCAL_REJECTED": set(), "LOCAL_CANCELLED": set(),
    "BROKER_REJECTED": set(), "FILLED": set(), "CANCELLED": set(),
}
SCHEMA = """
CREATE TABLE IF NOT EXISTS intents (
  owner_id TEXT NOT NULL,
  trade_day_ist TEXT NOT NULL,
  intent_id TEXT NOT NULL,
  market TEXT NOT NULL CHECK (market IN ('NIFTY', 'BANKNIFTY', 'BTC')),
  broker TEXT NOT NULL CHECK (broker IN ('Angel', 'Delta')),
  state TEXT NOT NULL CHECK (state IN (
    'PREPARED','LOCAL_REJECTED','LOCAL_CANCELLED',
    'AWAITING_BROKER_ACK','BROKER_REJECTED','BROKER_ACCEPTED',
    'PARTIALLY_FILLED','FILLED','CANCEL_REQUESTED','CANCELLED',
    'UNKNOWN_BROKER_OUTCOME','MANUAL_REVIEW'
  )),
  created_utc TEXT NOT NULL,
  updated_utc TEXT NOT NULL,
  PRIMARY KEY (owner_id, trade_day_ist, intent_id)
);
CREATE TABLE IF NOT EXISTS events (
  event_id TEXT NOT NULL PRIMARY KEY,
  owner_id TEXT NOT NULL,
  trade_day_ist TEXT NOT NULL,
  intent_id TEXT NOT NULL,
  previous_state TEXT,
  next_state TEXT NOT NULL,
  recorded_utc TEXT NOT NULL,
  FOREIGN KEY (owner_id, trade_day_ist, intent_id)
    REFERENCES intents(owner_id, trade_day_ist, intent_id)
);
"""


class JournalError(ValueError):
    pass


def _clock(now: datetime) -> tuple[str, str]:
    if not isinstance(now, datetime) or now.utcoffset() is None:
        raise JournalError("Aware server time required")
    return now.astimezone(IST).date().isoformat(), now.isoformat()


def _identifier(value: str, label: str) -> str:
    if not isinstance(value, str) or not (8 <= len(value) <= 96) or not value.isascii():
        raise JournalError(label + " must be an opaque ASCII identifier")
    if any(not (ch.isalnum() or ch in "_-") for ch in value):
        raise JournalError(label + " contains invalid characters")
    return value


def open_local_journal(path: str | Path) -> sqlite3.Connection:
    """Dev-only SQLite. NOT suitable for an ephemeral cloud execution host."""
    conn = sqlite3.connect(str(path), timeout=15, isolation_level=None)
    conn.execute("PRAGMA foreign_keys=ON")
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=FULL")
    conn.executescript(SCHEMA)
    return conn


def reserve_intent(
    conn: sqlite3.Connection, *,
    owner_id: str, intent_id: str, market: str, broker: str,
    now: datetime,
) -> bool:
    """Atomically reserve one intent; a duplicate returns False, never a retry signal."""
    _identifier(owner_id, "owner_id")
    _identifier(intent_id, "intent_id")
    if (market, broker) not in {
        ("NIFTY", "Angel"), ("BANKNIFTY", "Angel"), ("BTC", "Delta")
    }:
        raise JournalError("Broker/market mismatch")
    trade_day, timestamp = _clock(now)
    conn.execute("BEGIN IMMEDIATE")
    try:
        exists = conn.execute(
            "SELECT 1 FROM intents WHERE owner_id=? AND trade_day_ist=? AND intent_id=?",
            (owner_id, trade_day, intent_id),
        ).fetchone()
        if exists:
            conn.commit()
            return False
        conn.execute(
            "INSERT INTO intents(owner_id,trade_day_ist,intent_id,market,broker,state,created_utc,updated_utc)"
            " VALUES(?,?,?,?,?,?,?,?)",
            (owner_id, trade_day, intent_id, market, broker, "PREPARED", timestamp, timestamp),
        )
        conn.commit()
        return True
    except Exception:
        conn.rollback()
        raise


def transition(
    conn: sqlite3.Connection, *,
    owner_id: str, intent_id: str, trade_day_ist: str,
    event_id: str, target: str, now: datetime,
) -> str:
    """Apply a *recorded* state change. Does NOT cause the broker side effect.

    Any unknown send outcome must enter UNKNOWN_BROKER_OUTCOME and be manually
    reconciled against broker orderbook/tradebook BEFORE a new order is allowed.
    """
    _identifier(owner_id, "owner_id")
    _identifier(intent_id, "intent_id")
    _identifier(event_id, "event_id")
    if target not in STATES:
        raise JournalError("Unknown target state")
    today, timestamp = _clock(now)
    if not isinstance(trade_day_ist, str) or len(trade_day_ist) != 10:
        raise JournalError("Invalid trading date")
    conn.execute("BEGIN IMMEDIATE")
    try:
        if conn.execute("SELECT 1 FROM events WHERE event_id=?", (event_id,)).fetchone():
            raise JournalError("Duplicate event; no replay permitted")
        row = conn.execute(
            "SELECT state FROM intents WHERE owner_id=? AND trade_day_ist=? AND intent_id=?",
            (owner_id, trade_day_ist, intent_id),
        ).fetchone()
        if row is None:
            raise JournalError("Intent reservation missing")
        current = row[0]
        if target not in TRANSITIONS[current]:
            raise JournalError("Illegal lifecycle transition: " + current + " => " + target)
        conn.execute(
            "UPDATE intents SET state=?,updated_utc=? WHERE owner_id=? AND trade_day_ist=? AND intent_id=?",
            (target, timestamp, owner_id, trade_day_ist, intent_id),
        )
        conn.execute(
            "INSERT INTO events(event_id,owner_id,trade_day_ist,intent_id,previous_state,next_state,recorded_utc)"
            " VALUES(?,?,?,?,?,?,?)",
            (event_id, owner_id, trade_day_ist, intent_id, current, target, timestamp),
        )
        conn.commit()
        return target
    except Exception:
        conn.rollback()
        raise


def unresolved_orders(conn: sqlite3.Connection, owner_id: str) -> int:
    """Count broker-facing or uncertain states: they block another entry."""
    _identifier(owner_id, "owner_id")
    return conn.execute(
        "SELECT count(*) FROM intents WHERE owner_id=? AND state IN "
        "('AWAITING_BROKER_ACK','BROKER_ACCEPTED','PARTIALLY_FILLED',"
        "'CANCEL_REQUESTED','UNKNOWN_BROKER_OUTCOME','MANUAL_REVIEW')",
        (owner_id,),
    ).fetchone()[0]
