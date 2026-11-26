"""OptionX V30 owner-only *preparation* worker for manual SELL LIMIT.

Reads authenticated Angel NFO position/orderbook and LTP and writes a LOCAL,
non-authoritative, append-only draft audit. It never places, modifies or
cancels a broker order; real transport remains source-locked. No user input
can enable execution. Not a production order journal.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import os
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from pathlib import Path
import sqlite3
import stat
import uuid

import angel_gateway
from live_v7.aws_angel_owner_reader import _config, verify_login
from live_v7.angel_books_readonly import read_book
from live_v7.manual_sl_preflight_v26 import assess_manual_positions
from live_v7.manual_sl_quote_v27 import fetch_ltp

SYMBOL="NIFTY29DEC2629000CE"
TOKEN="38158"
QUANTITY=65
ENTRY=Decimal("12.92")
TARGET_LIMIT=Decimal("10.50")
TICK=Decimal("0.05")
MAX_PLANNED_LOSS=Decimal("800")
DEFAULT_DRAFT="/var/lib/optionx-v7/manual-exit-v30.sqlite3"

class PreviewBlocked(ValueError):
    pass


def _decimal(v, name):
    if isinstance(v,bool):
        raise PreviewBlocked(name+"_INVALID")
    try:
        d=Decimal(str(v))
    except (ValueError,TypeError,InvalidOperation):
        raise PreviewBlocked(name+"_INVALID") from None
    if not d.is_finite() or d<=0:
        raise PreviewBlocked(name+"_INVALID")
    return d


def preview_manual_exit(*,positions,orders,ltp,as_of,verified_owner=True):
    if verified_owner is not True:
        raise PreviewBlocked("OWNER_UNVERIFIED")
    if not isinstance(as_of,datetime) or as_of.utcoffset() is None:
        raise PreviewBlocked("AWARE_SNAPSHOT_TIME_REQUIRED")
    if (datetime.now(timezone.utc)-as_of).total_seconds() not in range(0,11):
        raise PreviewBlocked("BROKER_SNAPSHOT_NOT_FRESHLY_RECEIVED")
    if not isinstance(orders,list) or not isinstance(positions,list):
        raise PreviewBlocked("BROKER_BOOK_SHAPE_INVALID")
    long=assess_manual_positions(positions,orders)
    if len(long)!=1 or long[0]["contract"]!=SYMBOL or long[0]["instrumentToken"]!=TOKEN:
        raise PreviewBlocked("MANUAL_CONTRACT_NOT_EXACTLY_MATCHED")
    if long[0]["netLongQuantity"]!=QUANTITY:
        raise PreviewBlocked("POSITION_QUANTITY_CHANGED")
    if long[0]["activeSellOrders"]!=0:
        raise PreviewBlocked("ACTIVE_SELL_CONFLICT")
    # Unknown NFO orderbook statuses must not be interpreted as cancelled.
    for order in orders:
        if order.get("symbol")==SYMBOL and (not order.get("statusKnown",False)
            or order.get("status")=="UNKNOWN"):
            raise PreviewBlocked("UNRECOGNIZED_ORDER_STATE")
    price=_decimal(ltp,"LTP")
    if TARGET_LIMIT%TICK:
        raise PreviewBlocked("LIMIT_OFF_TICK")
    # A sell limit is NOT a stop: price must be at/above limit to be executable
    # in principle; last traded price is not guaranteed available bid.
    if price<TARGET_LIMIT:
        raise PreviewBlocked("LTP_BELOW_DRAFT_SELL_LIMIT")
    premium_loss=(ENTRY-TARGET_LIMIT)*QUANTITY
    if premium_loss>MAX_PLANNED_LOSS:
        raise PreviewBlocked("DRAFT_PREMIUM_LOSS_OVER_BUDGET")
    return {
        "broker":"Angel","exchange":"NFO","contract":SYMBOL,"token":TOKEN,
        "quantity":QUANTITY,"side":"SELL","orderType":"LIMIT",
        "limit":str(TARGET_LIMIT),"ltpSnapshot":str(price),
        "averageBuyOwnerDeclared":str(ENTRY),
        "premiumLossAtLimitExCharges":str(premium_loss),
        "brokerSnapshotReceivedUtc":as_of.isoformat(),
        "orderbookActiveSells":0,
        "brokerOrderPermissionVerified":False,
        "exchangeFeedTimestampVerified":False,
        "liveBidAskVerified":False,"actualFeesVerified":False,
        "manualPositionAutoAdopted":False,
        "submittedOrder":False,"canSubmitOrder":False,"realOrdersEnabled":False,
        "status":"PREVIEW_ONLY_SOURCE_LOCKED",
    }


def store_local_preview(path, *, owner_id, preview, now):
    """Crash-consistent local *draft* audit, never an order-send journal.

    Existing files must be owned by the current restricted OS user and mode
    0600; no symlinks; database in dedicated private directory. No secret
    or broker JWT is ever persisted.
    """
    dest=Path(path)
    if not dest.is_absolute() or dest.is_symlink():
        raise PreviewBlocked("PRIVATE_AUDIT_ABSOLUTE_PATH_REQUIRED")
    parent=dest.parent
    if not parent.is_dir() or parent.is_symlink():
        raise PreviewBlocked("PRIVATE_AUDIT_DIRECTORY_MISSING")
    directory=parent.stat()
    if directory.st_uid!=os.geteuid() or directory.st_mode&0o077:
        raise PreviewBlocked("PRIVATE_AUDIT_DIRECTORY_PERMISSIONS")
    if dest.exists():
        meta=dest.stat()
        if meta.st_uid!=os.geteuid() or meta.st_mode&0o077 or not stat.S_ISREG(meta.st_mode):
            raise PreviewBlocked("PRIVATE_AUDIT_FILE_PERMISSIONS")
    if preview.get("canSubmitOrder") is not False or preview.get("submittedOrder") is not False:
        raise PreviewBlocked("DRAFT_INVARIANT_BROKEN")
    # A generated identifier is not an authorization token, and multiple
    # draft records never authorize any real order.
    old_umask=os.umask(0o077)
    try:
        db=sqlite3.connect(str(dest),timeout=10,isolation_level=None)
        try:
            db.execute("PRAGMA synchronous=FULL")
            db.execute("PRAGMA journal_mode=DELETE")
            db.execute("""CREATE TABLE IF NOT EXISTS previews
              (draft_id TEXT PRIMARY KEY, owner_digest TEXT NOT NULL,
               recorded_utc TEXT NOT NULL, payload_json TEXT NOT NULL,
               status TEXT NOT NULL CHECK(status='PREVIEW_ONLY_SOURCE_LOCKED'))""")
            db.execute("BEGIN IMMEDIATE")
            row_id=str(uuid.uuid4())
            digest=hashlib.sha256(owner_id.encode("utf8")).hexdigest()
            db.execute("INSERT INTO previews VALUES(?,?,?,?,?)",
                (row_id,digest,now.isoformat(),json.dumps(preview,sort_keys=True),
                 "PREVIEW_ONLY_SOURCE_LOCKED"))
            db.commit()
        except Exception:
            db.rollback()
            raise
        finally:
            db.close()
    finally:
        os.umask(old_umask)
    return row_id


def run():
    owner=None
    try:
        if os.geteuid()==0:
            raise PreviewBlocked("NON_ROOT_OWNER_SESSION_REQUIRED")
        owner,client=_config()
        verify_login(owner,client)
        positions=read_book(owner,"positions")["positions"]
        orders=read_book(owner,"orderbook")["orders"]
        price=fetch_ltp(owner,symbol=SYMBOL,token=TOKEN)
        observed=datetime.now(timezone.utc)
        draft=preview_manual_exit(positions=positions,orders=orders,
                                  ltp=price,as_of=observed)
        # No default journal write unless pre-provisioned private file
        # destination, to keep existing infrastructure untouched.
        print("V30_MANUAL_LIMIT_EXIT_PREVIEW: PASS")
        for name in ("contract","token","quantity","side","orderType","limit",
                     "ltpSnapshot","premiumLossAtLimitExCharges","status"):
            print(name.upper()+":",draft[name])
        print("CURRENT_BROKER_OWNER_POSITION_RECHECK: PASS")
        print("OWNER_QUOTED_AVG_ENTRY:",ENTRY)
        print("FEED_TIMESTAMP_AND_LIVE_BID_VERIFIED: NO")
        print("ORDER_WRITE_API_AND_FEES_VERIFIED: NO")
        print("ORDER_SUBMITTED: NO | REAL_ORDERS: OFF")
        return 0
    except Exception:
        print("V30_MANUAL_LIMIT_EXIT_PREVIEW: BLOCKED")
        print("ORDER_SUBMITTED: NO | REAL_ORDERS: OFF")
        return 2
    finally:
        if owner:
            try: angel_gateway.disconnect(owner)
            except Exception: pass


if __name__=="__main__":
    raise SystemExit(run())
