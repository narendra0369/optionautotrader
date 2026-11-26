"""V48 Render-to-AWS signed owner control relay (STOP/review only).

Use ONLY after the website's Supabase bearer session was verified against
Supabase Auth AND matched the configured owner. The HMAC secret belongs in
Render/AWS server secret stores, never the browser or repository. No trading.
"""
from __future__ import annotations
from datetime import datetime, timezone
import json
import os
import re
import secrets
import ssl
import urllib.parse
import urllib.request
import urllib.error
import socket
from .signed_owner_commands_v48 import sign_from_trusted_gateway

class RelayBlocked(ValueError):pass

def forward_owner_control(*, verified_owner_id, expected_owner_id,
                          action, signing_key, aws_endpoint, now=None,
                          opener=None):
    if not isinstance(verified_owner_id,str) or verified_owner_id!=expected_owner_id:
        raise RelayBlocked("VERIFIED_OWNER_REQUIRED")
    if action not in ("EMERGENCY_STOP","REQUEST_UNLOCK_REVIEW","REQUEST_ACTIVATE_LIVE"):
        raise RelayBlocked("ACTION_NOT_ALLOWED")
    if not isinstance(aws_endpoint,str):
        raise RelayBlocked("AWS_ENDPOINT_NOT_CONFIGURED")
    url=urllib.parse.urlsplit(aws_endpoint)
    if (url.scheme!="https" or not url.hostname or url.username or url.password
        or url.query or url.fragment or url.path!="/v48/owner/control"
        or url.port not in (443,None)):
        raise RelayBlocked("PINNED_HTTPS_AWS_ENDPOINT_REQUIRED")
    instant=now or datetime.now(timezone.utc)
    if not isinstance(instant,datetime) or instant.utcoffset() is None:
        raise RelayBlocked("AWARE_TIME_REQUIRED")
    envelope={"v":1,"owner":verified_owner_id,"action":action,
              "nonce":secrets.token_urlsafe(24),
              "issued_at":int(instant.timestamp())}
    signature=sign_from_trusted_gateway(
       envelope,key=signing_key,owner_verified=True)
    body=json.dumps(envelope,sort_keys=True,separators=(",",":")).encode("utf-8")
    req=urllib.request.Request(aws_endpoint,data=body,method="POST",
        headers={"Content-Type":"application/json","X-OptionX-Signature":signature,
                 "Accept":"application/json","User-Agent":"OptionX-Owner-Relay/48"})
    try:
        if opener is not None:
            response=opener(req,timeout=7)
        else:
            context=ssl.create_default_context()
            response=urllib.request.urlopen(req,timeout=7,context=context)
        with response as stream:
            if getattr(stream,"status",0)!=200:
                raise RelayBlocked("AWS_CONTROL_NON_SUCCESS")
            raw=stream.read(4097)
        if len(raw)>4096: raise RelayBlocked("AWS_RESPONSE_OVERSIZE")
        result=json.loads(raw)
        if not isinstance(result,dict) or result.get("commandAccepted") is not True:
            raise RelayBlocked("AWS_CONTROL_NOT_ACKNOWLEDGED")
        if result.get("liveOrdersEnabled") is not False:
            raise RelayBlocked("AWS_CONTROL_RESPONSE_INCONSISTENT")
        return {"awsControlAcknowledged":True,"mode":result.get("mode"),
                "activationBlocked":result.get("mode")=="BLOCKED",
                "liveOrdersEnabled":False,"canSubmitOrder":False}
    except urllib.error.HTTPError as exc:
        # Reveal only upstream HTTP status classification, never response,
        # request signature, bearer credentials or the HMAC secret.
        if exc.code in (401,403):
            raise RelayBlocked("AWS_SIGNED_COMMAND_REJECTED") from None
        if exc.code == 404:
            raise RelayBlocked("AWS_CONTROL_ROUTE_NOT_FOUND") from None
        if exc.code == 503:
            raise RelayBlocked("AWS_RECEIVER_INTERNAL_UNAVAILABLE") from None
        raise RelayBlocked("AWS_UPSTREAM_HTTP_ERROR") from None
    except (socket.timeout, TimeoutError):
        raise RelayBlocked("AWS_CONNECTION_TIMEOUT") from None
    except (urllib.error.URLError, ConnectionError, OSError):
        raise RelayBlocked("AWS_TLS_OR_NETWORK_ERROR") from None
    except (ValueError, UnicodeDecodeError) as exc:
        if isinstance(exc,RelayBlocked): raise
        raise RelayBlocked("AWS_RESPONSE_INVALID") from None
