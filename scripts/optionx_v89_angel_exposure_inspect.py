"""OPTIONX V89 read-only owner broker exposure inspection.

One fresh owner-bound Angel session -> fixed three GET books -> safe counts.
No database writes, no broker orders, no auto SL/target. Manual positions
stay untouched. Do not interpret a position record as an open position.
"""
from __future__ import annotations
from datetime import datetime, timezone
from typing import Mapping
import argparse
import getpass
import re
import angel_gateway
from live_v7.angel_books_readonly import read_three_books

def summarize(snapshot: Mapping) -> dict:
    if not isinstance(snapshot, Mapping) or snapshot.get("allReadsSucceeded") is not True or snapshot.get("broker") != "Angel":
        raise ValueError("THREE_BOOKS_NOT_VERIFIED")
    books = snapshot.get("books")
    if not isinstance(books, Mapping) or set(books) != {"orderbook", "tradebook", "positions"}:
        raise ValueError("BROKER_BOOKS_INCOMPLETE")
    ob, tb, pb = (books[x] for x in ("orderbook", "tradebook", "positions"))
    if any(not isinstance(x, Mapping) for x in (ob, tb, pb)):
        raise ValueError("BROKER_BOOKS_INVALID")
    if any(x.get("canSubmitOrder") is not False or x.get("liveExecutionEnabled") is not False for x in (ob,tb,pb)):
        raise ValueError("BROKER_SAFETY_FLAG_MISSING")
    orders, positions, trade_count = ob.get("orders"), pb.get("positions"), tb.get("tradeRows")
    if not isinstance(orders, list) or not isinstance(positions, list) or type(trade_count) is not int or trade_count < 0:
        raise ValueError("BROKER_BOOK_COUNTS_INVALID")
    if any(not isinstance(row, Mapping) for row in orders + positions):
        raise ValueError("BROKER_ROWS_INVALID")
    quantities = [row.get("net_quantity") for row in positions]
    if any(type(q) is not int for q in quantities):
        raise ValueError("POSITION_NET_QTY_INVALID")
    active = {"OPEN", "PENDING", "PARTIALLY_FILLED", "CANCEL_REQUESTED", "UNKNOWN"}
    states = {"COMPLETE", "REJECTED", "CANCELLED"} | active
    if any(row.get("status") not in states for row in orders):
        raise ValueError("ORDER_STATUS_UNKNOWN")
    exposed = sum(q != 0 for q in quantities)
    return {
        "order_records":len(orders),
        "trade_records":trade_count,
        "position_records":len(positions),
        "nonzero_positions":exposed,
        "active_orders":sum(row["status"] in active for row in orders),
        "trade_fill_links_verified":False,
        "sl_target_broker_ack_verified":False,
        "owner_partition_verified":False,
        "can_place":False,
        "can_sell":False,
        "can_cancel":False,
        "can_modify":False,
    }

def main() -> int:
    from live_v7.aws_angel_owner_reader import _config
    owner = None
    try:
        owner, client = _config()
        key = getpass.getpass("Angel API key (hidden): ").strip()
        pin = getpass.getpass("Angel PIN (hidden): ").strip()
        totp = getpass.getpass("Angel TOTP 6 digits (hidden): ").strip()
        if not key or not pin or not re.fullmatch(r"[0-9]{6}", totp):
            print("BLOCKED: INVALID_PRIVATE_LOGIN_INPUT")
            return 2
        result = angel_gateway.connect(owner, {
            "apiKey":key, "clientCode":client, "pin":pin, "totp":totp,
        })
        key = pin = totp = None
        if result.get("connected") is not True or result.get("ownerMatch") is not True:
            raise ValueError("OWNER_OR_BROKER_VERIFICATION_FAILED")
        print("ANGEL_LOGIN_PROFILE: PASS")
        snapshot = read_three_books(owner)
        summary = summarize(snapshot)
        print("ANGEL_THREE_BOOKS: PASS")
        for k, v in summary.items():
            print(k.upper() + ": " + str(v))
        print("RECONCILIATION: PENDING_FILLS_AND_BROKER_PROTECTION")
        return 0
    except (Exception,) as exc:
        # Never print broker exceptions, tokens, client IDs or raw positions.
        print("BROKER_INSPECTION_BLOCKED:", type(exc).__name__)
        return 2
    finally:
        if owner:
            try: angel_gateway.disconnect(owner)
            except Exception: pass
        print("REAL_ORDERS: OFF | MANUAL_POSITIONS: UNTOUCHED")

if __name__ == "__main__":
    raise SystemExit(main())
