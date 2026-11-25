"""V25 PostgreSQL atomic reservation transaction skeleton — HARD BLOCKED.

Against CURRENT Supabase schema engine_guard only supports STOPPED, RESET_REQUESTED,
REVIEW_REQUIRED, with new_entries_blocked always true. Thus this writer
ALWAYS ABORTS before any INSERT to production. A later independently authorized
migration, broker permission audit and live code review are needed for a
real production writer; do not bypass the guard with env flags.

The code is intentionally transport-agnostic and has zero order send code.
"""
from __future__ import annotations
from datetime import datetime
from zoneinfo import ZoneInfo
from typing import Mapping, Any
from uuid import UUID
import re

IST=ZoneInfo("Asia/Kolkata")


class ReservationBlocked(RuntimeError):
    pass


def reserve_under_guard(db, *, verified_owner_id:str,
                        broker_authenticated:bool, owner_authenticated:bool,
                        order:Mapping[str,Any], idempotency_key:str,
                        now:datetime) -> dict[str,Any]:
    """Serializable transaction and row-lock audit; no current production writes.

    Critical ordering: lock owner guard row, reject STOPPED, then check
    idempotency and two-entry daily budget. A future reviewed implementation
    can add insertion ONLY after separate enabling of audited schema/worker.
    """
    if owner_authenticated is not True or broker_authenticated is not True:
        raise ReservationBlocked("OWNER_OR_BROKER_NOT_AUTHENTICATED")
    if not isinstance(now,datetime) or now.utcoffset() is None:
        raise ReservationBlocked("AWARE_SERVER_TIME_REQUIRED")
    if not isinstance(idempotency_key,str) or not re.fullmatch(r"[A-Za-z0-9_-]{8,96}",idempotency_key):
        raise ReservationBlocked("IDEMPOTENCY_KEY_INVALID")
    if not isinstance(order,Mapping):
        raise ReservationBlocked("INTENT_MISSING")
    try:
        uid=str(UUID(verified_owner_id))
    except (ValueError,TypeError,AttributeError):
        raise ReservationBlocked("OWNER_UUID_INVALID") from None
    if getattr(db,"autocommit",True) is not False:
        raise ReservationBlocked("TRANSACTION_REQUIRED")
    if (order.get("broker")!="Angel" or order.get("market") not in ("NIFTY","BANKNIFTY")
            or order.get("side")!="ENTRY_BUY"):
        raise ReservationBlocked("UNSUPPORTED_INTENT")
    # No independent signal/order allowance is inferred from this method.
    # BEGIN SERIALIZABLE prevents duplicate interleavings; owner-scoped
    # guard FOR UPDATE fences all future entrant processes.
    try:
        with db.cursor() as cur:
            cur.execute("SET TRANSACTION ISOLATION LEVEL SERIALIZABLE READ WRITE")
            cur.execute("""SELECT state,new_entries_blocked
                FROM optionx_private.engine_guard
                WHERE owner_id=%s FOR UPDATE""",(uid,))
            guard=cur.fetchone()
            if guard is None or guard[0]!="RUNNING" or guard[1] is not False:
                # Current production schema can NEVER satisfy this condition.
                raise ReservationBlocked("PRODUCTION_GUARD_STOPPED_DEFAULT_DENY")
            # Even if a future migration enables RUNNING, this code remains
            # explicitly unshippable until human-signed broker lifecycle.
            raise ReservationBlocked("EXECUTION_WORKER_NOT_CERTIFIED")
    finally:
        # Never persist a transaction side effect or leave locks around.
        db.rollback()
