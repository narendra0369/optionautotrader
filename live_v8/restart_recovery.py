"""V8 full read-only restart reconciliation proposal, OFFLINE synthetic-only.

Given separately authenticated/fresh normalized orderbook, tradebook and
positions, compare to durable shadow journal. ALWAYS block live entries.
Real broker status normalization and authenticated evidence still require
integration tests; a synthetic PASS is not permission to trade.
"""
from __future__ import annotations

from datetime import datetime
from typing import Mapping, Sequence, Any


def _exact_int(value):
    return isinstance(value, int) and not isinstance(value, bool)


def _shape(rows):
    return isinstance(rows, (list, tuple)) and all(isinstance(x, Mapping) for x in rows)


def _stamp(t, now):
    return (isinstance(t, datetime) and t.tzinfo is not None
            and t.utcoffset() is not None
            and isinstance(now, datetime) and now.tzinfo is not None
            and now.utcoffset() is not None
            and 0 <= (now-t).total_seconds() <= 10)


def assess_restart(*, local, orderbook, tradebook, positions, source_authenticated,
                   broker_owner_match, independent_account_verified,
                   snapshot_at, now, restart_occurred=True):
    """Return diagnostic only. No API transport, no risk authorization.

    Normalized order row: id, symbol, token, side, quantity, filled, status
      protection row additionally: variety='STOPLOSS',
      ordertype='STOPLOSS_LIMIT', triggerprice, price.
    Normalized trade row: trade_id, order_id, symbol, side, quantity
    Normalized position row: symbol, token, net_quantity
    All tables MUST cover the full account, not a filtered first page.
    """
    blocks=[]
    if not isinstance(local,Mapping):
        return _output(["LOCAL_SHADOW_MISSING"])
    if source_authenticated is not True:
        blocks.append("BROKER_SOURCE_NOT_AUTHENTICATED")
    if broker_owner_match is not True or independent_account_verified is not True:
        blocks.append("OWNER_ACCOUNT_UNVERIFIED")
    if not _stamp(snapshot_at,now):
        blocks.append("BROKER_SNAPSHOT_NOT_FRESH")
    if not _shape(orderbook) or not _shape(tradebook) or not _shape(positions):
        return _output(blocks+["BROKER_SNAPSHOT_SHAPE_INVALID"])
    if restart_occurred is not True:
        blocks.append("RESTART_PROOF_REQUIRED")
    symbol=local.get("symbol")
    token=local.get("token")
    planned=local.get("planned_qty")
    bought=local.get("observed_fill")
    sold=local.get("observed_exit")
    net=local.get("net_open")
    protected=local.get("protective_qty")
    oid=local.get("broker_order_id")
    sid=local.get("protective_order_id")
    state=local.get("lifecycle")
    if (not isinstance(symbol,str) or not isinstance(token,str)
        or any(not _exact_int(x) or x<0 for x in (planned,bought,sold,net,protected))
        or bought>planned or sold>bought or net!=bought-sold):
        return _output(blocks+["INVALID_LOCAL_QUANTITY_OR_CONTRACT"])
    if state in ("ACK_UNKNOWN","MANUAL_REVIEW","PREPARED"):
        blocks.append("ENTRY_ACK_UNKNOWN_OR_NOT_CONFIRMED")
    if state not in ("BROKER_OPEN","PARTIALLY_FILLED","FILLED","REJECTED","CANCELLED","ACK_UNKNOWN","MANUAL_REVIEW","PREPARED"):
        blocks.append("UNKNOWN_LOCAL_ORDER_STATE")

    ids=set()
    order_by_id={}
    for row in orderbook:
        id_=row.get("id")
        if not isinstance(id_,str) or not id_ or id_ in ids:
            blocks.append("INVALID_OR_DUPLICATE_BROKER_ORDER")
            continue
        ids.add(id_)
        order_by_id[id_]=row
    if oid:
        entry=order_by_id.get(oid)
        if entry is None:
            blocks.append("ENTRY_ORDER_MISSING_FROM_BROKER")
        else:
            if any((entry.get("symbol")!=symbol,
                    entry.get("token")!=token,
                    entry.get("side")!="BUY",
                    entry.get("quantity")!=planned,
                    entry.get("filled")!=bought)):
                blocks.append("ENTRY_ORDERBOOK_MISMATCH")
            expected={"BROKER_OPEN":{"OPEN","PENDING"},
                      "PARTIALLY_FILLED":{"PARTIAL"},
                      "FILLED":{"COMPLETE"},
                      "REJECTED":{"REJECTED"},
                      "CANCELLED":{"CANCELLED"}}.get(state,set())
            if expected and entry.get("status") not in expected:
                blocks.append("ENTRY_ORDER_STATUS_MISMATCH")
    elif state not in ("PREPARED",):
        blocks.append("MISSING_LINKED_BROKER_ID")

    # All broker order rows are inspected: untracked/manual orders are NOT
    # implicitly ignored (account must be private and reconciled).
    allowed_ids={x for x in (oid,sid) if isinstance(x,str) and x}
    if any(row.get("id") not in allowed_ids for row in orderbook):
        blocks.append("UNTRACKED_BROKER_ORDERS")

    trade_ids=set()
    buy_trades=0
    sell_trades=0
    for tr in tradebook:
        trade_id=tr.get("trade_id")
        qty=tr.get("quantity")
        if not isinstance(trade_id,str) or not trade_id or trade_id in trade_ids:
            blocks.append("INVALID_OR_DUPLICATE_TRADE_ID")
            continue
        trade_ids.add(trade_id)
        if not _exact_int(qty) or qty<=0 or tr.get("symbol")!=symbol:
            blocks.append("BROKER_TRADE_QUANTITY_OR_CONTRACT_MISMATCH")
            continue
        if tr.get("side")=="BUY" and tr.get("order_id")==oid:
            buy_trades+=qty
        elif tr.get("side")=="SELL" and tr.get("order_id") in allowed_ids:
            sell_trades+=qty
        else:
            blocks.append("UNTRACKED_BROKER_TRADE")
    if buy_trades!=bought or sell_trades!=sold:
        blocks.append("TRADEBOOK_SHADOW_FILL_MISMATCH")

    position_map={}
    for pos in positions:
        s=pos.get("symbol")
        qty=pos.get("net_quantity")
        if (not isinstance(s,str) or not s
            or not _exact_int(qty) or s in position_map):
            blocks.append("INVALID_BROKER_POSITION")
            continue
        position_map[s]=pos
    if position_map.get(symbol,{}).get("net_quantity",0)!=net:
        blocks.append("BROKER_POSITION_QUANTITY_MISMATCH")
    if symbol in position_map and position_map[symbol].get("token")!=token:
        blocks.append("BROKER_POSITION_CONTRACT_MISMATCH")
    if any(s!=symbol and row.get("net_quantity",0)!=0 for s,row in position_map.items()):
        blocks.append("OTHER_OPEN_BROKER_POSITIONS")

    if net>0:
        stop=order_by_id.get(sid) if sid else None
        if not stop:
            blocks.append("OPEN_POSITION_WITHOUT_BROKER_STOP")
        elif (stop.get("symbol")!=symbol or stop.get("token")!=token
              or stop.get("side")!="SELL" or stop.get("variety")!="STOPLOSS"
              or stop.get("ordertype")!="STOPLOSS_LIMIT"
              or stop.get("quantity")!=net or stop.get("status") not in
              ("TRIGGER PENDING","OPEN","PENDING")):
            blocks.append("BROKER_NATIVE_STOP_NOT_CONFIRMED")
        if protected!=net:
            blocks.append("STOP_COVERAGE_MISMATCH")
    elif sid:
        blocks.append("POSSIBLE_ORPHAN_STOP")
    if state=="PARTIALLY_FILLED":
        blocks.append("ENTRY_UNFILLED_REMAINDER_MUST_BE_RESOLVED")
    if state in ("REJECTED","CANCELLED") and net:
        blocks.append("CANCEL_REJECT_PARTIAL_REQUIRES_MANUAL_REVIEW")
    return _output(blocks)


def _output(blocks):
    b=sorted(set(blocks))
    return {
        "mode":"OFFLINE_RESTART_RECONCILIATION_ONLY",
        "shadowConsistent":not b,
        "blockingReasons":b if b else ["LIVE_ORDER_RELEASE_NOT_AUTHORIZED"],
        "newEntriesBlocked":True,
        "canSubmitOrder":False,
        "liveExecutionEnabled":False,
        "brokerOrdersSent":0,
        "notice":"All supplied broker snapshots are simulated/external evidence; no autonomous entry, cancel, or target exit.",
    }
