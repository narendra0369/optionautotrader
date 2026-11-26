"""V45 isolated PostgreSQL MOCK_ONLY atomic reservation adapter.

This code is ONLY for a separately created staging DB and cannot send orders.
Never point at the real Supabase database. No SQL credentials are stored.
SQL transaction must be externally managed and autocommit disabled.
"""
from __future__ import annotations
from datetime import datetime
from decimal import Decimal, InvalidOperation
from hashlib import sha256
import json
import re
from uuid import UUID

class StageReservationBlocked(RuntimeError): pass

_ALLOWED_FIELDS=frozenset(("symbol","token","side","order_type","quantity","price"))

def validate_intent(intent):
    if not isinstance(intent,dict) or set(intent)!=_ALLOWED_FIELDS:
        raise StageReservationBlocked("INTENT_SHAPE_INVALID")
    if (not isinstance(intent["symbol"],str)
        or not re.fullmatch(r"[A-Z0-9]{6,80}",intent["symbol"])):
        raise StageReservationBlocked("SYMBOL_INVALID")
    if not isinstance(intent["token"],str) or not re.fullmatch(r"[0-9]{1,20}",intent["token"]):
        raise StageReservationBlocked("TOKEN_INVALID")
    if (intent["side"] not in ("SELL","BUY")
        or intent["order_type"] not in ("LIMIT","STOPLOSS_LIMIT")):
        raise StageReservationBlocked("ORDER_TYPE_INVALID")
    if type(intent["quantity"]) is not int or not 0<intent["quantity"]<=100000:
        raise StageReservationBlocked("QUANTITY_INVALID")
    try: price=Decimal(str(intent["price"]))
    except (TypeError,ValueError,InvalidOperation):
        raise StageReservationBlocked("PRICE_INVALID") from None
    if not price.is_finite() or price<=0 or price.as_tuple().exponent < -4:
        raise StageReservationBlocked("PRICE_INVALID")
    clean=dict(intent,price=str(price))
    payload=json.dumps(clean,sort_keys=True,separators=(",",":")).encode("utf-8")
    return clean,sha256(payload).hexdigest()

def mock_reserve(conn,*,owner_id,intent_key,intent,now):
    """Serializes owner guard+intent, always canSubmitOrder=False."""
    try: owner=str(UUID(str(owner_id)))
    except (TypeError,ValueError,AttributeError):
        raise StageReservationBlocked("OWNER_INVALID") from None
    if not isinstance(intent_key,str) or not re.fullmatch(r"[A-Za-z0-9_-]{8,96}",intent_key):
        raise StageReservationBlocked("KEY_INVALID")
    if not isinstance(now,datetime) or now.utcoffset() is None:
        raise StageReservationBlocked("AWARE_TIME_REQUIRED")
    clean,payload_hash=validate_intent(intent)
    if getattr(conn,"autocommit",True) is not False:
        raise StageReservationBlocked("TRANSACTIONAL_CONNECTION_REQUIRED")
    try:
        with conn.cursor() as cur:
            cur.execute("SET TRANSACTION ISOLATION LEVEL SERIALIZABLE READ WRITE")
            cur.execute("""SELECT state,new_orders_blocked FROM optionx_exec_stage.guard
                           WHERE owner_id=%s FOR UPDATE""",(owner,))
            guard=cur.fetchone()
            if guard is None or guard[0]!="MOCK_ONLY" or guard[1] is not True:
                raise StageReservationBlocked("STAGING_MOCK_GUARD_NOT_ENABLED")
            # The state MOCK_ONLY is impossible in production optionx_private.
            cur.execute("""SELECT payload_hash,state FROM optionx_exec_stage.order_intents
                           WHERE owner_id=%s AND intent_key=%s FOR UPDATE""",
                        (owner,intent_key))
            found=cur.fetchone()
            if found is not None:
                if found[0]!=payload_hash:
                    raise StageReservationBlocked("KEY_CONFLICT_DIFFERENT_ORDER")
                state=found[1]
                result="EXISTING_NO_RESEND"
            else:
                cur.execute("""INSERT INTO optionx_exec_stage.order_intents
                   (owner_id,intent_key,payload_hash,symbol,token,side,
                    order_type,quantity,price,state)
                   VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,'RESERVED_UNSENT')""",
                   (owner,intent_key,payload_hash,clean["symbol"],clean["token"],
                    clean["side"],clean["order_type"],clean["quantity"],clean["price"]))
                cur.execute("""INSERT INTO optionx_exec_stage.order_events
                   (owner_id,intent_key,event) VALUES(%s,%s,'RESERVED')""",
                   (owner,intent_key))
                state="RESERVED_UNSENT"
                result="STAGING_RESERVED_NO_SEND"
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    return {"state":state,"result":result,"canSubmitOrder":False,
            "canRetry":False,"liveOrdersEnabled":False}

def mock_seal_unknown(conn,*,owner_id,intent_key):
    try: owner=str(UUID(str(owner_id)))
    except (TypeError,ValueError,AttributeError):
        raise StageReservationBlocked("OWNER_INVALID") from None
    if not isinstance(intent_key,str) or not re.fullmatch(r"[A-Za-z0-9_-]{8,96}",intent_key):
        raise StageReservationBlocked("KEY_INVALID")
    if getattr(conn,"autocommit",True) is not False:
        raise StageReservationBlocked("TRANSACTIONAL_CONNECTION_REQUIRED")
    try:
        with conn.cursor() as cur:
            cur.execute("SET TRANSACTION ISOLATION LEVEL SERIALIZABLE READ WRITE")
            cur.execute("""SELECT state,new_orders_blocked FROM optionx_exec_stage.guard
                WHERE owner_id=%s FOR UPDATE""",(owner,))
            guard=cur.fetchone()
            if guard is None or guard[0]!="MOCK_ONLY" or guard[1] is not True:
                raise StageReservationBlocked("STAGING_MOCK_GUARD_NOT_ENABLED")
            cur.execute("""SELECT state FROM optionx_exec_stage.order_intents
                WHERE owner_id=%s AND intent_key=%s FOR UPDATE""",(owner,intent_key))
            state_row=cur.fetchone()
            if not state_row:
                raise StageReservationBlocked("RESERVATION_NOT_FOUND")
            if state_row[0]=="RESERVED_UNSENT":
                cur.execute("""UPDATE optionx_exec_stage.order_intents
                    SET state='MAY_HAVE_SENT_RECONCILE'
                    WHERE owner_id=%s AND intent_key=%s""",(owner,intent_key))
                cur.execute("""INSERT INTO optionx_exec_stage.order_events
                    (owner_id,intent_key,event) VALUES(%s,%s,'SEALED_UNKNOWN')""",
                    (owner,intent_key))
            elif state_row[0]!="MAY_HAVE_SENT_RECONCILE":
                raise StageReservationBlocked("TRANSITION_NOT_ALLOWED")
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    return {"state":"MAY_HAVE_SENT_RECONCILE","canSubmitOrder":False,
            "canRetry":False,"liveOrdersEnabled":False}
