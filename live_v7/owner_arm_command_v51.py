"""V51 owner-click activation on AWS; fail-closed when broker is not certified.

The website may request activation with a signed owner command; only the AWS
worker decides eligibility using its OWN trustworthy evidence, persistent
database and independently inspected broker transport. Browser cannot supply
the evidence/transport predicates. In this release the production evidence
provider is intentionally unavailable and returns all False. Hence ACTIVATE
is correctly BLOCKED until a separately certified production integration.
"""
from __future__ import annotations
from datetime import datetime,timezone
import hashlib
import hmac
import json
import re
import sqlite3
from uuid import UUID
from live_v7.signed_owner_commands_v48 import _canonical, CommandRejected
from live_v7.owner_activation_v50 import arm, CHECKS, ActivationDenied
from live_v7.angel_execution_transport import capabilities

def _trusted_aws_evidence():
    """Replace only with audited AWS owner + broker attestations, not flags."""
    return {key:False for key in CHECKS}

def attempt_activation(db,*,data,signature,key,expected_owner,now=None):
    stamp=now or datetime.now(timezone.utc)
    # IMPORTANT: No browser session alone can set activation. Requires a
    # server-issued signature, strong key and unique owner binding.
    raw=_canonical(data)
    if data["action"]!="REQUEST_ACTIVATE_LIVE":
        raise CommandRejected("ACTIVATION_ACTION_REQUIRED")
    try: owner=str(UUID(str(expected_owner)))
    except (TypeError, ValueError,AttributeError):
        raise CommandRejected("OWNER_UUID_INVALID") from None
    if data["owner"]!=owner:
        raise CommandRejected("COMMAND_OWNER_MISMATCH")
    if (type(key) is not bytes or len(key)<32 or
        not isinstance(signature,str) or not re.fullmatch(r"[0-9a-f]{64}",signature)):
        raise CommandRejected("SIGNATURE_INVALID")
    digest=hmac.new(key,raw,hashlib.sha256).hexdigest()
    if not hmac.compare_digest(digest,signature):
        raise CommandRejected("SIGNATURE_MISMATCH")
    if not isinstance(stamp,datetime) or stamp.utcoffset() is None:
        raise CommandRejected("AWARE_TIME_REQUIRED")
    if abs(int(stamp.timestamp())-data["issued_at"])>30:
        raise CommandRejected("COMMAND_STALE_OR_FUTURE")

    # Owner must not be able to submit prerequisites through the API.
    # The source lock is independently read from the actual transport.
    evidence=_trusted_aws_evidence()
    locked=capabilities().get("sourceLockEnabled") is not False
    nonce_owner=hashlib.sha256(owner.encode("ascii")).hexdigest()
    db.execute("""CREATE TABLE IF NOT EXISTS v51_arm_nonces(
        owner_digest TEXT NOT NULL,
        nonce TEXT NOT NULL,
        issued_at INTEGER NOT NULL,
        PRIMARY KEY(owner_digest,nonce))""")
    # Consume nonce BEFORE checking/attempting activation. If DB is restarted,
    # the same signed request cannot be replayed to gain authorization.
    db.execute("BEGIN IMMEDIATE")
    try:
        db.execute("INSERT INTO v51_arm_nonces VALUES(?,?,?)",
                   (nonce_owner,data["nonce"],data["issued_at"]))
        db.commit()
    except sqlite3.IntegrityError:
        db.rollback()
        raise CommandRejected("ACTIVATION_COMMAND_ALREADY_USED") from None
    except Exception:
        db.rollback()
        raise
    try:
        result=arm(db,owner_id=owner,owner_verified=True,
                   server_evidence=evidence,now=stamp,
                   transport_is_source_locked=locked)
    except ActivationDenied:
        return {"state":"BLOCKED","commandReceived":True,
                "liveOrdersEnabled":False,"canSubmitOrder":False,
                "blockers":["PRODUCTION_BROKER_CERTIFICATION_INCOMPLETE",
                            "SOURCE_LOCK_OR_PRODUCTION_GATES_ACTIVE"]}
    return {"state":result["state"],"commandReceived":True,
            "liveOrdersEnabled":False,"canSubmitOrder":False,
            "expiresAt":result["expiresAt"],
            "message":"ARM lease only; a separate exact-order certified writer is required."}
