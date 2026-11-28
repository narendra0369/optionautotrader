"""AWS interactive owner -> Angel GET books -> Supabase private PostgreSQL review.

This process asks for secrets only on a private TTY. Broker session remains
RAM-only. PostgreSQL URL is entered hidden and never printed/stored. No live
broker order, stop, cancel, SQL mutation, or browser API call exists.
Requires psycopg >=3 on AWS with TLS certificate verification.
"""
from __future__ import annotations

from datetime import datetime,timezone
import getpass
import os
import re
import sys

from live_v7.aws_angel_owner_reader import _config, verify_login
from live_v7.angel_books_readonly import read_three_books
from live_v7.aws_pg_recovery_v19 import read_recovery
import angel_gateway

def connect_postgres(*,prompt=getpass.getpass,driver=None):
    if not (sys.stdin.isatty() and sys.stdout.isatty()) or os.geteuid()==0:
        raise ValueError("PRIVATE_NONROOT_TERMINAL_REQUIRED")
    uri=prompt("Supabase PostgreSQL connection URI (hidden): ")
    if not isinstance(uri,str) or not uri.startswith("postgresql://") or len(uri)>4096:
        raise ValueError("POSTGRES_URI_REQUIRED")
    if driver is None:
        import psycopg
        driver=psycopg
    # Enforce certificate hostname checks and a short connection timeout.
    # Do not add a Render secret, browser key, or printed DSN.
    db=driver.connect(uri,sslmode="verify-full",connect_timeout=8,autocommit=False)
    if getattr(db,"autocommit",True) is not False:
        raise ValueError("TRANSACTION_REQUIRED")
    return db

def run() -> int:
    owner=None
    try:
        owner,client=_config()
        verify_login(owner,client)
        now=datetime.now(timezone.utc)
        snapshot=read_three_books(owner,now=now)
        db=connect_postgres()
        try:
            result=read_recovery(db,verified_owner_id=owner,owner_authenticated=True,
                                 broker_authenticated=True,snapshot=snapshot,
                                 snapshot_at=now,now=datetime.now(timezone.utc))
        finally:
            db.close()
        # No sensitive contract/order identifiers in output.
        print("AWS_ANGEL_LOGIN: VERIFIED")
        print("POSTGRES_PRIVATE_LEDGER: CONNECTED")
        print("BROKER_ORDERS: "+str(result["brokerOrderCount"]))
        print("MANUAL_OR_UNTRACKED_ORDERS: "+str(result["manualOrUntrackedOrderCount"]))
        print("POSITIONS_WITH_EXPOSURE: "+str(result["positionsWithExposure"]))
        print("BROKER_LEDGER_REVIEW: "+",".join(result["blockedReasons"]))
        print("REAL_ORDERS: OFF | AUTO_ENTRY: BLOCKED | MANUAL_TRADES: UNTOUCHED")
        return 0
    except (Exception,) as exc:
        # Never expose driver or broker exceptions: they can include URLs,
        # account tokens, IPs, passwords or raw private order data.
        print("AWS_POSTGRES_RECOVERY_BLOCKED: credentials/DB/broker verification unavailable")
        return 2
    finally:
        if owner:
            try:
                angel_gateway.disconnect(owner)
            except Exception:
                pass

if __name__=="__main__":
    raise SystemExit(run())
