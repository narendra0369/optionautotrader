"""OptionX V18 — durable AWS-local execution lifecycle REHEARSAL.

Not a production database, no broker network functions and no orders. SQLite
is restricted to persistent AWS-local development verification. The live gate
in angel_execution_transport remains physically locked.

Design: owner-scoped entry reservation, maximum 2 auto entries per IST day,
write-before-send UNKNOWN barrier, monotonic broker fill quantities, independent
broker-observed STOPLOSS_LIMIT coverage, manual position collision blocking,
restart recovery requiring fresh authenticated broker data, append-only events.

Broker states are externally normalized by a separately trusted adapter. Never
trust raw browser JSON as broker evidence.
"""
from __future__ import annotations

from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo
import os
import re
import sqlite3
from typing import Any, Mapping

IST = ZoneInfo("Asia/Kolkata")
SCHEMA = """
CREATE TABLE IF NOT EXISTS owned_entries(
 owner_id TEXT NOT NULL, day_ist TEXT NOT NULL, intent_key TEXT NOT NULL,
 symbol TEXT NOT NULL, instrument_token TEXT NOT NULL, requested_qty INTEGER NOT NULL CHECK(requested_qty>0),
 broker_order_id TEXT, filled_qty INTEGER NOT NULL DEFAULT 0 CHECK(filled_qty>=0),
 state TEXT NOT NULL CHECK(state IN (
 'RESERVED','SEND_UNCERTAIN','BROKER_ACCEPTED','PARTIALLY_FILLED',
 'FILLED','BROKER_REJECTED','CLOSED','MANUAL_REVIEW')),
 stop_order_id TEXT, confirmed_stop_qty INTEGER NOT NULL DEFAULT 0 CHECK(confirmed_stop_qty>=0),
 updated_utc TEXT NOT NULL,
 PRIMARY KEY(owner_id,day_ist,intent_key),
 CHECK(filled_qty<=requested_qty),
 CHECK(confirmed_stop_qty<=filled_qty)
);
CREATE UNIQUE INDEX IF NOT EXISTS owned_broker_id_unique
ON owned_entries(owner_id,broker_order_id) WHERE broker_order_id IS NOT NULL;
CREATE TABLE IF NOT EXISTS lifecycle_events (
 id INTEGER PRIMARY KEY AUTOINCREMENT, owner_id TEXT NOT NULL,
 day_ist TEXT NOT NULL, intent_key TEXT NOT NULL,
 event TEXT NOT NULL, at_utc TEXT NOT NULL,
 FOREIGN KEY(owner_id,day_ist,intent_key)
 REFERENCES owned_entries(owner_id,day_ist,intent_key)
);
CREATE TRIGGER IF NOT EXISTS lifecycle_event_no_update
 BEFORE UPDATE ON lifecycle_events BEGIN SELECT RAISE(ABORT,'APPEND_ONLY'); END;
CREATE TRIGGER IF NOT EXISTS lifecycle_event_no_delete
 BEFORE DELETE ON lifecycle_events BEGIN SELECT RAISE(ABORT,'APPEND_ONLY'); END;
"""

class LifecycleError(ValueError):
    pass


def _clock(now: datetime) -> tuple[str,str]:
    if not isinstance(now,datetime) or now.utcoffset() is None:
        raise LifecycleError("TRUSTED_AWARE_CLOCK_REQUIRED")
    return now.astimezone(IST).date().isoformat(),now.isoformat()


def _owner(value: str) -> str:
    if not isinstance(value,str) or not re.fullmatch(r"[a-fA-F0-9-]{36}",value):
        raise LifecycleError("VERIFIED_OWNER_UUID_REQUIRED")
    return value.lower()


def _key(value: str) -> str:
    if not isinstance(value,str) or not re.fullmatch(r"[A-Za-z0-9_-]{8,96}",value):
        raise LifecycleError("IDEMPOTENCY_KEY_INVALID")
    return value


def open_rehearsal(path: str | Path) -> sqlite3.Connection:
    p=Path(path)
    if not p.is_absolute() or p.is_symlink() or not p.parent.is_dir():
        raise LifecycleError("PERSISTENT_PRIVATE_PATH_REQUIRED")
    if p.exists() and (p.stat().st_mode & 0o077):
        raise LifecycleError("LEDGER_PERMISSIONS_UNSAFE")
    c=sqlite3.connect(p,timeout=15,isolation_level=None)
    c.execute("PRAGMA foreign_keys=ON")
    c.execute("PRAGMA synchronous=FULL")
    c.execute("PRAGMA journal_mode=WAL")
    c.executescript(SCHEMA)
    os.chmod(p,0o600)
    return c


def _event(c,owner,day,key,event,ts):
    c.execute("INSERT INTO lifecycle_events(owner_id,day_ist,intent_key,event,at_utc) VALUES(?,?,?,?,?)",
              (owner,day,key,event,ts))


def reserve(c, *, verified_owner_id:str, owner_authenticated:bool,
            intent_key:str,symbol:str,instrument_token:str,quantity:int,
            now:datetime) -> dict:
    """Reserve at most two auto entries per IST day; even rejected ones count.

    Caller must have separately established owner identity and verified risk
    budget, contract master, quote freshness and account manual exposure.
    This function only records an intent; always forbids sending.
    """
    if owner_authenticated is not True:
        raise LifecycleError("OWNER_AUTH_REQUIRED")
    owner=_owner(verified_owner_id); key=_key(intent_key); day,ts=_clock(now)
    if (not isinstance(symbol,str) or not re.fullmatch(r"(NIFTY|BANKNIFTY)[A-Z0-9]{6,68}(CE|PE)",symbol)):
        raise LifecycleError("INDEX_OPTION_CONTRACT_REQUIRED")
    if not isinstance(instrument_token,str) or not re.fullmatch(r"[0-9]{1,20}",instrument_token):
        raise LifecycleError("CONTRACT_TOKEN_INVALID")
    if type(quantity) is not int or quantity <= 0:
        raise LifecycleError("QUANTITY_INVALID")
    c.execute("BEGIN IMMEDIATE")
    try:
        exists=c.execute("SELECT state FROM owned_entries WHERE owner_id=? AND day_ist=? AND intent_key=?",
                          (owner,day,key)).fetchone()
        if exists:
            c.commit()
            return {"reserved":False,"duplicate":True,"newEntriesBlocked":True,"canSubmitOrder":False}
        number=c.execute("SELECT count(*) FROM owned_entries WHERE owner_id=? AND day_ist=?",
                         (owner,day)).fetchone()[0]
        if number>=2:
            raise LifecycleError("TWO_AUTO_ENTRIES_PER_DAY_REACHED")
        uncertain=c.execute("SELECT 1 FROM owned_entries WHERE owner_id=? AND state NOT IN ('BROKER_REJECTED','CLOSED') LIMIT 1",
                             (owner,)).fetchone()
        if uncertain:
            raise LifecycleError("PRIOR_ENTRY_REQUIRES_RECONCILIATION")
        c.execute("""INSERT INTO owned_entries(owner_id,day_ist,intent_key,symbol,instrument_token,
                    requested_qty,state,updated_utc) VALUES(?,?,?,?,?,?,'RESERVED',?)""",
                  (owner,day,key,symbol,instrument_token,quantity,ts))
        _event(c,owner,day,key,"RESERVED",ts)
        c.commit()
    except Exception:
        c.rollback()
        raise
    return {"reserved":True,"duplicate":False,"dailyAutoEntries":number+1,
            "newEntriesBlocked":True,"canSubmitOrder":False}


def before_possible_send(c, *, verified_owner_id:str,intent_key:str,day_ist:str,now:datetime):
    """Durable write-ahead barrier: restart must NEVER blindly retry a send.

    V18 has no send transport. Transition simulates what the audited worker
    must persist BEFORE external network side effect.
    """
    owner=_owner(verified_owner_id);key=_key(intent_key);_,ts=_clock(now)
    c.execute("BEGIN IMMEDIATE")
    try:
        changed=c.execute("""UPDATE owned_entries SET state='SEND_UNCERTAIN',updated_utc=?
           WHERE owner_id=? AND day_ist=? AND intent_key=? AND state='RESERVED'""",
                          (ts,owner,day_ist,key)).rowcount
        if changed!=1:
            raise LifecycleError("SEND_ALREADY_PREPARED_OR_NOT_FOUND")
        _event(c,owner,day_ist,key,"SEND_UNCERTAIN",ts)
        c.commit()
    except Exception:
        c.rollback()
        raise
    return {"state":"SEND_UNCERTAIN","networkRequestMade":False,"canSubmitOrder":False}


def broker_fill_observed(c, *,verified_owner_id:str,intent_key:str,day_ist:str,
                         broker_order_id:str,filled_quantity:int,status:str,
                         source_authenticated:bool,now:datetime):
    """Record external broker evidence, never infer a fill from HTTP 200."""
    if source_authenticated is not True:
        raise LifecycleError("BROKER_EVIDENCE_NOT_AUTHENTICATED")
    owner=_owner(verified_owner_id);key=_key(intent_key);_,ts=_clock(now)
    if not isinstance(broker_order_id,str) or not re.fullmatch(r"[A-Za-z0-9_-]{4,96}",broker_order_id):
        raise LifecycleError("BROKER_ORDER_ID_REQUIRED")
    if type(filled_quantity) is not int or filled_quantity<0:
        raise LifecycleError("INVALID_FILLED_QUANTITY")
    states={"OPEN":"BROKER_ACCEPTED","PARTIALLY_FILLED":"PARTIALLY_FILLED",
            "COMPLETE":"FILLED","REJECTED":"BROKER_REJECTED"}
    if status not in states:
        raise LifecycleError("UNKNOWN_BROKER_STATUS_REQUIRES_REVIEW")
    c.execute("BEGIN IMMEDIATE")
    try:
        row=c.execute("""SELECT state,requested_qty,filled_qty,broker_order_id
             FROM owned_entries WHERE owner_id=? AND day_ist=? AND intent_key=?""",
             (owner,day_ist,key)).fetchone()
        if not row or row[0] not in ("SEND_UNCERTAIN","BROKER_ACCEPTED","PARTIALLY_FILLED","FILLED"):
            raise LifecycleError("INTENT_NOT_ELIGIBLE_FOR_BROKER_EVIDENCE")
        state,qty,prior,old_id=row
        if (old_id is not None and old_id!=broker_order_id) or filled_quantity<prior or filled_quantity>qty:
            raise LifecycleError("BROKER_ID_OR_FILL_REGRESSION")
        if status=="COMPLETE" and filled_quantity!=qty:
            raise LifecycleError("COMPLETE_QUANTITY_MISMATCH")
        if status=="REJECTED" and filled_quantity!=0:
            raise LifecycleError("REJECTED_WITH_FILL")
        if prior>0 and status=="REJECTED":
            raise LifecycleError("FILLED_THEN_REJECTED_INVALID")
        if state=="FILLED" and status!="COMPLETE":
            raise LifecycleError("FILL_FINALITY_REGRESSION")
        if status=="OPEN" and filled_quantity:
            raise LifecycleError("OPEN_WITH_PARTIAL_FILL")
        next_state=states[status]
        c.execute("""UPDATE owned_entries SET state=?,broker_order_id=?,filled_qty=?,
                   updated_utc=? WHERE owner_id=? AND day_ist=? AND intent_key=?""",
                  (next_state,broker_order_id,filled_quantity,ts,owner,day_ist,key))
        _event(c,owner,day_ist,key,"BROKER_"+next_state,ts)
        c.commit()
    except Exception:
        c.rollback()
        raise
    return {"brokerState":next_state,"filledQuantity":filled_quantity,
            "requiresStopVerification":filled_quantity>0,
            "newEntriesBlocked":True,"canSubmitOrder":False}


def confirm_protection(c, *,verified_owner_id:str,intent_key:str,day_ist:str,
                       broker_snapshot:Mapping[str,Any],source_authenticated:bool,
                       now:datetime):
    """Count only an independently broker-observed open STOPLOSS_LIMIT SELL.

    No order placement, and never marks automatic TP or OCO as confirmed.
    """
    owner=_owner(verified_owner_id);key=_key(intent_key);_,ts=_clock(now)
    if source_authenticated is not True or not isinstance(broker_snapshot,Mapping):
        raise LifecycleError("BROKER_STOP_EVIDENCE_MISSING")
    c.execute("BEGIN IMMEDIATE")
    try:
        row=c.execute("""SELECT instrument_token,symbol,filled_qty,state
                   FROM owned_entries WHERE owner_id=? AND day_ist=? AND intent_key=?""",
                   (owner,day_ist,key)).fetchone()
        if not row or row[2]<=0 or row[3] not in ("PARTIALLY_FILLED","FILLED"):
            raise LifecycleError("NO_VERIFIED_FILL_TO_PROTECT")
        token,symbol,qty,_=row
        s=broker_snapshot
        evidence_time=s.get("as_of")
        from datetime import timedelta
        if not isinstance(evidence_time,datetime) or evidence_time.utcoffset() is None or not timedelta(0)<=now-evidence_time<=timedelta(seconds=10):
            raise LifecycleError("STOP_SNAPSHOT_STALE")
        oid=s.get("order_id")
        if (s.get("symbol")!=symbol or s.get("instrument_token")!=token or
            s.get("side")!="SELL" or s.get("ordertype")!="STOPLOSS_LIMIT" or
            s.get("variety")!="STOPLOSS" or s.get("status") not in ("OPEN","TRIGGER_PENDING") or
            type(s.get("remaining_quantity")) is not int or
            s.get("remaining_quantity")!=qty or
            not isinstance(oid,str) or not re.fullmatch(r"[A-Za-z0-9_-]{4,96}",oid)):
            raise LifecycleError("BROKER_STOP_NOT_FULLY_CONFIRMED")
        c.execute("""UPDATE owned_entries SET stop_order_id=?,confirmed_stop_qty=?,updated_utc=?
                  WHERE owner_id=? AND day_ist=? AND intent_key=?""",
                  (oid,qty,ts,owner,day_ist,key))
        _event(c,owner,day_ist,key,"STOP_OBSERVED_FULL_COVERAGE",ts)
        c.commit()
    except Exception:
        c.rollback()
        raise
    return {"protectiveStopBrokerObserved":True,"protectedQuantity":qty,
            "newEntriesBlocked":True,"canSubmitOrder":False,
            "stopFillGuaranteed":False}


def recovery_review(c,*,verified_owner_id:str,broker_orders:list,
                    broker_positions:list,source_authenticated:bool,
                    now:datetime) -> dict:
    """On every restart: stop new orders, list collisions, no auto intervention.

    Manual position rows are never interpreted as OptionX-owned merely because
    symbol or quantity matches. No order cancellation or square-off code.
    """
    owner=_owner(verified_owner_id);_clock(now)
    blocks=["SOURCE_LOCK_ACTIVE","PRODUCTION_LEDGER_NOT_CONNECTED"]
    if source_authenticated is not True:
        blocks.append("BROKER_BOOKS_UNAUTHENTICATED")
    if not isinstance(broker_orders,list) or not isinstance(broker_positions,list):
        blocks.append("BROKER_SNAPSHOT_MISSING")
        broker_orders=[];broker_positions=[]
    own=c.execute("""SELECT broker_order_id,symbol,filled_qty,confirmed_stop_qty,state
                  FROM owned_entries WHERE owner_id=?""",(owner,)).fetchall()
    owned_ids={r[0] for r in own if r[0]}
    if any(r[4] not in ("CLOSED","BROKER_REJECTED") for r in own):
        blocks.append("UNRESOLVED_OWNED_ENTRY")
    if any(r[2]>r[3] for r in own):
        blocks.append("OPEN_FILL_WITHOUT_FULL_STOP_COVERAGE")
    manual_orders=sum(isinstance(o,Mapping) and o.get("order_id") not in owned_ids for o in broker_orders)
    manual_positions=sum(isinstance(p,Mapping) and p.get("net_quantity",0)!=0 for p in broker_positions)
    if manual_orders or manual_positions:
        blocks.append("MANUAL_OR_UNTRACKED_ACCOUNT_EXPOSURE")
    return {"manualOrUntrackedOrders":manual_orders,
            "brokerPositionsWithExposure":manual_positions,
            "unresolvedOwnedEntries":sum(r[4] not in ("CLOSED","BROKER_REJECTED") for r in own),
            "blocks":sorted(set(blocks)),"newEntriesBlocked":True,
            "liveOrdersEnabled":False,"canSubmitOrder":False,
            "canCancelOrder":False,"manualOrdersModified":False}
