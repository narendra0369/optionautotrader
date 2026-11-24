"""V8 local durable lifecycle rehearsal; offline only, no broker network.

The SQLite file is for synthetic/dev test scenarios, never an authoritative
live broker ledger or Render ephemeral disk. A pending send state is recorded
BEFORE a fake network decision and always blocks automatic retry.
"""
from __future__ import annotations

from datetime import datetime, timezone
import re
import sqlite3

SCHEMA = """
CREATE TABLE IF NOT EXISTS orders (
 owner_id TEXT NOT NULL,
 intent_id TEXT NOT NULL,
 symbol TEXT NOT NULL,
 contract_token TEXT NOT NULL,
 planned_qty INTEGER NOT NULL CHECK(planned_qty>0),
 lifecycle TEXT NOT NULL,
 broker_order_id TEXT,
 observed_fill INTEGER NOT NULL DEFAULT 0,
 observed_exit INTEGER NOT NULL DEFAULT 0,
 protective_order_id TEXT,
 protective_qty INTEGER NOT NULL DEFAULT 0,
 updated_at TEXT NOT NULL,
 PRIMARY KEY(owner_id,intent_id)
);
CREATE UNIQUE INDEX IF NOT EXISTS broker_order_unique ON orders(broker_order_id)
 WHERE broker_order_id IS NOT NULL;
CREATE UNIQUE INDEX IF NOT EXISTS stop_order_unique ON orders(protective_order_id)
 WHERE protective_order_id IS NOT NULL;
CREATE TABLE IF NOT EXISTS events (
 event_id TEXT PRIMARY KEY,
 owner_id TEXT NOT NULL,
 intent_id TEXT NOT NULL,
 kind TEXT NOT NULL,
 asof TEXT NOT NULL,
 FOREIGN KEY(owner_id,intent_id) REFERENCES orders(owner_id,intent_id)
);
"""

STATES = frozenset({"PREPARED", "ACK_UNKNOWN", "BROKER_OPEN",
                    "PARTIALLY_FILLED", "FILLED", "REJECTED",
                    "CANCELLED", "MANUAL_REVIEW"})


class ShadowJournalError(ValueError):
    pass


def clock(t):
    if not isinstance(t, datetime) or t.tzinfo is None or t.utcoffset() is None:
        raise ShadowJournalError("TZ_AWARE_SERVER_CLOCK_REQUIRED")
    return t.astimezone(timezone.utc).isoformat()


def key(s, label):
    if not isinstance(s, str) or not re.fullmatch(r"[A-Za-z0-9_-]{8,96}", s):
        raise ShadowJournalError("INVALID_" + label)
    return s


def open_dev_db(filename):
    """Local DEV journal with full SQLite durability; caller owns its file."""
    db = sqlite3.connect(str(filename), timeout=10, isolation_level=None)
    db.execute("PRAGMA foreign_keys=ON")
    db.execute("PRAGMA busy_timeout=10000")
    db.execute("PRAGMA journal_mode=WAL")
    db.execute("PRAGMA synchronous=FULL")
    db.executescript(SCHEMA)
    return db


def _transaction(db, work):
    db.execute("BEGIN IMMEDIATE")
    try:
        value=work()
        db.commit()
        return value
    except Exception:
        db.rollback()
        raise


def reserve(db, *, owner, intent, symbol, token, quantity, now):
    """Idempotent append-only intent reservation; duplicates never resubmit."""
    key(owner,"OWNER"); key(intent,"INTENT")
    if not isinstance(symbol,str) or not re.fullmatch(r"[A-Z0-9.-]{6,72}",symbol):
        raise ShadowJournalError("INVALID_SYMBOL")
    if not isinstance(token,str) or not re.fullmatch(r"\d{2,16}",token):
        raise ShadowJournalError("INVALID_TOKEN")
    if type(quantity) is not int or not (0<quantity<=100000):
        raise ShadowJournalError("INVALID_QUANTITY")
    stamp=clock(now)
    def work():
        if db.execute("SELECT 1 FROM orders WHERE owner_id=? AND intent_id=?",(owner,intent)).fetchone():
            return False
        db.execute("INSERT INTO orders(owner_id,intent_id,symbol,contract_token,planned_qty,lifecycle,updated_at)"
                   " VALUES(?,?,?,?,?,'PREPARED',?)",(owner,intent,symbol,token,quantity,stamp))
        return True
    return _transaction(db,work)


def mark_synthetic_send_unknown(db, *, owner, intent, event_id, now):
    """Persist UNKNOWN *before* any mock send; never auto-retry after crash."""
    key(event_id,"EVENT"); stamp=clock(now)
    def work():
        row=db.execute("SELECT lifecycle FROM orders WHERE owner_id=? AND intent_id=?",(owner,intent)).fetchone()
        if row != ("PREPARED",):
            raise ShadowJournalError("DUPLICATE_OR_UNKNOWN_ENTRY_BLOCKED")
        db.execute("UPDATE orders SET lifecycle='ACK_UNKNOWN',updated_at=? WHERE owner_id=? AND intent_id=?",
                   (stamp,owner,intent))
        db.execute("INSERT INTO events VALUES(?,?,?,?,?)",(event_id,owner,intent,"SYNTHETIC_SEND_UNKNOWN",stamp))
        return "ACK_UNKNOWN"
    return _transaction(db,work)


def observe_entry(db, *, owner, intent, event_id, broker_id, broker_status,
                  cumulative_filled, snapshot_authenticated, asof, now, identity_linked):
    """Ingest simulated independently normalized broker entry observations.

    'identity_linked' means a trusted orderbook+tradebook match to this intent,
    not simply matching a user supplied symbol. Source is injected/test only.
    """
    key(event_id,"EVENT"); key(broker_id,"BROKER_ORDER_ID")
    stamp=clock(now); observed=clock(asof)
    seconds=(now-asof).total_seconds()
    if (snapshot_authenticated is not True or identity_linked is not True
            or not 0<=seconds<=10):
        raise ShadowJournalError("AUTHENTIC_FRESH_BROKER_EVIDENCE_REQUIRED")
    if broker_status not in ("OPEN","PARTIAL","COMPLETE","REJECTED","CANCELLED"):
        raise ShadowJournalError("UNKNOWN_BROKER_STATE")
    if type(cumulative_filled) is not int or cumulative_filled<0:
        raise ShadowJournalError("INVALID_FILL")
    def work():
        row=db.execute("SELECT lifecycle,broker_order_id,planned_qty,observed_fill FROM orders "
                       "WHERE owner_id=? AND intent_id=?",(owner,intent)).fetchone()
        if not row or row[0] not in ("ACK_UNKNOWN","BROKER_OPEN","PARTIALLY_FILLED","FILLED"):
            raise ShadowJournalError("INVALID_STATE_FOR_BROKER_OBSERVATION")
        state, prev_id,qty,prev_fill=row
        if prev_id is not None and prev_id!=broker_id:
            raise ShadowJournalError("BROKER_ORDER_ID_CHANGED")
        if not prev_id and state!="ACK_UNKNOWN":
            raise ShadowJournalError("ORDER_ID_UNKNOWN")
        if not prev_id and db.execute("SELECT 1 FROM orders WHERE broker_order_id=?",(broker_id,)).fetchone():
            raise ShadowJournalError("BROKER_ORDER_REUSED")
        if not prev_fill<=cumulative_filled<=qty:
            raise ShadowJournalError("REGRESSING_OR_OVERSIZE_FILL")
        if (broker_status=="COMPLETE" and cumulative_filled!=qty) or (
            broker_status=="REJECTED" and cumulative_filled!=0):
            raise ShadowJournalError("CONFLICTING_BROKER_TERMINAL_STATE")
        if broker_status=="OPEN" and cumulative_filled:
            raise ShadowJournalError("OPEN_WITH_PARTIAL_FILL_NEEDS_RECONCILIATION")
        if broker_status=="PARTIAL" and not 0<cumulative_filled<qty:
            raise ShadowJournalError("INVALID_PARTIAL_FILL")
        if broker_status=="CANCELLED" and cumulative_filled>0:
            # Exchanges may cancel unfilled balance after a partial fill,
            # but a final cancel needs a separate position reconciliation.
            next_state="MANUAL_REVIEW"
        else:
            next_state={"OPEN":"BROKER_OPEN","PARTIAL":"PARTIALLY_FILLED",
                        "COMPLETE":"FILLED","REJECTED":"REJECTED",
                        "CANCELLED":"CANCELLED"}[broker_status]
        if state=="FILLED" and (next_state!="FILLED" or prev_fill!=cumulative_filled):
            raise ShadowJournalError("TERMINAL_STATE_REGRESSION")
        db.execute("UPDATE orders SET lifecycle=?,broker_order_id=?,observed_fill=?,updated_at=? "
                   "WHERE owner_id=? AND intent_id=?",
                   (next_state,broker_id,cumulative_filled,stamp,owner,intent))
        db.execute("INSERT INTO events VALUES(?,?,?,?,?)",
                   (event_id,owner,intent,"BROKER_"+broker_status,observed))
        return next_state
    return _transaction(db,work)


def observe_protection(db, *, owner, intent, event_id, stop_order_id,
                       protected_qty, verified_stop_orderbook,
                       snapshot_authenticated, asof, now):
    """Record mock broker-confirmed protective order; not a real SL placement."""
    key(event_id,"EVENT"); key(stop_order_id,"STOP_ORDER_ID")
    stamp=clock(now)
    seconds=(now-asof).total_seconds() if isinstance(asof,datetime) and asof.utcoffset() is not None else 999
    if (verified_stop_orderbook is not True or snapshot_authenticated is not True
            or not 0<=seconds<=10):
        raise ShadowJournalError("STOP_BROKER_ACK_NOT_VERIFIED")
    if type(protected_qty) is not int or protected_qty<=0:
        raise ShadowJournalError("INVALID_PROTECTED_QTY")
    def work():
        row=db.execute("SELECT observed_fill,observed_exit,protective_order_id,planned_qty "
                       "FROM orders WHERE owner_id=? AND intent_id=?",(owner,intent)).fetchone()
        if row is None:
            raise ShadowJournalError("ORDER_NOT_FOUND")
        filled,exited,old_stop,planned=row
        net=filled-exited
        if net<=0 or protected_qty!=net or old_stop is not None:
            raise ShadowJournalError("PROTECTIVE_QTY_OR_EXISTING_ORDER_MISMATCH")
        db.execute("UPDATE orders SET protective_order_id=?,protective_qty=?,updated_at=? "
                   "WHERE owner_id=? AND intent_id=?",
                   (stop_order_id,protected_qty,stamp,owner,intent))
        db.execute("INSERT INTO events VALUES(?,?,?,?,?)",
                   (event_id,owner,intent,"SIMULATED_STOP_ACK",stamp))
        return protected_qty
    return _transaction(db,work)


def record_exit(db, *, owner, intent, event_id, cumulative_exit,
                broker_tradebook_verified, asof, now):
    """Cumulative simulated verified SELL trades; orphan stop still blocks."""
    key(event_id,"EVENT"); stamp=clock(now)
    secs=(now-asof).total_seconds() if isinstance(asof,datetime) and asof.utcoffset() is not None else 999
    if broker_tradebook_verified is not True or not 0<=secs<=10:
        raise ShadowJournalError("EXIT_TRADEBOOK_UNVERIFIED")
    if type(cumulative_exit) is not int:
        raise ShadowJournalError("INVALID_EXIT_QTY")
    def work():
        row=db.execute("SELECT observed_fill,observed_exit FROM orders WHERE owner_id=? AND intent_id=?",
                       (owner,intent)).fetchone()
        if not row:
            raise ShadowJournalError("ORDER_NOT_FOUND")
        filled,previous=row
        if not previous<cumulative_exit<=filled:
            raise ShadowJournalError("EXIT_EXCEEDS_HOLDINGS_OR_DUPLICATE")
        db.execute("UPDATE orders SET observed_exit=?,updated_at=? WHERE owner_id=? AND intent_id=?",
                   (cumulative_exit,stamp,owner,intent))
        db.execute("INSERT INTO events VALUES(?,?,?,?,?)",
                   (event_id,owner,intent,"SIMULATED_EXIT_FILL",stamp))
        return filled-cumulative_exit
    return _transaction(db,work)


def snapshot(db, *, owner, intent):
    row=db.execute("SELECT symbol,contract_token,planned_qty,lifecycle,broker_order_id,"
                   "observed_fill,observed_exit,protective_order_id,protective_qty "
                   "FROM orders WHERE owner_id=? AND intent_id=?",(owner,intent)).fetchone()
    if row is None:
        raise ShadowJournalError("ORDER_NOT_FOUND")
    keys=("symbol","token","planned_qty","lifecycle","broker_order_id",
          "observed_fill","observed_exit","protective_order_id","protective_qty")
    out=dict(zip(keys,row))
    out["net_open"]=out["observed_fill"]-out["observed_exit"]
    out["protective_gap"]=max(0,out["net_open"]-out["protective_qty"])
    out["manual_review_required"]=bool(out["lifecycle"] in ("ACK_UNKNOWN","MANUAL_REVIEW")
        or out["protective_gap"] or (out["net_open"]==0 and out["protective_order_id"] is not None))
    out["canSubmitOrder"]=False
    out["liveExecutionEnabled"]=False
    return out
