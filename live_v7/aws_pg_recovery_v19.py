"""OptionX V19 AWS -> private Supabase PostgreSQL READ-ONLY recovery bridge.

A caller supplies an authenticated Angel GET-only three-book snapshot and a
trusted psycopg/DB-API connection. This module only *reads* private ledger
state. It never sends broker orders, writes execution intent, exposes secrets,
or adopts manual trades based on matching contract symbol.

Cross-account broker orders or positions block all new auto entries; explicit
broker order IDs recorded by OptionX are required for ownership. The database
guard must be STOPPED; absent/malformed guard is an error, not permission.
"""
from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any, Mapping
from uuid import UUID

MAX_AGE = timedelta(seconds=10)
ACTIVE = frozenset({"AWAITING_BROKER_ACK","BROKER_ACCEPTED",
                    "PARTIALLY_FILLED","CANCEL_REQUESTED",
                    "UNKNOWN_BROKER_OUTCOME","MANUAL_REVIEW",
                    "PREPARED","FILLED"})
FINAL = frozenset({"LOCAL_REJECTED","LOCAL_CANCELLED","BROKER_REJECTED",
                   "CANCELLED"})

class PostgresRecoveryError(ValueError):
    pass

def owner_uuid(owner: str) -> str:
    try:
        if not isinstance(owner,str):
            raise ValueError()
        return str(UUID(owner))
    except (ValueError,AttributeError,TypeError):
        raise PostgresRecoveryError("VERIFIED_OWNER_UUID_REQUIRED") from None

def _clock(when: datetime, now: datetime) -> None:
    if any(not isinstance(x,datetime) or x.utcoffset() is None for x in (when,now)):
        raise PostgresRecoveryError("AWARE_BROKER_AND_SERVER_CLOCK_REQUIRED")
    if not timedelta(0)<=now-when<=MAX_AGE:
        raise PostgresRecoveryError("BROKER_SNAPSHOT_STALE")

def _shape(snapshot:Mapping[str,Any]) -> tuple[list,list,dict]:
    if not isinstance(snapshot,Mapping) or snapshot.get("allReadsSucceeded") is not True or snapshot.get("broker")!="Angel":
        raise PostgresRecoveryError("COMPLETE_ANGEL_SNAPSHOT_REQUIRED")
    books=snapshot.get("books")
    if not isinstance(books,Mapping) or any(not isinstance(books.get(k),Mapping) for k in ("orderbook","tradebook","positions")):
        raise PostgresRecoveryError("THREE_BROKER_BOOKS_REQUIRED")
    ob=books["orderbook"].get("orders")
    pos=books["positions"].get("positions")
    trade=books["tradebook"]
    if not isinstance(ob,list) or not isinstance(pos,list) or len(ob)>500 or len(pos)>500:
        raise PostgresRecoveryError("BROKER_ROWS_INVALID")
    for row in ob:
        if not isinstance(row,Mapping) or not isinstance(row.get("order_id"),str) or not isinstance(row.get("symbol"),str):
            raise PostgresRecoveryError("BROKER_ORDER_INVALID")
        if row.get("status") not in {"COMPLETE","REJECTED","CANCELLED","OPEN","PENDING","PARTIALLY_FILLED","CANCEL_REQUESTED"}:
            raise PostgresRecoveryError("BROKER_STATUS_UNKNOWN")
        q,f=row.get("quantity"),row.get("filled_quantity")
        if type(q) is not int or type(f) is not int or q<=0 or f<0 or f>q:
            raise PostgresRecoveryError("BROKER_QUANTITY_INVALID")
    for row in pos:
        if not isinstance(row,Mapping) or not isinstance(row.get("symbol"),str) or type(row.get("net_quantity")) is not int:
            raise PostgresRecoveryError("BROKER_POSITION_INVALID")
    return ob,pos,trade

def read_recovery(
    db, *,
    verified_owner_id: str,
    owner_authenticated: bool,
    snapshot: Mapping[str,Any],
    broker_authenticated: bool,
    snapshot_at: datetime,
    now: datetime,
) -> dict[str,Any]:
    """Trusted server-only PG/Angel comparison; NO INSERT/UPDATE/DELETE.

    HOLD if manual orders are in the account, even when there are no tracked
    OptionX orders. A matching symbol is NEVER sufficient to claim ownership.
    This is a recovery audit, NOT certification that a protective stop was
    placed or a broker fill was reconciled.
    """
    if owner_authenticated is not True or broker_authenticated is not True:
        raise PostgresRecoveryError("SERVER_AND_BROKER_AUTH_REQUIRED")
    if getattr(db,"autocommit",True) is not False:
        raise PostgresRecoveryError("TRANSACTIONAL_POSTGRES_CONNECTION_REQUIRED")
    uid=owner_uuid(verified_owner_id)
    _clock(snapshot_at,now)
    orders,positions,trade=_shape(snapshot)
    with db.cursor() as cur:
        cur.execute("""SELECT state,new_entries_blocked FROM optionx_private.engine_guard
                        WHERE owner_id=%s""",(uid,))
        guard=cur.fetchone()
        # Existing schema's default is deny even with no row. Do not INSERT
        # from the diagnostic bridge: that is a separately authorized write.
        if guard is not None and tuple(guard)!=("STOPPED",True):
            raise PostgresRecoveryError("ENGINE_GUARD_NOT_STOPPED")
        cur.execute("""SELECT external_broker_order_id,contract_symbol,quantity,
                              filled_quantity,state
                       FROM optionx_private.order_intents
                       WHERE owner_id=%s AND broker='Angel'""",(uid,))
        local=cur.fetchall()
        cur.execute("""SELECT stop_order_broker_id,confirmed_open_quantity,
                              protected_quantity,state
                       FROM optionx_private.position_protection
                       WHERE owner_id=%s AND broker='Angel'""",(uid,))
        stops=cur.fetchall()
    if not isinstance(local,list) or not isinstance(stops,list):
        raise PostgresRecoveryError("POSTGRES_ROW_SHAPE_INVALID")
    owned={}
    blocks=set()
    for row in local:
        if not isinstance(row,(tuple,list)) or len(row)!=5:
            raise PostgresRecoveryError("INVALID_LEDGER_INTENT")
        oid,symbol,qty,fill,state=row
        if state not in ACTIVE|FINAL:
            blocks.add("UNRECOGNIZED_LOCAL_INTENT_STATE")
        if state in ACTIVE:
            blocks.add("UNRESOLVED_OWNED_ENTRY")
        if oid is None:
            blocks.add("OWNED_ENTRY_WITHOUT_BROKER_ORDER_ID")
        else:
            if oid in owned:
                blocks.add("DUPLICATE_LEDGER_ORDER_ID")
            owned[oid]=(symbol,qty,fill,state)
    byid={}
    for order in orders:
        oid=order["order_id"]
        if oid in byid:
            blocks.add("DUPLICATE_BROKER_ORDER_ID")
        byid[oid]=order
    manual_order_count=0
    for oid,remote in byid.items():
        if oid not in owned:
            manual_order_count+=1
            blocks.add("MANUAL_OR_UNTRACKED_BROKER_ORDER")
            continue
        symbol,qty,fill,state=owned[oid]
        if symbol!=remote["symbol"] or qty!=remote["quantity"] or fill!=remote["filled_quantity"]:
            blocks.add("BROKER_LEDGER_ORDER_DISCREPANCY")
        if remote["status"] in {"OPEN","PENDING","PARTIALLY_FILLED","CANCEL_REQUESTED"}:
            blocks.add("ACTIVE_BROKER_ORDER")
    if set(owned)-set(byid):
        blocks.add("OWNED_BROKER_ORDER_NOT_FOUND")
    # Whole-account net positions are NOT partitioned by owner/order source.
    # Do not assume the manual +65 position is an OptionX position.
    exposed=[p for p in positions if p["net_quantity"]!=0]
    if exposed:
        blocks.add("ACCOUNT_POSITION_OWNERSHIP_UNRESOLVED")
    for stop in stops:
        if not isinstance(stop,(tuple,list)) or len(stop)!=4:
            raise PostgresRecoveryError("INVALID_LEDGER_STOP")
        stop_id,open_qty,protected_qty,stop_state=stop
        if (stop_state!="STOP_ACKED" or not stop_id or type(open_qty) is not int or
            type(protected_qty) is not int or open_qty!=protected_qty or stop_id not in byid):
            blocks.add("PROTECTIVE_STOP_NOT_BROKER_CONFIRMED_NOW")
    if trade.get("fillsBrokerVerified") is not True or trade.get("reconciliationPending") is not False:
        blocks.add("TRADEBOOK_FILL_RECONCILIATION_PENDING")
    blocks.add("REAL_ORDER_WORKER_SOURCE_LOCKED")
    blocks.add("BROKER_NATIVE_STOP_END_TO_END_NOT_CERTIFIED")
    return {
        "mode":"AWS_POSTGRES_READ_ONLY_RECOVERY",
        "ledgerConnected":True,"ledgerQuerySucceeded":True,
        "engineGuard":"STOPPED" if guard is not None else "ABSENT_DEFAULT_DENY",
        "ledgerOrderCount":len(local),"brokerOrderCount":len(orders),
        "manualOrUntrackedOrderCount":manual_order_count,
        "positionsWithExposure":len(exposed),"storedStopCount":len(stops),
        "blockedReasons":sorted(blocks),
        "newEntriesBlocked":True,"canSubmitOrder":False,
        "canCancelOrder":False,"liveOrdersEnabled":False,
        "manualPositionModified":False,"databaseMutated":False,
    }
