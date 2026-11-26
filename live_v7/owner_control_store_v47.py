"""V47 durable local owner execution control plane (NOT a broker executor).

Persistent fail-closed STOP and owner unlock-review requests. No ARM/START API:
when actual broker execution is source locked, an unlock attempt cannot turn it
on. This file is deliberately standalone and never imports transport / creds.
Local file store is for isolated AWS owner service after installation; it is
NOT shared with Render website and must never be advertised as live execution.
"""
from __future__ import annotations

import hashlib
import os
from pathlib import Path
import re
import sqlite3
import stat
from datetime import datetime, timezone
from uuid import UUID

class ControlBlocked(ValueError):
    pass

def _identity(owner):
    try:
        return hashlib.sha256(str(UUID(str(owner))).encode("ascii")).hexdigest()
    except (TypeError, ValueError, AttributeError):
        raise ControlBlocked("OWNER_ID_INVALID") from None

def _now(when):
    if not isinstance(when, datetime) or when.utcoffset() is None:
        raise ControlBlocked("AWARE_TIMESTAMP_REQUIRED")
    return when.astimezone(timezone.utc).isoformat()

def open_control_store(path):
    target=Path(path)
    if not target.is_absolute() or target.is_symlink():
        raise ControlBlocked("ABSOLUTE_PRIVATE_DB_REQUIRED")
    parent=target.parent
    if not parent.is_dir() or parent.is_symlink():
        raise ControlBlocked("PRIVATE_DIRECTORY_REQUIRED")
    p=parent.stat()
    if p.st_uid!=os.geteuid() or p.st_mode & 0o077:
        raise ControlBlocked("PRIVATE_DIRECTORY_PERMISSIONS")
    if target.exists():
        s=target.stat()
        if not stat.S_ISREG(s.st_mode) or s.st_uid!=os.geteuid() or s.st_mode & 0o077:
            raise ControlBlocked("PRIVATE_FILE_PERMISSIONS")
    prior=os.umask(0o077)
    try:
        db=sqlite3.connect(str(target), timeout=10, isolation_level=None)
        db.execute("PRAGMA synchronous=FULL")
        db.execute("PRAGMA journal_mode=DELETE")
        db.execute("PRAGMA busy_timeout=10000")
        db.execute("""CREATE TABLE IF NOT EXISTS owner_control(
            owner_digest TEXT PRIMARY KEY,
            mode TEXT NOT NULL CHECK(mode IN ('STOPPED','REVIEW_REQUESTED')),
            stopped INTEGER NOT NULL DEFAULT 1 CHECK(stopped=1),
            updated_utc TEXT NOT NULL)""")
        db.execute("""CREATE TABLE IF NOT EXISTS control_audit(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            owner_digest TEXT NOT NULL,
            action TEXT NOT NULL CHECK(action IN
              ('INITIAL_STOP','OWNER_REQUEST_UNLOCK_REVIEW','EMERGENCY_STOP')),
            occurred_utc TEXT NOT NULL)""")
        return db
    finally:
        os.umask(prior)

def _change(db, owner_id, when, *, action, mode):
    owner=_identity(owner_id)
    stamp=_now(when)
    db.execute("BEGIN IMMEDIATE")
    try:
        old=db.execute("SELECT mode FROM owner_control WHERE owner_digest=?",
                       (owner,)).fetchone()
        if old is None:
            db.execute("INSERT INTO owner_control VALUES(?,?,1,?)",
                       (owner,"STOPPED",stamp))
            db.execute("INSERT INTO control_audit(owner_digest,action,occurred_utc) VALUES(?,?,?)",
                       (owner,"INITIAL_STOP",stamp))
        db.execute("UPDATE owner_control SET mode=?,stopped=1,updated_utc=? WHERE owner_digest=?",
                   (mode,stamp,owner))
        db.execute("INSERT INTO control_audit(owner_digest,action,occurred_utc) VALUES(?,?,?)",
                   (owner,action,stamp))
        db.commit()
    except Exception:
        db.rollback()
        raise
    return {"mode":mode,"stopPersisted":True,"liveOrdersEnabled":False,
            "canSubmitOrder":False,"realOrderSent":False}

def request_unlock_review(db,*,owner_id,owner_verified,when):
    """Owner-verified intent ONLY. No actual unlock or order is possible."""
    if owner_verified is not True:
        raise ControlBlocked("VERIFIED_OWNER_REQUIRED")
    return _change(db,owner_id,when,action="OWNER_REQUEST_UNLOCK_REVIEW",
                   mode="REVIEW_REQUESTED")

def emergency_stop(db,*,owner_id,owner_verified,when):
    """Persist STOPPED. Source-locked worker cannot trade regardless."""
    if owner_verified is not True:
        raise ControlBlocked("VERIFIED_OWNER_REQUIRED")
    return _change(db,owner_id,when,action="EMERGENCY_STOP",mode="STOPPED")

def read_state(db,*,owner_id):
    owner=_identity(owner_id)
    rec=db.execute("SELECT mode,stopped FROM owner_control WHERE owner_digest=?",
                   (owner,)).fetchone()
    state=rec[0] if rec else "STOPPED"
    return {"mode":state,"stopPersisted":True if rec is None else rec[1]==1,
            "liveOrdersEnabled":False,"canSubmitOrder":False,
            "requiresIndependentBrokerCertification":True,
            "message":("Owner review requested; orders remain STOPPED."
                       if state=="REVIEW_REQUESTED"
                       else "Emergency STOP/Default STOP is active.")}
