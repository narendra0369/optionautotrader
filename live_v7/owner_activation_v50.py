"""OptionX V50: owner-controlled activation state, fail closed.

This is a control-plane state manager, NOT an Angel One order sender. All
production readiness evidence must be collected by the trusted AWS worker,
never from the website/browser or Render's stale authentication session.

The activation lease is short and non-renewing: owner must re-authorize
after expiry. A worker can read this control only; actual broker transport
still has an independent source lock and requires separate certification.
"""
from __future__ import annotations
import hashlib
import os
from pathlib import Path
import re
import sqlite3
import stat
from datetime import datetime, timedelta, timezone
from uuid import UUID

class ActivationDenied(PermissionError): pass

# All predicates represent independent AWS-side checks. Never trust a
# user-submitted checklist or a UI POST body to supply them.
CHECKS=(
    "owner_session_mfa_fresh",
    "broker_technical_approval_verified",
    "account_write_entitlement_verified",
    "aws_static_ip_verified",
    "production_journal_verified",
    "broker_books_and_quotes_fresh",
    "risk_and_daily_quota_enforced",
    "unknown_outcome_recovery_tested",
    "protective_exit_lifecycle_tested",
    "worker_leader_fence_verified",
    "manual_positions_excluded",
    "broker_write_transport_certified",
)

def _owner(owner):
    try: return hashlib.sha256(str(UUID(str(owner))).encode()).hexdigest()
    except (ValueError,TypeError,AttributeError):
        raise ActivationDenied("OWNER_UUID_INVALID") from None

def _timestamp(now):
    if not isinstance(now,datetime) or now.utcoffset() is None:
        raise ActivationDenied("AWARE_TIME_REQUIRED")
    return now.astimezone(timezone.utc)

def create_store(path):
    path=Path(path)
    if not path.is_absolute() or path.is_symlink():
        raise ActivationDenied("ABSOLUTE_PRIVATE_PATH_REQUIRED")
    parent=path.parent
    if not parent.is_dir() or parent.is_symlink():
        raise ActivationDenied("PRIVATE_DIRECTORY_REQUIRED")
    info=parent.stat()
    if info.st_uid!=os.geteuid() or info.st_mode & 0o077:
        raise ActivationDenied("PRIVATE_DIRECTORY_PERMISSIONS")
    if path.exists():
        info=path.stat()
        if not stat.S_ISREG(info.st_mode) or info.st_uid!=os.geteuid() or info.st_mode & 0o077:
            raise ActivationDenied("PRIVATE_DB_PERMISSIONS")
    old=os.umask(0o077)
    try:
        db=sqlite3.connect(str(path),timeout=10,isolation_level=None)
        db.execute("PRAGMA journal_mode=DELETE")
        db.execute("PRAGMA synchronous=FULL")
        db.execute("PRAGMA busy_timeout=10000")
        db.execute("""CREATE TABLE IF NOT EXISTS activation(
            owner_digest TEXT PRIMARY KEY,
            state TEXT NOT NULL CHECK(state IN ('STOPPED','ARMED')),
            expires_utc TEXT, version INTEGER NOT NULL DEFAULT 0,
            updated_utc TEXT NOT NULL)""")
        db.execute("""CREATE TABLE IF NOT EXISTS activation_audit(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            owner_digest TEXT NOT NULL, action TEXT NOT NULL,
            occurred_utc TEXT NOT NULL, evidence_digest TEXT)""")
        return db
    finally: os.umask(old)

def _blockers(evidence):
    # Evidence is a trusted server-side snapshot, NOT user data. An absent or
    # outdated predicate fails, even if all others pass.
    if not isinstance(evidence,dict) or set(evidence)!=set(CHECKS):
        return list(CHECKS)
    return [key for key in CHECKS if evidence.get(key) is not True]

def eligibility(*, evidence, owner_verified, now):
    _timestamp(now)
    blocked=_blockers(evidence)
    if owner_verified is not True:
        blocked=["OWNER_VERIFICATION_REQUIRED"]+blocked
    return {"eligible":not blocked,"blockers":blocked,
            "activationRequired":True,"ordersSent":0}

def arm(db,*,owner_id,owner_verified,server_evidence,now,
        transport_is_source_locked=True):
    """Require ALL server proofs, fresh MFA and independently certified transport.

    Browser cannot change transport_is_source_locked: only internal worker code
    may pass its own inspected capability state.
    """
    stamp=_timestamp(now)
    status=eligibility(evidence=server_evidence,owner_verified=owner_verified,now=stamp)
    if transport_is_source_locked is not False:
        status["blockers"].append("ANGEL_SOURCE_LOCK_STILL_ACTIVE")
    if status["blockers"]:
        raise ActivationDenied("PREREQUISITES_NOT_CERTIFIED:"+
                               ",".join(status["blockers"]))
    digest=_owner(owner_id)
    expiry=stamp+timedelta(minutes=15)
    evidence_digest=hashlib.sha256(
        ",".join(sorted(CHECKS)).encode()).hexdigest()
    db.execute("BEGIN IMMEDIATE")
    try:
        db.execute("""INSERT INTO activation(owner_digest,state,expires_utc,version,updated_utc)
                      VALUES(?,'ARMED',?,1,?)
                      ON CONFLICT(owner_digest) DO UPDATE SET
                        state='ARMED',expires_utc=excluded.expires_utc,
                        version=version+1,updated_utc=excluded.updated_utc""",
                   (digest,expiry.isoformat(),stamp.isoformat()))
        db.execute("""INSERT INTO activation_audit
                      (owner_digest,action,occurred_utc,evidence_digest)
                      VALUES(?,'OWNER_ARMED',?,?)""",
                   (digest,stamp.isoformat(),evidence_digest))
        db.commit()
    except Exception:
        db.rollback()
        raise
    # Arming doesn't submit or approve any specific trade.
    return {"state":"ARMED","expiresAt":expiry.isoformat(),
            "ordersSent":0,"canSubmitOrder":False,
            "nextStep":"ORDER_SPECIFIC_RISK_AND_CONSENT_CHECK_REQUIRED"}

def stop(db,*,owner_id,owner_verified,now):
    if owner_verified is not True: raise ActivationDenied("OWNER_VERIFICATION_REQUIRED")
    digest=_owner(owner_id);stamp=_timestamp(now)
    db.execute("BEGIN IMMEDIATE")
    try:
        db.execute("""INSERT INTO activation(owner_digest,state,expires_utc,version,updated_utc)
                      VALUES(?,'STOPPED',NULL,1,?)
                      ON CONFLICT(owner_digest) DO UPDATE SET
                      state='STOPPED',expires_utc=NULL,version=version+1,
                      updated_utc=excluded.updated_utc""",(digest,stamp.isoformat()))
        db.execute("""INSERT INTO activation_audit
                    (owner_digest,action,occurred_utc)
                    VALUES(?,'OWNER_STOPPED',?)""",(digest,stamp.isoformat()))
        db.commit()
    except Exception:
        db.rollback();raise
    return {"state":"STOPPED","ordersSent":0,"canSubmitOrder":False}

def state(db,*,owner_id,now):
    digest=_owner(owner_id);stamp=_timestamp(now)
    rec=db.execute("SELECT state,expires_utc FROM activation WHERE owner_digest=?",
                   (digest,)).fetchone()
    valid=False
    if rec and rec[0]=="ARMED" and rec[1]:
        try: valid=stamp<datetime.fromisoformat(rec[1])
        except (TypeError,ValueError): valid=False
    return {"state":"ARMED" if valid else "STOPPED",
            "leaseValid":valid,
            "canSubmitOrder":False,
            "ordersSent":0}
