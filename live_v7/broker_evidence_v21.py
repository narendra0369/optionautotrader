"""V21 strict broker-book evidence proofs. Pure functions; NO network/orders.

Trade book fields follow Angel One SmartAPI official Get Trade Book response:
exchange, orderid, fillid, fillsize, fillprice, tradingsymbol,
transactiontype. Broker source/owner authentication must be established
INDEPENDENTLY. Never infer OptionX ownership from a symbol or position.
A successful proof is still NOT approval to submit a live order.
"""
from __future__ import annotations

from datetime import datetime, timedelta
from decimal import Decimal, InvalidOperation
import re
from typing import Mapping, Sequence, Any

MAX_AGE=timedelta(seconds=10)
_ID=re.compile(r"^[A-Za-z0-9_-]{4,96}$")
_SYMBOL=re.compile(r"^[A-Z0-9._-]{4,72}$")

class EvidenceError(ValueError):
    pass

def _timestamp(now,as_of):
    if not all(isinstance(x,datetime) and x.utcoffset() is not None for x in (now,as_of)):
        raise EvidenceError("BROKER_TIME_NOT_TRUSTED")
    if not timedelta(0)<=now-as_of<=MAX_AGE:
        raise EvidenceError("BROKER_EVIDENCE_STALE")

def _quantity(value):
    if type(value) is int:
        number=value
    elif isinstance(value,str) and re.fullmatch(r"\d+",value):
        number=int(value)
    else:
        raise EvidenceError("INVALID_BROKER_QUANTITY")
    if number < 0 or number > 2_000_000_000:
        raise EvidenceError("INVALID_BROKER_QUANTITY")
    return number

def _price(value):
    if isinstance(value,bool) or not isinstance(value,(str,int,Decimal)):
        raise EvidenceError("INVALID_BROKER_PRICE")
    try:
        p=Decimal(value)
    except (InvalidOperation,TypeError,ValueError):
        raise EvidenceError("INVALID_BROKER_PRICE") from None
    if not p.is_finite() or p<=0:
        raise EvidenceError("INVALID_BROKER_PRICE")
    return p

def _id(v):
    if not isinstance(v,str) or not _ID.fullmatch(v):
        raise EvidenceError("INVALID_BROKER_ID")
    return v

def confirm_tradebook_fills(*, owned_order_id: str, symbol: str,
                            expected_quantity: int, orderbook_filled_quantity:int,
                            raw_trade_rows: Sequence[Mapping[str,Any]],
                            source_authenticated:bool, owner_authenticated:bool,
                            snapshot_at:datetime, now:datetime) -> dict[str,Any]:
    """Reconcile exact broker trade IDs against ONE OptionX-owned order ID.

    Other valid orders are deliberately excluded, not adopted. Unknown NFO
    trades are rejected rather than silently skipped. Requires independent
    trusted GET transport and a separately durable owned ID from the ledger.
    """
    if source_authenticated is not True or owner_authenticated is not True:
        raise EvidenceError("OWNER_AND_BROKER_AUTH_REQUIRED")
    _timestamp(now,snapshot_at)
    _id(owned_order_id)
    if not isinstance(symbol,str) or not _SYMBOL.fullmatch(symbol):
        raise EvidenceError("INVALID_CONTRACT")
    if (type(expected_quantity) is not int or expected_quantity<=0 or
        type(orderbook_filled_quantity) is not int or
        not 0<=orderbook_filled_quantity<=expected_quantity):
        raise EvidenceError("INVALID_ORDERBOOK_FILL")
    if not isinstance(raw_trade_rows,(list,tuple)) or len(raw_trade_rows)>500:
        raise EvidenceError("TRADEBOOK_ROWS_INVALID")
    total=0
    value=Decimal(0)
    trades=0
    ids=set()
    for row in raw_trade_rows:
        if not isinstance(row,Mapping):
            raise EvidenceError("TRADEBOOK_ROW_INVALID")
        exch=row.get("exchange")
        if exch in ("NSE","BSE","BFO","CDS","MCX","NCDEX"):
            continue
        if exch!="NFO":
            raise EvidenceError("UNKNOWN_TRADE_EXCHANGE")
        order_id=_id(row.get("orderid"))
        if order_id != owned_order_id:
            # Broker order belongs to a separate order; never infer ownership
            # by matching symbol. Elsewhere account exposure stays blocked.
            continue
        if row.get("transactiontype")!="BUY" or row.get("tradingsymbol")!=symbol:
            raise EvidenceError("OWNED_FILL_CONTRACT_OR_SIDE_MISMATCH")
        fillid=_id(row.get("fillid"))
        if fillid in ids:
            raise EvidenceError("DUPLICATE_FILL_ID")
        ids.add(fillid)
        qty=_quantity(row.get("fillsize"))
        if qty<=0:
            raise EvidenceError("ZERO_SIZED_FILL")
        price=_price(row.get("fillprice"))
        total+=qty
        value+=price*qty
        trades+=1
        if total>expected_quantity:
            raise EvidenceError("TRADEBOOK_OVERFILLED")
    if total!=orderbook_filled_quantity:
        raise EvidenceError("BROKER_TRADEBOOK_ORDERBOOK_MISMATCH")
    return {"brokerFillProof":total>0,"verifiedQuantity":total,
            "weightedAverageFillPrice":str(value/total) if total else None,
            "distinctFillCount":trades,"requiresProtection":total>0,
            "canSubmitOrder":False,"liveOrdersEnabled":False}

def confirm_native_stop(*, owned_stop_order_id:str, symbol:str, instrument_token:str,
                        open_quantity:int, orderbook_row:Mapping[str,Any],
                        source_authenticated:bool, owner_authenticated:bool,
                        snapshot_at:datetime,now:datetime)->dict[str,Any]:
    """Strict broker-observed active Angel STOPLOSS_LIMIT exit SELL.

    A stop order placed in an account does NOT guarantee it will execute,
    especially across gaps; and a protective stop is not an OCO target.
    """
    if source_authenticated is not True or owner_authenticated is not True:
        raise EvidenceError("OWNER_AND_BROKER_AUTH_REQUIRED")
    _timestamp(now,snapshot_at)
    _id(owned_stop_order_id)
    if type(open_quantity) is not int or open_quantity<=0:
        raise EvidenceError("OPEN_POSITION_QUANTITY_INVALID")
    if not isinstance(orderbook_row,Mapping):
        raise EvidenceError("STOP_ORDERBOOK_ROW_MISSING")
    row=orderbook_row
    if row.get("orderid")!=owned_stop_order_id:
        raise EvidenceError("STOP_ID_NOT_OWNED")
    if row.get("exchange")!="NFO" or row.get("tradingsymbol")!=symbol:
        raise EvidenceError("STOP_CONTRACT_MISMATCH")
    if not isinstance(instrument_token,str) or not instrument_token:
        raise EvidenceError("EXPECTED_INSTRUMENT_TOKEN_MISSING")
    if str(row.get("symboltoken"))!=instrument_token:
        raise EvidenceError("STOP_INSTRUMENT_TOKEN_MISMATCH")
    if row.get("transactiontype")!="SELL":
        raise EvidenceError("STOP_NOT_EXIT_SELL")
    if (str(row.get("variety","")).upper()!="STOPLOSS" or
        str(row.get("ordertype","")).upper()!="STOPLOSS_LIMIT"):
        raise EvidenceError("NOT_BROKER_NATIVE_STOPLOSS_LIMIT")
    status=str(row.get("orderstatus",row.get("status",""))).lower().strip()
    # Existing broker normalization maps trigger pending to PENDING, but
    # that alone is not proof. Require raw recognizable stop status.
    if status not in ("trigger pending","open"):
        raise EvidenceError("BROKER_STOP_NOT_ACTIVE")
    qty=_quantity(row.get("quantity"))
    filled=_quantity(row.get("filledshares"))
    unfilled=_quantity(row.get("unfilledshares"))
    if qty<=0 or filled+unfilled!=qty or unfilled!=open_quantity:
        raise EvidenceError("STOP_UNPROTECTED_QUANTITY")
    trigger=_price(row.get("triggerprice"))
    limit=_price(row.get("price"))
    if not limit<=trigger:
        raise EvidenceError("STOP_LIMIT_TRIGGER_RELATION_INVALID")
    return {"stopObservedInBrokerBook":True,"verifiedRemainingQuantity":unfilled,
            "stopTrigger":str(trigger),"stopLimit":str(limit),
            "stopFillGuaranteed":False,"targetOCOCertified":False,
            "canSubmitOrder":False,"liveOrdersEnabled":False}
