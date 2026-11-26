"""V43 isolated durable pre-send INTENT ledger, not a broker order sender.

SQLite durability/uniqueness prototype for a future reviewed production
journal. Reserving or sealing an intent NEVER authorizes any broker request.
A sealed intent persists as an ambiguous MAY_HAVE_SENT, including after crash.
No API to reset/dispatch/retry it; independent broker reconciliation required.
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import re
import sqlite3
import stat
from datetime import datetime, timezone
from uuid import UUID

class IntentBlocked(ValueError): pass

def _identity(owner, key, now):
    try: owner = str(UUID(owner))
    except (ValueError, TypeError, AttributeError):
        raise IntentBlocked("OWNER_UUID_INVALID") from None
    if not isinstance(key,str) or not re.fullmatch(r"[A-Za-z0-9_-]{8,96}",key):
        raise IntentBlocked("IDEMPOTENCY_KEY_INVALID")
    if not isinstance(now,datetime) or now.utcoffset() is None:
        raise IntentBlocked("AWARE_TIME_REQUIRED")
    return hashlib.sha256(owner.encode()).hexdigest(),key,now.astimezone(timezone.utc).isoformat()

def _draft(order):
    if not isinstance(order,dict) or set(order)!={"exchange","symbol","token","side","type","price","quantity","producttype","duration"}:
        raise IntentBlocked("EXACT_ORDER_FIELDS_REQUIRED")
    if (order["exchange"]!="NFO" or order["side"]!="SELL" or order["type"]!="LIMIT"
        or order["duration"]!="DAY" or order["producttype"] not in ("INTRADAY","CARRYFORWARD")
        or order["symbol"]!="NIFTY29DEC2629000CE" or order["token"]!="38158"
        or type(order["quantity"]) is not int or order["quantity"]!=65 or order["price"]!="10.50"):
        raise IntentBlocked("V43_FIXED_DRAFT_MISMATCH")
    return json.dumps(order,sort_keys=True,separators=(",",":"))

def open_ledger(path):
    path=Path(path)
    if not path.is_absolute() or path.is_symlink():
        raise IntentBlocked("ABSOLUTE_NON_SYMLINK_PATH_REQUIRED")
    parent=path.parent
    if not parent.is_dir() or parent.is_symlink():
        raise IntentBlocked("PRIVATE_DIRECTORY_REQUIRED")
    p=parent.stat()
    if p.st_uid!=os.geteuid() or (p.st_mode&0o077)!=0:
        raise IntentBlocked("PRIVATE_DIRECTORY_PERMISSIONS")
    if path.exists():
        s=path.stat()
        if not stat.S_ISREG(s.st_mode) or s.st_uid!=os.geteuid() or (s.st_mode&0o077):
            raise IntentBlocked("PRIVATE_LEDGER_FILE_PERMISSIONS")
    prior=os.umask(0o077)
    try:
        db=sqlite3.connect(str(path),timeout=10,isolation_level=None)
        db.execute("PRAGMA journal_mode=DELETE")
        db.execute("PRAGMA synchronous=FULL")
        db.execute("PRAGMA busy_timeout=10000")
        db.execute("""CREATE TABLE IF NOT EXISTS intents (
          owner_digest TEXT NOT NULL, intent_key TEXT NOT NULL,
          order_json TEXT NOT NULL,
          state TEXT NOT NULL CHECK(state IN ('RESERVED_UNSENT','MAY_HAVE_SENT_RECONCILE')),
          created_utc TEXT NOT NULL,
          PRIMARY KEY(owner_digest,intent_key))""")
        db.execute("""CREATE TABLE IF NOT EXISTS events (
          id INTEGER PRIMARY KEY AUTOINCREMENT, owner_digest TEXT NOT NULL,
          intent_key TEXT NOT NULL, event TEXT NOT NULL, timestamp_utc TEXT NOT NULL)""")
        return db
    finally:
        os.umask(prior)

def reserve(db, *,owner_id,idempotency_key,order,now):
    digest,key,when=_identity(owner_id,idempotency_key,now)
    payload=_draft(order)
    db.execute("BEGIN IMMEDIATE")
    try:
        previous=db.execute("SELECT order_json,state FROM intents WHERE owner_digest=? AND intent_key=?",
            (digest,key)).fetchone()
        if previous:
            if previous[0]!=payload:
                raise IntentBlocked("IDEMPOTENCY_CONFLICT")
            state=previous[1]
            result="ALREADY_RESERVED_NO_DISPATCH"
        else:
            # Entire transaction persists before any possible subsequent action.
            db.execute("INSERT INTO intents VALUES(?,?,?,?,?)",(digest,key,payload,"RESERVED_UNSENT",when))
            db.execute("INSERT INTO events(owner_digest,intent_key,event,timestamp_utc) VALUES(?,?,?,?)",
                (digest,key,"RESERVED",when))
            state="RESERVED_UNSENT"
            result="RESERVED_ONLY"
        db.commit()
    except Exception:
        db.rollback()
        raise
    return {"state":state,"result":result,"canSubmitOrder":False,"canRetry":False}

def seal_uncertain(db, *,owner_id,idempotency_key,now):
    """Crash-fence simulation. No network call follows this method.

    Source does not provide a broker dispatch mechanism. A future reviewed
    sender would need atomic provenance and independent account reconciliation.
    """
    digest,key,when=_identity(owner_id,idempotency_key,now)
    db.execute("BEGIN IMMEDIATE")
    try:
        old=db.execute("SELECT state FROM intents WHERE owner_digest=? AND intent_key=?",
            (digest,key)).fetchone()
        if old is None:
            raise IntentBlocked("INTENT_UNKNOWN")
        if old[0]=="RESERVED_UNSENT":
            db.execute("UPDATE intents SET state='MAY_HAVE_SENT_RECONCILE' WHERE owner_digest=? AND intent_key=?",
                (digest,key))
            db.execute("INSERT INTO events(owner_digest,intent_key,event,timestamp_utc) VALUES(?,?,?,?)",
                (digest,key,"SEALED_UNKNOWN",when))
        db.commit()
    except Exception:
        db.rollback()
        raise
    return {"state":"MAY_HAVE_SENT_RECONCILE","canSubmitOrder":False,"canRetry":False}

def recover(db, *,owner_id,idempotency_key,now):
    digest,key,_=_identity(owner_id,idempotency_key,now)
    row=db.execute("SELECT state FROM intents WHERE owner_digest=? AND intent_key=?",
        (digest,key)).fetchone()
    if row is None:
        raise IntentBlocked("INTENT_UNKNOWN")
    return {"state":row[0],"brokerReconciliationRequired":True,
            "manualPositionAdopted":False,"canSubmitOrder":False,
            "canRetry":False,"canCancel":False,"realOrdersEnabled":False}
