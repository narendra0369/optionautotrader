"""OptionX V22: owner-bound runtime evidence review (READ-ONLY).

This module is an auditable bridge between owner-verified PostgreSQL order IDs,
broker-authenticated Angel raw GET-only Order/Trade books, and strict V21 proof
functions. It NEVER adopts manual orders merely by contract symbol, never
writes to PostgreSQL, and never sends broker place/cancel/modify requests.

A clean observation cannot authorize live trading. Broker-side full lifecycle,
native stop placement, OCO, post-crash persistence and live risk authorization
remain separate work.
"""
from __future__ import annotations
from datetime import datetime
from typing import Mapping, Any
from live_v7.aws_pg_recovery_v19 import owner_uuid, _clock
from live_v7.broker_evidence_v21 import (
    confirm_tradebook_fills, confirm_native_stop, EvidenceError
)


class RuntimeEvidenceError(ValueError):
    pass


def review_runtime_evidence(
    db, *, verified_owner_id: str, owner_authenticated: bool,
    broker_authenticated: bool, orderbook_raw: list,
    tradebook_raw: list, snapshot_at: datetime, now: datetime
) -> dict[str, Any]:
    """Use only explicit ledger-owned BUY & STOP ids; never trust symbol alone."""
    if owner_authenticated is not True or broker_authenticated is not True:
        raise RuntimeEvidenceError("OWNER_OR_BROKER_UNVERIFIED")
    if getattr(db, "autocommit", True) is not False:
        raise RuntimeEvidenceError("TRANSACTIONAL_DB_REQUIRED")
    uid = owner_uuid(verified_owner_id)
    _clock(snapshot_at, now)
    if (not isinstance(orderbook_raw, list) or not isinstance(tradebook_raw, list)
            or len(orderbook_raw) > 500 or len(tradebook_raw) > 500):
        raise RuntimeEvidenceError("BROKER_BOOK_SHAPE_INVALID")
    if any(not isinstance(row, Mapping) for row in orderbook_raw+tradebook_raw):
        raise RuntimeEvidenceError("BROKER_BOOK_ROW_INVALID")
    # Read only, based on *durable* broker IDs recorded by the trusted server.
    with db.cursor() as cur:
        cur.execute("""SELECT i.external_broker_order_id, i.contract_symbol,
                              i.instrument_token, i.quantity, i.filled_quantity,
                              p.stop_order_broker_id, p.confirmed_open_quantity,
                              p.protected_quantity, p.state
                       FROM optionx_private.order_intents AS i
                       LEFT JOIN optionx_private.position_protection AS p
                         ON p.owner_id=i.owner_id AND p.order_intent_id=i.id
                       WHERE i.owner_id=%s AND i.broker='Angel'
                       ORDER BY i.created_at, i.id""", (uid,))
        intents = cur.fetchall()
    if not isinstance(intents, list):
        raise RuntimeEvidenceError("LEDGER_ROWS_INVALID")
    if len(intents) > 500:
        raise RuntimeEvidenceError("TOO_MANY_OWNED_INTENTS")
    orders = {}
    for row in orderbook_raw:
        oid = row.get("orderid")
        if not isinstance(oid, str) or not oid:
            raise RuntimeEvidenceError("BROKER_ORDER_ID_MISSING")
        if oid in orders:
            raise RuntimeEvidenceError("BROKER_ORDER_ID_DUPLICATED")
        orders[oid] = row
    owned_ids = set()
    owned_stop_ids = set()
    verified_fills = 0
    verified_stops = 0
    evidence_blocks = set()
    for rec in intents:
        if not isinstance(rec, (tuple, list)) or len(rec) != 9:
            raise RuntimeEvidenceError("LEDGER_INTENT_SHAPE_INVALID")
        oid, symbol, token, quantity, saved_fill, stop_id, open_qty, protected, protection_state = rec
        if oid is None:
            evidence_blocks.add("OWNED_ORDER_WITHOUT_BROKER_ID")
            continue
        if oid in owned_ids:
            raise RuntimeEvidenceError("LEDGER_DUPLICATE_OWNED_ORDER_ID")
        owned_ids.add(oid)
        remote = orders.get(oid)
        if remote is None:
            evidence_blocks.add("OWNED_ORDER_MISSING_FROM_BROKER_BOOK")
            continue
        # Evidence must match owner ledger AND raw broker orderbook, not merely
        # the position symbol. Unknown/malformed trade rows fail closed.
        if (remote.get("tradingsymbol") != symbol
                or remote.get("transactiontype") != "BUY"
                or str(remote.get("symboltoken")) != str(token)):
            evidence_blocks.add("ENTRY_BROKER_CONTRACT_MISMATCH")
            continue
        try:
            remote_qty = int(remote.get("quantity"))
            broker_fill = int(remote.get("filledshares"))
            if (type(quantity) is not int or type(saved_fill) is not int
                    or remote_qty != quantity or not 0 <= broker_fill <= quantity):
                raise EvidenceError("ENTRY_ORDER_QUANTITY_MISMATCH")
            fill = confirm_tradebook_fills(
                owned_order_id=oid, symbol=symbol, expected_quantity=quantity,
                orderbook_filled_quantity=broker_fill,
                raw_trade_rows=tradebook_raw, source_authenticated=True,
                owner_authenticated=True, snapshot_at=snapshot_at, now=now,
            )
            if fill["verifiedQuantity"] != saved_fill:
                evidence_blocks.add("LEDGER_FILL_NOT_YET_RECONCILED")
            if fill["brokerFillProof"]:
                verified_fills += 1
            if not fill["requiresProtection"]:
                if stop_id:
                    evidence_blocks.add("STOP_EXISTS_WITHOUT_BROKER_FILL")
                continue
            if not stop_id or protection_state != "STOP_ACKED":
                evidence_blocks.add("OWNED_FILL_STOP_NOT_ACKED_IN_LEDGER")
                continue
            if (type(open_qty) is not int or type(protected) is not int
                    or not 0 < open_qty == protected <= broker_fill):
                evidence_blocks.add("OWNED_STOP_LEDGER_QUANTITY_MISMATCH")
                continue
            if stop_id in owned_stop_ids:
                raise RuntimeEvidenceError("DUPLICATE_OWNED_STOP_ID")
            owned_stop_ids.add(stop_id)
            stop_row = orders.get(stop_id)
            if stop_row is None:
                evidence_blocks.add("OWNED_STOP_NOT_IN_BROKER_BOOK")
                continue
            confirm_native_stop(
                owned_stop_order_id=stop_id, symbol=symbol,
                instrument_token=str(token), open_quantity=open_qty,
                orderbook_row=stop_row, source_authenticated=True,
                owner_authenticated=True, snapshot_at=snapshot_at, now=now,
            )
            verified_stops += 1
        except (EvidenceError, ValueError, TypeError):
            evidence_blocks.add("OWNED_ENTRY_OR_STOP_PROOF_FAILED")
    # Any other broker order (including manual) is NOT adopted as owned.
    untracked = len(set(orders)-owned_ids-owned_stop_ids)
    if untracked:
        evidence_blocks.add("MANUAL_OR_UNTRACKED_BROKER_ORDER")
    if not intents:
        evidence_blocks.add("NO_OPTIONX_OWNED_ORDERS_TO_VERIFY")
    evidence_blocks.add("LIVE_EXECUTION_SOURCE_LOCKED")
    evidence_blocks.add("NATIVE_STOP_PLACEMENT_AND_OCO_NOT_CERTIFIED")
    return {
        "mode": "AWS_V22_READ_ONLY_BROKER_EVIDENCE",
        "trackedEntries": len(intents),
        "verifiedFillOrders": verified_fills,
        "verifiedStopsObserved": verified_stops,
        "manualOrUntrackedOrders": untracked,
        "blockedReasons": sorted(evidence_blocks),
        "newEntriesBlocked": True, "liveOrdersEnabled": False,
        "canSubmitOrder": False, "canCancelOrder": False,
        "manualPositionsModified": False, "databaseMutated": False,
    }
