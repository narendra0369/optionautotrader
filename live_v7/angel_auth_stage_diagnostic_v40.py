"""V40 owner-bound Angel auth stage diagnostic, NO order transport.

One explicitly user-triggered authentication cycle. Reuses trusted
angel_gateway.connect unchanged, intercepting its two allowlisted HTTP stages
only to label failures. Prints no credentials, JWT, broker payload or account ID.
No automatic retries. Real orders remain source locked.
"""
from __future__ import annotations

import angel_gateway
from unittest.mock import patch
from live_v7.aws_angel_owner_reader import _config, verify_login

STAGES=frozenset(("CONFIG","PRIVATE_INPUT","LOGIN_API","PROFILE_API","OWNER_MATCH"))
PUBLIC_CODES=frozenset(("INVALID_PRIVATE_LOGIN_INPUT",
                        "BROKER_OWNER_PROFILE_NOT_VERIFIED"))
def blocked(stage, category="UNVERIFIED"):
    if stage not in STAGES:
        stage="PRIVATE_INPUT"
    if category not in ("UNVERIFIED","REJECTED_OR_UNAVAILABLE",
                        "LOCAL_INPUT_INVALID","OWNER_MISMATCH"):
        category="UNVERIFIED"
    return {"stage":stage,"category":category,"canSubmitOrder":False,
            "canRetry":False,"realOrdersEnabled":False}


def run():
    owner=None
    stage="CONFIG"
    observed={"stage":"PRIVATE_INPUT"}
    original=angel_gateway._post_or_get

    def label_only(method, endpoint, *args, **kwargs):
        # Never capture, display, save or inspect payload, key, password,
        # JWT or broker response. Only label the fixed endpoint method/path.
        if method=="POST" and endpoint==angel_gateway.LOGIN:
            observed["stage"]="LOGIN_API"
        elif method=="GET" and endpoint==angel_gateway.PROFILE:
            observed["stage"]="PROFILE_API"
        else:
            observed["stage"]="PRIVATE_INPUT"
        return original(method,endpoint,*args,**kwargs)

    try:
        owner,client=_config()
        stage="PRIVATE_INPUT"
        # One explicit call, no built-in retry; source-gateway validates
        # TOTP, client, owner binding, rate limit, login and profile.
        with patch.object(angel_gateway,"_post_or_get",label_only):
            verify_login(owner,client)
        print("V40_AUTHENTICATION: PASS",flush=True)
        print("V40_AUTH_STAGE: OWNER_MATCH",flush=True)
        return 0
    except Exception as exc:
        stage=observed["stage"] if stage!="CONFIG" else "CONFIG"
        # Do NOT emit exception text. Only classify fixed known local errors.
        reason="UNVERIFIED"
        if type(exc).__name__=="OwnerReaderError":
            if str(exc)=="INVALID_PRIVATE_LOGIN_INPUT":
                reason="LOCAL_INPUT_INVALID"
            elif str(exc)=="BROKER_OWNER_PROFILE_NOT_VERIFIED":
                reason="OWNER_MISMATCH"
        if isinstance(exc,angel_gateway.AuthError):
            reason="REJECTED_OR_UNAVAILABLE"
        result=blocked(stage,reason)
        print("V40_AUTHENTICATION: BLOCKED",flush=True)
        print("V40_BLOCK_STAGE:",result["stage"],flush=True)
        print("V40_FAILURE_CATEGORY:",result["category"],flush=True)
        return 2
    finally:
        if owner:
            try:
                angel_gateway.disconnect(owner)
            except Exception:
                pass
        print("NO_ORDER_SUBMITTED | REAL_ORDERS: OFF",flush=True)


if __name__=="__main__":
    raise SystemExit(run())
