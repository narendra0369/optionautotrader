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
    # A MAC alone does NOT ensure single use. Do not return an executable
    # grant until production nonce/journal transactional consumption is wired.
    raise PermitDenied("DURABLE_NONCE_CONSUMPTION_NOT_CERTIFIED")
