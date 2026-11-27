"""V94 private Angel position product-type attestation.

The public normalized position intentionally omits producttype. Match a fresh
raw broker position to that normalized row before V93 planning. This does NOT
authorize any order, issue a permit, or turn on a production gate.
"""
from __future__ import annotations
from collections.abc import Mapping
from live_v7.angel_sl_guarded_worker_v93 import SLDispatchBlocked

def verified_position(*, normalized, raw_positions, expected_symbol,
                      expected_quantity):
    if not isinstance(normalized,list) or not isinstance(raw_positions,list):
        raise SLDispatchBlocked("POSITION_SOURCES_MISSING")
    if type(expected_quantity) is not int or expected_quantity <= 0:
        raise SLDispatchBlocked("POSITION_QUANTITY_INVALID")
    matching=[x for x in normalized if isinstance(x,Mapping)
              and x.get("symbol")==expected_symbol and x.get("exchange")=="NFO"]
    raw=[x for x in raw_positions if isinstance(x,Mapping)
         and x.get("tradingsymbol")==expected_symbol and x.get("exchange")=="NFO"]
    if len(matching)!=1 or len(raw)!=1:
        raise SLDispatchBlocked("POSITION_NOT_UNIQUE")
    norm,actual=matching[0],raw[0]
    if (norm.get("net_quantity")!=expected_quantity
        or str(norm.get("instrumentToken"))!=str(actual.get("symboltoken"))
        or str(actual.get("netqty"))!=str(expected_quantity)):
        raise SLDispatchBlocked("RAW_NORMALIZED_POSITION_MISMATCH")
    product=actual.get("producttype")
    if product not in ("CARRYFORWARD","INTRADAY"):
        raise SLDispatchBlocked("BROKER_PRODUCT_UNVERIFIED")
    return {**dict(norm),"producttype":product}
