"""V48 signed, replay-safe owner control messages for AWS (NO live orders).

A trusted gateway may sign after verifying a Supabase owner JWT itself.
Never expose signing key in browser, logs, git or HTML. Use separate keys for
staging and production. This module handles STOP and REQUEST_UNLOCK_REVIEW
ONLY; it deliberately cannot generate an ARM/TRADE/START command.
"""
from __future__ import annotations
from datetime import datetime, timezone
import hashlib
import hmac
import json
import re
import sqlite3
from uuid import UUID

ACTIONS=frozenset(("EMERGENCY_STOP","REQUEST_UNLOCK_REVIEW","REQUEST_ACTIVATE_LIVE"))
MAX_SKEW_SECONDS=30
class CommandRejected(ValueError): pass

def _uuid(x):
    try:
        u=str(UUID(x))
        if x!=u: raise ValueError()
        return u
    except (TypeError, ValueError, AttributeError):
        raise CommandRejected("OWNER_UUID_INVALID") from None

def _canonical(data):
    if not isinstance(data,dict) or set(data)!={"v","owner","action","nonce","issued_at"}:
        raise CommandRejected("COMMAND_FIELDS_INVALID")
    if data["v"]!=1 or type(data["issued_at"]) is not int:
        raise CommandRejected("COMMAND_VERSION_OR_TIME_INVALID")
    _uuid(data["owner"])
    if data["action"] not in ACTIONS:
        raise CommandRejected("COMMAND_ACTION_NOT_PERMITTED")
    if not isinstance(data["nonce"],str) or not re.fullmatch(r"[A-Za-z0-9_-]{20,96}",data["nonce"]):
        raise CommandRejected("NONCE_INVALID")
    return json.dumps(data,sort_keys=True,separators=(",",":"),ensure_ascii=True).encode("ascii")

def sign_from_trusted_gateway(data, *, key:bytes, owner_verified:bool):
    """Use ONLY on authenticated owner-bound SERVER, never in frontend."""
    if owner_verified is not True:
        raise CommandRejected("TRUSTED_GATEWAY_OWNER_VERIFICATION_REQUIRED")
    if type(key) is not bytes or len(key)<32:
        raise CommandRejected("STRONG_SERVER_KEY_REQUIRED")
    return hmac.new(key,_canonical(data),hashlib.sha256).hexdigest()

def _initialize(db):
    db.execute("""CREATE TABLE IF NOT EXISTS v48_command_nonces(
        owner_digest TEXT NOT NULL,
        nonce TEXT NOT NULL,
        action TEXT NOT NULL CHECK(action IN ('EMERGENCY_STOP','REQUEST_UNLOCK_REVIEW')),
        issued_at INTEGER NOT NULL,
        PRIMARY KEY(owner_digest,nonce)
    )""")

def apply_signed_command(db, *, data, signature, key:bytes,
                         expected_owner:str, now:datetime):
    """Authenticate command, persist nonce and STOP/review atomically.

    If the connection crashes before commit, no command is accepted. If commit
    succeeds but HTTP response is lost, replayed nonce is rejected. Review
    requests are never an authorization to dispatch an order.
    """
    payload=_canonical(data)
    if data["action"]=="REQUEST_ACTIVATE_LIVE":
        raise CommandRejected("ACTIVATION_REQUIRES_V51_CERTIFIED_HANDLER")
    owner=_uuid(expected_owner)
    if owner!=data["owner"]:
        raise CommandRejected("COMMAND_OWNER_MISMATCH")
    if type(key) is not bytes or len(key)<32 or not isinstance(signature,str) or not re.fullmatch(r"[0-9a-f]{64}",signature):
        raise CommandRejected("SIGNATURE_INVALID")
    expected=hmac.new(key,payload,hashlib.sha256).hexdigest()
    if not hmac.compare_digest(expected,signature):
        raise CommandRejected("SIGNATURE_MISMATCH")
    if not isinstance(now,datetime) or now.utcoffset() is None:
        raise CommandRejected("AWARE_CURRENT_TIME_REQUIRED")
    current=int(now.astimezone(timezone.utc).timestamp())
    if abs(current-data["issued_at"])>MAX_SKEW_SECONDS:
        raise CommandRejected("COMMAND_STALE_OR_FUTURE")
    digest=hashlib.sha256(owner.encode("ascii")).hexdigest()
    action=data["action"]
    mode="STOPPED" if action=="EMERGENCY_STOP" else "REVIEW_REQUESTED"
    when=now.astimezone(timezone.utc).isoformat()
    # On AWS production, initialize durable table in an approved private
    # SQLite file already protected by open_control_store.
    _initialize(db)
    db.execute("BEGIN IMMEDIATE")
    try:
        db.execute("""INSERT INTO v48_command_nonces
                (owner_digest,nonce,action,issued_at) VALUES(?,?,?,?)""",
                (digest,data["nonce"],action,data["issued_at"]))
        old=db.execute("SELECT mode FROM owner_control WHERE owner_digest=?",
                       (digest,)).fetchone()
        if old is None:
            db.execute("INSERT INTO owner_control VALUES(?,?,1,?)",
                       (digest,"STOPPED",when))
            db.execute("""INSERT INTO control_audit(owner_digest,action,occurred_utc)
                          VALUES(?,?,?)""",(digest,"INITIAL_STOP",when))
        db.execute("""UPDATE owner_control SET mode=?,stopped=1,updated_utc=?
                      WHERE owner_digest=?""",(mode,when,digest))
        db.execute("""INSERT INTO control_audit(owner_digest,action,occurred_utc)
                      VALUES(?,?,?)""",(digest,"OWNER_REQUEST_UNLOCK_REVIEW"
                                       if action=="REQUEST_UNLOCK_REVIEW" else "EMERGENCY_STOP",when))
        db.commit()
    except sqlite3.IntegrityError:
        db.rollback()
        raise CommandRejected("REPLAYED_OR_CONFLICTING_COMMAND") from None
    except Exception:
        db.rollback()
        raise
    return {"mode":mode,"stopPersisted":True,"commandAccepted":True,
            "liveOrdersEnabled":False,"canSubmitOrder":False,
            "brokerOrdersSent":0}
