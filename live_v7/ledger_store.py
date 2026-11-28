"""OptionX V7 — transaction-safe SHADOW journal helpers (NOT DEPLOYED).

Uses an externally supplied trusted PostgreSQL connection. NEVER opens its
own DB/network connection, obtains tokens, authenticates users, or sends orders.
These helpers cannot enable live trading. Schema draft must be independently
audited and applied later; nothing here calls it automatically.

The owner must come from VERIFIED server authentication, not a browser body.
"""
from __future__ import annotations

from datetime import datetime
from decimal import Decimal, InvalidOperation
from typing import Any, Mapping
from uuid import UUID
from zoneinfo import ZoneInfo

IST = ZoneInfo("Asia/Kolkata")
BROKER_MARKETS = {"NIFTY": "Angel", "BANKNIFTY": "Angel", "BTC": "Delta"}


class LedgerError(ValueError):
    pass


def _owner(value: Any) -> str:
    if not isinstance(value, str):
        raise LedgerError("Verified user UUID required")
    try:
        return str(UUID(value))
    except (ValueError, AttributeError):
        raise LedgerError("Verified user UUID required") from None


def _decimal(value: Any, label: str) -> Decimal:
    if isinstance(value, bool) or not isinstance(value, (str, int, Decimal)):
        raise LedgerError(label + " must be exact decimal")
    try:
        amount = Decimal(value)
    except (ValueError, InvalidOperation, TypeError):
        raise LedgerError(label + " invalid") from None
    if not amount.is_finite():
        raise LedgerError(label + " invalid")
    return amount


def save_shadow_preview(
    db,
    *,
    verified_owner_id: str,
    owner_authorized_by_server: bool,
    intent: Mapping[str, Any],
    now: datetime,
) -> dict[str, Any]:
    """Reserve idempotent PREPARED order *research* while server guard is OFF.

    Requires a DB-API 2.0 PostgreSQL connection. The database transaction locks
    the owner guard row. There is no send/submit method anywhere in this module.
    The unique index prevents duplicate previews with the same user/day/key.
    """
    if owner_authorized_by_server is not True:
        raise LedgerError("Owner must be independently authenticated")
    uid = _owner(verified_owner_id)
    if not isinstance(intent, Mapping):
        raise LedgerError("Malformed proposed research preview")
    if not isinstance(now, datetime) or now.utcoffset() is None:
        raise LedgerError("Trusted timezone-aware server time required")
    day = now.astimezone(IST).date()
    market, broker = intent.get("market"), intent.get("broker")
    if BROKER_MARKETS.get(market) != broker:
        raise LedgerError("Broker/market mismatch")
    key = intent.get("idempotency_key")
    if not isinstance(key, str) or not 8 <= len(key) <= 96 or not key.isascii() or not all(
        ch.isalnum() or ch in "_-" for ch in key
    ):
        raise LedgerError("Invalid idempotency key")
    token, symbol, kind = (intent.get(x) for x in ("instrument_token", "contract_symbol", "contract_kind"))
    if not isinstance(token, str) or not 1 <= len(token) <= 64:
        raise LedgerError("Invalid instrument token")
    if not isinstance(symbol, str) or not 4 <= len(symbol) <= 72:
        raise LedgerError("Invalid contract label")
    if not isinstance(kind, str) or not 2 <= len(kind) <= 16:
        raise LedgerError("Invalid derivative kind")
    qty = intent.get("quantity")
    if isinstance(qty, bool) or not isinstance(qty, int) or qty <= 0:
        raise LedgerError("Positive integer quantity required")
    entry = _decimal(intent.get("planned_entry"), "entry")
    stop = _decimal(intent.get("planned_stop"), "stop")
    target = _decimal(intent.get("planned_target"), "target")
    loss = _decimal(intent.get("estimated_max_loss"), "loss")
    if not (target > entry > stop > 0 and loss > 0):
        raise LedgerError("Invalid non-executing research risk")
    # The 'with db' context must be a real DB transaction, never autocommit.
    if getattr(db, "autocommit", False):
        raise LedgerError("Autocommit connection unsafe for ledger mutation")
    with db:
        with db.cursor() as cur:
            cur.execute(
                """INSERT INTO optionx_private.engine_guard(owner_id)
                   VALUES (%s) ON CONFLICT(owner_id) DO NOTHING""",
                (uid,),
            )
            cur.execute(
                """SELECT state, new_entries_blocked FROM optionx_private.engine_guard
                   WHERE owner_id=%s FOR UPDATE""",
                (uid,),
            )
            guard = cur.fetchone()
            if guard != ("STOPPED", True):
                # Even a later migration introducing an ON state must NOT
                # turn research previews into order execution.
                raise LedgerError("Development previews require a STOPPED guard")
            cur.execute(
                """INSERT INTO optionx_private.order_intents(
                       owner_id,trade_day_ist,idempotency_key,broker,market,
                       instrument_token,contract_symbol,contract_kind,side,
                       quantity,planned_entry,planned_stop,planned_target,
                       estimated_max_loss,state
                   ) VALUES(
                       %s,%s,%s,%s,%s,%s,%s,%s,'ENTRY_BUY',%s,%s,%s,%s,%s,
                       'PREPARED'
                   ) ON CONFLICT(owner_id, broker, trade_day_ist, idempotency_key)
                       DO NOTHING RETURNING id""",
                (uid, day, key, broker, market, token, symbol, kind,
                 qty, entry, stop, target, loss),
            )
            row = cur.fetchone()
    return {
        "saved": row is not None,
        "duplicatePreview": row is None,
        "mode": "SHADOW_PREVIEW_ONLY",
        "liveExecutionEnabled": False,
        "canSubmitOrder": False,
        "noBrokerNetworkCalls": True,
    }


def unresolved_count(db, *, verified_owner_id: str, broker: str) -> int:
    """Read outstanding broker states; unknown/outstanding orders block entries."""
    uid = _owner(verified_owner_id)
    if broker not in ("Angel", "Delta"):
        raise LedgerError("Broker not allowed")
    with db.cursor() as cur:
        cur.execute(
            """SELECT count(*) FROM optionx_private.order_intents
               WHERE owner_id=%s AND broker=%s AND state IN (
                   'AWAITING_BROKER_ACK','BROKER_ACCEPTED',
                   'PARTIALLY_FILLED','CANCEL_REQUESTED',
                   'UNKNOWN_BROKER_OUTCOME','MANUAL_REVIEW'
               )""",
            (uid, broker),
        )
        n = cur.fetchone()
    if not isinstance(n, (tuple, list)) or len(n) != 1 or not isinstance(n[0], int):
        raise LedgerError("Invalid unresolved order count")
    return n[0]


def public_ledger_status() -> dict[str, Any]:
    return {
        "stage": "UNAPPLIED_SQL_AND_UNTESTED_PYTHON_SOURCE",
        "databaseConnected": False,
        "durableLedgerDeployed": False,
        "liveOrderExecutionEnabled": False,
        "newOrdersBlocked": True,
    }
