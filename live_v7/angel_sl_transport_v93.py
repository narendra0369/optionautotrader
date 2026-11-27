"""Angel One SmartAPI SL-LIMIT network adapter for certified V93 worker ONLY.

Not imported by website or public market API. Never performs order submission
unless V93 guarded_submit has already consumed a valid production permit.
SDK-equivalent fixed endpoint, strict TLS, no redirect, no retry, no secrets
printed; broker identity/session must be verified in same AWS process.
"""
from __future__ import annotations
import json, ssl, urllib.request, urllib.error
from collections.abc import Mapping
from live_v7.angel_books_readonly import read_book
import angel_gateway

ROOT="https://apiconnect.angelone.in"
PLACE="/rest/secure/angelbroking/order/v1/placeOrder"
MAX_BYTES=32768

class AngelExecutionTransportError(RuntimeError):pass

def send_one_sl_limit(*, owner, order, opener=None):
    """LOW-LEVEL transport; CALL ONLY from permit-protected worker.
    
    Access to this module must be restricted by production OS isolation.
    This is not itself an authorization mechanism.
    """
    if not isinstance(order,dict) or set(order)!={
        "variety","tradingsymbol","symboltoken","transactiontype","exchange",
        "ordertype","producttype","duration","price","triggerprice","quantity"}:
        raise AngelExecutionTransportError("EXACT_ORDER_FIELDS_REQUIRED")
    if (order["variety"]!="STOPLOSS" or order["ordertype"]!="STOPLOSS_LIMIT"
        or order["transactiontype"]!="SELL" or order["exchange"]!="NFO"
        or order["duration"]!="DAY"):
        raise AngelExecutionTransportError("ONLY_SELL_SL_LIMIT_ALLOWED")
    if not angel_gateway._owner_bound(owner):
        raise AngelExecutionTransportError("OWNER_NOT_VERIFIED")
    import time
    session=angel_gateway._clean_session(owner,time.time())
    if not session or not isinstance(session.get("jwt"),str) or not isinstance(session.get("apiKey"),str):
        raise AngelExecutionTransportError("ANGEL_VERIFIED_SESSION_REQUIRED")
    headers={
        "Authorization":"Bearer "+session["jwt"],
        "X-PrivateKey":session["apiKey"],
        "X-UserType":"USER","X-SourceID":"WEB",
        "Accept":"application/json","Content-Type":"application/json",
        "User-Agent":"OptionX-V93-Certified-SL-Worker/1.0",
        **angel_gateway.angel_client_identity_headers(allow_public_lookup=False)
    }
    req=urllib.request.Request(ROOT+PLACE,headers=headers,
        data=json.dumps(order,separators=(",",":"),sort_keys=True).encode("utf-8"),method="POST")
    if opener is None:
        opener=urllib.request.build_opener(
            angel_gateway.NoRedirect(),
            urllib.request.HTTPSHandler(context=ssl.create_default_context()))
    # After POST begins, any exception is an unknown broker outcome.
    # Caller MUST NOT retry without independent orderbook reconciliation.
    with opener.open(req,timeout=10) as response:
        if getattr(response,"status",200)!=200:
            raise AngelExecutionTransportError("BROKER_HTTP_NOT_ACCEPTED")
        payload=response.read(MAX_BYTES+1)
    if len(payload)>MAX_BYTES:
        raise AngelExecutionTransportError("BROKER_ACK_TOO_LARGE")
    body=json.loads(payload)
    if not isinstance(body,Mapping) or body.get("status") is not True:
        raise AngelExecutionTransportError("BROKER_DID_NOT_ACKNOWLEDGE")
    data=body.get("data")
    if not isinstance(data,Mapping):
        raise AngelExecutionTransportError("BROKER_ACK_MALFORMED")
    oid=data.get("orderid")
    if not isinstance(oid,str) or len(oid)<4 or len(oid)>96:
        raise AngelExecutionTransportError("BROKER_ORDER_ID_MISSING")
    return {"orderid":oid}

def fresh_orderbook(owner):
    return read_book(owner,"orderbook")["orders"]
