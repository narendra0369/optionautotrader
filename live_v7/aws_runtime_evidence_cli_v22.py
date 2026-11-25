"""V22 interactive AWS read-only book evidence (no broker writes).

Run as optionx OS account in private TTY. Password hidden, TLS verify-full.
Existing source-level real-order lock unchanged. No broker/order symbols,
passwords, or raw books are printed.
"""
from __future__ import annotations

from datetime import datetime, timezone
import sys

import angel_gateway
from live_v7.aws_angel_owner_reader import _config, verify_login
from live_v7.aws_pg_safe_diag_v20 import connect_readonly, stage_name
from live_v7.angel_books_readonly import read_book
from live_v7.aws_pg_recovery_v19 import read_recovery
from live_v7.aws_runtime_evidence_v22 import review_runtime_evidence


def run() -> int:
    db=None
    owner=None
    stage="OWNER_CONFIG"
    try:
        owner,client=_config()
        print("OWNER_CONFIG: PASS",flush=True)
        stage="PG_CONNECT"
        db=connect_readonly()
        print("SUPABASE_TLS_POSTGRES: PASS",flush=True)
        stage="ANGEL_LOGIN"
        verify_login(owner,client)
        print("ANGEL_OWNER_LOGIN: PASS",flush=True)
        stage="BROKER_BOOKS"
        now=datetime.now(timezone.utc)
        orders=read_book(owner,"orderbook",now=now,include_raw_for_server=True)
        trades=read_book(owner,"tradebook",now=now,include_raw_for_server=True)
        positions=read_book(owner,"positions",now=now)
        snapshot_at=datetime.now(timezone.utc)
        print("ANGEL_THREE_BOOK_READ: PASS",flush=True)
        snapshot={"broker":"Angel","allReadsSucceeded":True,"books":{
             "orderbook":{"orders":orders["orders"]},
             "tradebook":{"tradeRows":trades["tradeRows"],
                           "fillsBrokerVerified":False,"reconciliationPending":True},
             "positions":{"positions":positions["positions"]}}}
        stage="PG_RECONCILE"
        base=read_recovery(
            db,verified_owner_id=owner,owner_authenticated=True,
            broker_authenticated=True,snapshot=snapshot,
            snapshot_at=snapshot_at,now=datetime.now(timezone.utc))
        print("SUPABASE_LEDGER_READ: PASS",flush=True)
        stage="V22_EVIDENCE"
        evidence=review_runtime_evidence(
            db,verified_owner_id=owner,owner_authenticated=True,
            broker_authenticated=True,
            orderbook_raw=orders["rawRows"],
            tradebook_raw=trades["rawRows"],
            snapshot_at=snapshot_at,now=datetime.now(timezone.utc))
        print("V22_EVIDENCE_REVIEW: PASS",flush=True)
        print("TRACKED_ENTRIES:",evidence["trackedEntries"])
        print("VERIFIED_FILL_ORDERS:",evidence["verifiedFillOrders"])
        print("VERIFIED_STOP_ORDERS:",evidence["verifiedStopsObserved"])
        print("MANUAL_OR_UNTRACKED_ORDERS:",evidence["manualOrUntrackedOrders"])
        print("BLOCKED_REASONS:",",".join(sorted(
            set(base["blockedReasons"])|set(evidence["blockedReasons"]))))
        return 0
    except Exception as exc:
        print("BLOCKED_STAGE:",stage,flush=True)
        print("SAFE_REASON:",stage_name(exc,stage) if stage in
              ("OWNER_CONFIG","PG_CONNECT","ANGEL_LOGIN","BROKER_BOOKS")
              else "BROKER_LEDGER_EVIDENCE_INCOMPLETE",flush=True)
        return 2
    finally:
        print("REAL_ORDERS: OFF | MANUAL_POSITIONS: UNTOUCHED",flush=True)
        if db is not None:
            try:db.close()
            except Exception:pass
        if owner is not None:
            try:angel_gateway.disconnect(owner)
            except Exception:pass


if __name__=="__main__":
    sys.exit(run())
