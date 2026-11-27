"""V90 owner-bound manual-position read-only integration diagnostic.

Requires an interactive private terminal and existing trusted environment
owner/client bindings. Only Angel GET order, trade and position books, no
broker order/stop/cancel/modify and no database writes.
"""
from __future__ import annotations
import angel_gateway
from live_v7.aws_angel_owner_reader import _config, verify_login
from live_v7.angel_books_readonly import read_three_books
from scripts.optionx_v90_fill_sl_ownership_review import adjudicate

def run() -> int:
    owner = None
    try:
        owner, client = _config()
        verify_login(owner, client)
        print("ANGEL_OWNER_PROFILE: PASS", flush=True)
        snapshot = read_three_books(owner)
        books = snapshot["books"]
        if snapshot.get("allReadsSucceeded") is not True:
            raise ValueError("INCOMPLETE_BROKER_BOOKS")
        result = adjudicate(
            orders=books["orderbook"]["orders"],
            fills=[],  # tradebook adapter cannot yet authenticate trade IDs
            positions=books["positions"]["positions"],
            owned_intents=[],  # no verified OPTIONX broker order IDs in prod ledger
            protection_records=[],  # don't claim broker stop from empty ledger
            authenticated_broker=True,
            verified_trade_ids=False,
            verified_stop_types=False,
            verified_order_ack=False,
        )
        print("ANGEL_THREE_BOOK_GET: PASS", flush=True)
        print("BROKER_ORDER_RECORDS:",len(books["orderbook"]["orders"]),flush=True)
        print("BROKER_TRADE_RECORDS:",books["tradebook"]["tradeRows"],flush=True)
        print("BROKER_POSITION_RECORDS:",len(books["positions"]["positions"]),flush=True)
        print("NONZERO_BROKER_POSITIONS:",result["positions_with_exposure"],flush=True)
        print("MANUAL_POSITION_ADOPTED: NO",flush=True)
        print("FILL_ID_CERTIFIED:",result["fill_reconciled"],flush=True)
        print("SL_TARGET_ACK_CERTIFIED:",result["sl_confirmed"],flush=True)
        print("POSITION_OWNERSHIP_CERTIFIED:",result["owner_partition_verified"],flush=True)
        print("RECONCILIATION_BLOCKS:",",".join(result["issues"]),flush=True)
        print("V90_REAL_BROKER_READ_ONLY_REVIEW_COMPLETE",flush=True)
        return 0
    except Exception as exc:
        print("V90_READ_ONLY_INSPECTION_BLOCKED:",type(exc).__name__,flush=True)
        return 2
    finally:
        if owner:
            try: angel_gateway.disconnect(owner)
            except Exception: pass
        print("REAL_ORDERS: OFF | MANUAL_POSITION: UNTOUCHED",flush=True)

if __name__ == "__main__":
    raise SystemExit(run())
