"""V52 broker-transport dispatch permit verification (no minting interface).

The Angel transport can proceed only on a single-use, exact-payload, short-lived
server-side permit authenticated by a private worker key. User website/browser
never supplies the key. This module NEVER issues permits, starts trading, or
connects to Angel. Issuance belongs to separately certified production worker
after atomic durable intent and risk reservation.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import os
from pathlib import Path
import re
import stat
import sqlite3
from datetime import datetime, timezone

class PermitDenied(PermissionError):pass

def _canonical_order(operation,owner,payload):
    if operation not in ("place","cancel"):
        raise PermitDenied("PERMIT_OPERATION_NOT_ALLOWLISTED")
    if not isinstance(owner,str) or len(owner)<8 or not isinstance(payload,dict):
        raise PermitDenied("PERMIT_OWNER_OR_PAYLOAD_INVALID")
    return hashlib.sha256(json.dumps(
        {"operation":operation,"owner":owner,"payload":payload},
        separators=(",",":"),sort_keys=True,ensure_ascii=True
    ).encode()).hexdigest()

def verify_dispatch_permit(*,operation,owner,payload,permit,now=None):
    """Reject unless token matches exact order and secret held by trusted AWS.

    No external issuer is currently deployed. The signing key must be created
    out-of-band by production provisioning and kept unreadable by web users.
    """
    current=now if now is not None else datetime.now(timezone.utc)
    if not isinstance(current,datetime) or current.utcoffset() is None:
        raise PermitDenied("PERMIT_CLOCK_INVALID")
    if not isinstance(permit,dict) or set(permit)!={"order_sha256","nonce","expires_unix","mac"}:
        raise PermitDenied("PERMIT_MISSING_OR_INVALID")
    if (not isinstance(permit["nonce"],str)
        or not re.fullmatch(r"[a-f0-9]{32,64}",permit["nonce"])
        or type(permit["expires_unix"]) is not int
        or not isinstance(permit["mac"],str)
        or not re.fullmatch(r"[a-f0-9]{64}",permit["mac"])):
        raise PermitDenied("PERMIT_SHAPE_INVALID")
    expiry=permit["expires_unix"]
    current_sec=int(current.timestamp())
    if expiry<current_sec or expiry>current_sec+10:
        raise PermitDenied("PERMIT_STALE_OR_TOO_LONG")
    order_digest=_canonical_order(operation,owner,payload)
    if permit["order_sha256"]!=order_digest:
        raise PermitDenied("PERMIT_NOT_BOUND_TO_EXACT_ORDER")
    keyfile=os.getenv("OPTIONX_V52_PERMIT_KEY_FILE","")
    path=Path(keyfile)
    if not keyfile or not path.is_absolute() or path.is_symlink():
        raise PermitDenied("PRIVATE_SIGNING_KEY_NOT_PROVISIONED")
    try:
        metadata=path.stat()
        if (not stat.S_ISREG(metadata.st_mode) or metadata.st_mode & 0o077
            or metadata.st_uid!=os.geteuid()):
            raise PermitDenied("PRIVATE_SIGNING_KEY_PERMISSIONS")
        key=path.read_bytes()
    except OSError:
        raise PermitDenied("PRIVATE_SIGNING_KEY_UNAVAILABLE") from None
    if len(key)<32 or len(key)>128:
        raise PermitDenied("PRIVATE_SIGNING_KEY_LENGTH_INVALID")
    message=":".join((order_digest,permit["nonce"],str(expiry))).encode()
    calculated=hmac.new(key,message,hashlib.sha256).hexdigest()
    if not hmac.compare_digest(calculated,permit["mac"]):
        raise PermitDenied("PERMIT_SIGNATURE_INVALID")
    # Consume the permit BEFORE any broker network call. If the process
    # crashes after this commit, the permit cannot be retried blindly.
    ledger_path=os.getenv("OPTIONX_V52_PERMIT_LEDGER_FILE","")
    ledger=Path(ledger_path)
    if not ledger_path or not ledger.is_absolute() or ledger.is_symlink():
        raise PermitDenied("PRIVATE_NONCE_LEDGER_NOT_CONFIGURED")
    parent=ledger.parent
    if not parent.is_dir() or parent.is_symlink():
        raise PermitDenied("PRIVATE_NONCE_DIRECTORY_MISSING")
    info=parent.stat()
    if info.st_uid!=os.geteuid() or info.st_mode&0o077:
        raise PermitDenied("PRIVATE_NONCE_DIRECTORY_PERMISSIONS")
    if ledger.exists():
        info=ledger.stat()
        if not stat.S_ISREG(info.st_mode) or info.st_uid!=os.geteuid() or info.st_mode&0o077:
            raise PermitDenied("PRIVATE_NONCE_FILE_PERMISSIONS")
    prev=os.umask(0o077)
    try:
        db=sqlite3.connect(str(ledger),timeout=10,isolation_level=None)
    except sqlite3.Error:
        raise PermitDenied("NONCE_LEDGER_UNAVAILABLE") from None
    finally:
        os.umask(prev)
    try:
        db.execute("PRAGMA journal_mode=DELETE")
        db.execute("PRAGMA synchronous=FULL")
        db.execute("CREATE TABLE IF NOT EXISTS consumed_permits(nonce TEXT PRIMARY KEY,order_digest TEXT NOT NULL,consumed_utc TEXT NOT NULL)")
        db.execute("BEGIN IMMEDIATE")
        try:
            db.execute("INSERT INTO consumed_permits VALUES(?,?,?)",
                       (permit["nonce"],order_digest,current.isoformat()))
            db.commit()
        except sqlite3.IntegrityError:
            db.rollback()
            raise PermitDenied("PERMIT_ALREADY_CONSUMED") from None
        except Exception:
            db.rollback()
            raise
    except sqlite3.Error:
        raise PermitDenied("PERMIT_NONCE_PERSISTENCE_FAILED") from None
    finally:
        db.close()
    return {"verified":True,"singleUseConsumed":True,
            "orderDigest":order_digest}
