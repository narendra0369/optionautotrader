"""OPTIONX V91 read-only manual long-position SELL SL-LIMIT draft inspection.

Angel authenticated profile, three GET books, one fixed POST GetLtpData
(read-only price query), then local validation. NO place/modify/cancel/exit.
Does not import trading executor. Never outputs credentials, client code,
order IDs or tokens. Use only interactively under owner account.
"""
from __future__ import annotations
import getpass, json, re, ssl, sys, urllib.request
from decimal import Decimal, InvalidOperation
from datetime import datetime, timezone
import angel_gateway
from live_v7.aws_angel_owner_reader import _config, verify_login
from live_v7.angel_books_readonly import read_three_books

LTP_PATH="/rest/secure/angelbroking/order/v1/getLtpData"

def dec(value):
    if isinstance(value, bool) or not isinstance(value,(str,int,float,Decimal)):
        raise ValueError("NONNUMERIC_PRICE")
    try: v=Decimal(str(value))
    except InvalidOperation: raise ValueError("INVALID_PRICE") from None
    if not v.is_finite() or v<=0: raise ValueError("NONPOSITIVE_PRICE")
    return v

def check_draft(*, position, orders, ltp, trigger=None, limit=None, tick=None):
    if not isinstance(position,dict): raise ValueError("POSITION_INVALID")
    qty=position.get("net_quantity")
    if type(qty) is not int or qty<=0: raise ValueError("SELL_SL_REQUIRES_LONG_POSITION")
    symbol=position.get("symbol")
    token=position.get("instrumentToken")
    if position.get("exchange")!="NFO" or not isinstance(symbol,str) or not isinstance(token,str) or not token:
        raise ValueError("NFO_SYMBOL_OR_TOKEN_INVALID")
    px=dec(ltp)
    if not isinstance(orders,list):raise ValueError("ORDER_BOOK_MISSING")
    if any(o.get("status") in {"OPEN","PENDING","PARTIALLY_FILLED","CANCEL_REQUESTED","UNKNOWN"}
           and o.get("symbol")==symbol for o in orders):
        raise ValueError("EXISTING_ACTIVE_OR_UNKNOWN_CONTRACT_ORDER")
    result={"exchange":"NFO","symbol":symbol,"net_quantity":qty,
            "ltp":str(px),"same_contract_active_orders":0,
            "trigger":None,"limit":None,"draft_price_check":"TRIGGER_NOT_SELECTED",
            "tick_validation":"UNVERIFIED","broker_lpp_validation":"UNVERIFIED",
            "can_place":False,"can_sell":False,"can_cancel":False}
    if trigger is None or limit is None: return result
    t,l=dec(trigger),dec(limit)
    # A SELL SL-LIMIT for a long holding normally triggers BELOW current LTP;
    # sell limit must be <= trigger, not an extreme marketable sell.
    if not (l<=t<px): raise ValueError("SELL_STOP_PRICE_RELATION_INVALID")
    if tick is not None:
        tk=dec(tick)
        if (t/tk)%1 or (l/tk)%1:raise ValueError("PRICE_NOT_ON_VERIFIED_TICK")
        result["tick_validation"]="PASS_SUPPLIED_VERIFIED_TICK"
    result.update(trigger=str(t),limit=str(l),
                  draft_price_check="RELATION_VALID_NOT_BROKER_CERTIFIED")
    return result

def get_ltp(owner,position):
    session=angel_gateway._clean_session(owner,datetime.now(timezone.utc).timestamp())
    if not session:raise ValueError("OWNER_RAM_SESSION_MISSING")
    payload=json.dumps({"exchange":"NFO","tradingsymbol":position["symbol"],
                        "symboltoken":position["instrumentToken"]},separators=(",",":")).encode()
    headers={"Authorization":"Bearer "+session["jwt"],"X-PrivateKey":session["apiKey"],
             "X-UserType":"USER","X-SourceID":"WEB","Content-Type":"application/json",
             "Accept":"application/json","User-Agent":"OptionX-ReadOnly-SL-Preflight/1.0"}
    headers.update(angel_gateway.angel_client_identity_headers(allow_public_lookup=False))
    req=urllib.request.Request("https://apiconnect.angelone.in"+LTP_PATH,
                               data=payload,headers=headers,method="POST")
    # POST is used by Angel for read-only LTP retrieval; path cannot place orders.
    opener=urllib.request.build_opener(angel_gateway.NoRedirect(),
              urllib.request.HTTPSHandler(context=ssl.create_default_context()))
    with opener.open(req,timeout=8) as response:
        if response.status!=200:raise ValueError("BROKER_LTP_HTTP_REJECTED")
        raw=response.read(16385)
    if len(raw)>16384:raise ValueError("LTP_RESPONSE_TOO_LARGE")
    reply=json.loads(raw)
    if not isinstance(reply,dict) or reply.get("status") is not True:
        raise ValueError("BROKER_LTP_REJECTED")
    body=reply.get("data")
    if not isinstance(body,dict) or body.get("tradingsymbol")!=position["symbol"] or str(body.get("symboltoken"))!=position["instrumentToken"]:
        raise ValueError("LTP_CONTRACT_MISMATCH")
    return dec(body.get("ltp"))

def run():
    owner=None
    try:
        owner,client=_config()
        verify_login(owner,client)
        books=read_three_books(owner)
        if books.get("allReadsSucceeded") is not True:raise ValueError("BROKER_BOOKS_INCOMPLETE")
        pos=[p for p in books["books"]["positions"]["positions"] if p.get("net_quantity")!=0]
        if len(pos)!=1:raise ValueError("EXPECTED_EXACTLY_ONE_NONZERO_NFO_POSITION")
        position=pos[0]
        orders=books["books"]["orderbook"]["orders"]
        print("ANGEL_AUTHENTICATED_BOOKS: PASS")
        ltp=get_ltp(owner,position)
        draft=check_draft(position=position,orders=orders,ltp=ltp)
        for k in ("exchange","symbol","net_quantity","ltp","same_contract_active_orders",
                  "draft_price_check","tick_validation","broker_lpp_validation","can_place"):
            print(k.upper()+":",draft[k],flush=True)
        print("SL_PRICE_INPUT: NOT_COLLECTED",flush=True)
        print("SL_ORDER_SUBMISSION: DISABLED",flush=True)
        return 0
    except Exception as exc:
        print("READONLY_PREFLIGHT_BLOCKED:",type(exc).__name__,flush=True)
        return 2
    finally:
        if owner:
            try:angel_gateway.disconnect(owner)
            except Exception:pass
        print("REAL_ORDER_ACTIONS: NONE",flush=True)

if __name__=="__main__":raise SystemExit(run())
