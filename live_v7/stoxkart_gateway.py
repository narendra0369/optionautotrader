"""OptionX V7: Stoxkart Superr API owner-bound ephemeral login + READ-ONLY profile.

Official references:
https://developers.stoxkart.com/api-documentation/login
https://developers.stoxkart.com/api-documentation/portfolio

No broker order placement/modification/cancellation methods. Profile login does
not permit unattended algorithmic orders under the broker's API terms.
No secrets go to GitHub/Supabase/logs. Pending API secret exists in RAM for at
most 10 minutes and is consumed once; access token stays in RAM for 15 minutes.

For sandbox/test, inject a mocked fetch. Live login can only complete after the
user obtains own Stoxkart API credentials, creates a developer app registering
the exact Stoxkart callback URL, and signs in on the BROKER's login page.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import os
import re
import secrets
import ssl
import threading
import time
from datetime import datetime, timezone
from urllib.parse import quote
from urllib.request import Request, HTTPRedirectHandler, HTTPSHandler, build_opener
from urllib.error import HTTPError, URLError

import angel_gateway

API_ORIGIN = "https://openapi.stoxkart.com"
OFFICIAL_LOGIN_ORIGIN = "https://superrtrade.stoxkart.com"
STAGING_CALLBACK = "https://optionx-v7-frontend-test-staging.onrender.com/stoxkart_callback.html"
TIMEOUT = 9
BODY_LIMIT = 262_144
PENDING_TTL = 10 * 60
SESSION_TTL = 15 * 60
ATTEMPT_WINDOW = 15 * 60
MAX_ATTEMPTS = 3
LOCK = threading.RLock()
_PENDING: dict[str, dict] = {}
_SESSIONS: dict[str, dict] = {}
_ATTEMPTS: dict[str, list[float]] = {}
_API_KEY = re.compile(r"^[A-Za-z0-9_-]{8,128}$")
_CLIENT = re.compile(r"^[A-Za-z0-9_-]{4,32}$")
_OPAQUE = re.compile(r"^[A-Za-z0-9._~-]{20,512}$")
_FLOW = re.compile(r"^[A-Za-z0-9_-]{20,128}$")

class StoxkartAuthError(ValueError):
    """Public-safe error, never include a secret or raw broker payload."""

class _RejectRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise StoxkartAuthError("Broker changed API destination; login not accepted")

def _post_or_get(method: str, path: str, *, payload=None, api_key="", token="", fetch=None) -> dict:
    if (method, path) not in (
        ("POST", "/auth/token"), ("GET", "/auth/profile"),
        ("GET", "/portfolio/positions"),
    ):
        raise StoxkartAuthError("Unsupported Stoxkart read-only/login endpoint")
    headers = {"Accept": "application/json", "Content-Type": "application/json",
               "User-Agent": "OptionX-ReadOnly-Stoxkart/7.0"}
    if method == "GET":
        if not _API_KEY.fullmatch(api_key) or not _OPAQUE.fullmatch(token):
            raise StoxkartAuthError("Read-only Stoxkart session invalid")
        headers.update({"x-Api-key": api_key, "X-Access-Token": token,
                        "x-Platform": "api"})
    body = json.dumps(payload, separators=(",", ":")).encode("utf-8") if payload is not None else None
    req = Request(API_ORIGIN + path, data=body, headers=headers, method=method)
    try:
        if fetch is None:
            response = build_opener(_RejectRedirect(),
                                    HTTPSHandler(context=ssl.create_default_context())).open(req, timeout=TIMEOUT)
        else:
            response = fetch(req, timeout=TIMEOUT)
        with response as r:
            if getattr(r, "status", 200) != 200:
                raise StoxkartAuthError("Stoxkart did not accept this read-only/login request")
            raw = r.read(BODY_LIMIT + 1)
        if len(raw) > BODY_LIMIT:
            raise StoxkartAuthError("Broker response exceeded safety limit")
        data = json.loads(raw)
    except StoxkartAuthError:
        raise
    except (HTTPError, URLError, ValueError, OSError, TimeoutError, UnicodeDecodeError) as exc:
        raise StoxkartAuthError("Stoxkart login/read unavailable or rejected") from None
    if not isinstance(data, dict) or str(data.get("status", "")).lower() != "success":
        raise StoxkartAuthError("Stoxkart rejected login/read; check account and API app")
    return data

def _now(now):
    return time.time() if now is None else float(now)

def _owner(user_id: str) -> None:
    if not angel_gateway._owner_bound(user_id):
        raise PermissionError("Only the configured OptionX owner may inspect personal Stoxkart account")

def _mask(client: str) -> str:
    return "*" * max(2, len(client)-2) + client[-2:]

def _clean(user: str, now: float):
    with LOCK:
        pending = _PENDING.get(user)
        if pending and pending["expires"] <= now:
            _PENDING.pop(user, None)
        session = _SESSIONS.get(user)
        if session and session["expires"] <= now:
            _SESSIONS.pop(user, None)

def status(user_id: str, *, now=None) -> dict:
    current = _now(now)
    allowed = angel_gateway._owner_bound(user_id)
    if allowed:
        _clean(user_id, current)
    with LOCK:
        session = _SESSIONS.get(user_id) if allowed else None
        pending = _PENDING.get(user_id) if allowed else None
    return {
        "provider": "Stoxkart Superr API", "ownerMatch": allowed,
        "ownerConfigured": bool(os.getenv("OPTIONX_OWNER_USER_ID", "").strip()),
        "connected": bool(session),
        "pendingLogin": bool(pending),
        "maskedClientCode": session["maskedClientCode"] if session else None,
        "verifiedAt": session["verifiedAt"] if session else None,
        "expiresAt": datetime.fromtimestamp(session["expires"], timezone.utc).isoformat() if session else None,
        "sessionStorage": "RAM_ONLY_15_MIN", "loginFlow": "STOXKART_OFFICIAL_BROKER_LOGIN",
        "readOnly": True, "canSubmitOrder": False, "orderExecutionEnabled": False,
        "unattendedAlgoApproved": False,
        "note": "Official broker login only. No API order placement and no automatic trading approval.",
    }

def start(user_id: str, body: dict, *, now=None) -> dict:
    """Create one ephemeral owner-scoped redirect-based login flow.

    API key is a public app identifier used only for the official login URL.
    Secret never leaves backend memory after this request is consumed.
    """
    _owner(user_id)
    current = _now(now)
    if not isinstance(body, dict) or set(body) != {"apiKey", "apiSecret", "clientCode"}:
        raise StoxkartAuthError("API key, API secret and expected broker client code required")
    api_key, secret, client = (body.get(k) for k in ("apiKey", "apiSecret", "clientCode"))
    if not isinstance(api_key, str) or not _API_KEY.fullmatch(api_key):
        raise StoxkartAuthError("Invalid Stoxkart app API key format")
    if not isinstance(secret, str) or not 16 <= len(secret) <= 256 or not secret.isascii():
        raise StoxkartAuthError("Invalid Stoxkart API secret format")
    if not isinstance(client, str) or not _CLIENT.fullmatch(client):
        raise StoxkartAuthError("Invalid Stoxkart broker client ID format")
    with LOCK:
        stamps = [t for t in _ATTEMPTS.get(user_id, []) if current - t < ATTEMPT_WINDOW]
        if len(stamps) >= MAX_ATTEMPTS:
            raise StoxkartAuthError("Too many login attempts. Try again after 15 minutes")
        stamps.append(current)
        _ATTEMPTS[user_id] = stamps
        flow_id = secrets.token_urlsafe(32)
        _SESSIONS.pop(user_id, None)
        _PENDING[user_id] = {
            "flowId": flow_id, "apiKey": api_key, "apiSecret": secret,
            "expectedClient": client.upper(), "expires": current + PENDING_TTL,
        }
    return {
        "loginUrl": OFFICIAL_LOGIN_ORIGIN + "/login?api_key=" + quote(api_key, safe=""),
        "flowId": flow_id,
        "registeredRedirectMustBe": STAGING_CALLBACK,
        "expiresInSeconds": PENDING_TTL,
        "canSubmitOrder": False, "orderExecutionEnabled": False,
        "note": "Use the official Stoxkart login page; do not enter your password in OptionX.",
    }

def complete(user_id: str, body: dict, *, fetch=None, now=None) -> dict:
    """Consume broker redirect token once; verify profile identity read-only."""
    _owner(user_id)
    current = _now(now)
    if not isinstance(body, dict) or set(body) != {"flowId", "requestToken"}:
        raise StoxkartAuthError("Expected Stoxkart one-time login flow and request token")
    flow_id, req_token = body["flowId"], body["requestToken"]
    if not isinstance(flow_id, str) or not _FLOW.fullmatch(flow_id):
        raise StoxkartAuthError("Invalid login flow")
    if not isinstance(req_token, str) or not _OPAQUE.fullmatch(req_token):
        raise StoxkartAuthError("Invalid broker redirect token")
    with LOCK:
        pending = _PENDING.pop(user_id, None)
    if not pending or pending["flowId"] != flow_id or current >= pending["expires"]:
        raise StoxkartAuthError("Login flow expired or mismatched; restart at OptionX")
    # Follow the broker's published Python SDK: HMAC key = api key + request
    # token, message = app secret. Do NOT log the signature or API token.
    key = (pending["apiKey"] + req_token).encode("utf-8")
    signature = hmac.new(key, pending["apiSecret"].encode("utf-8"), hashlib.sha256).hexdigest()
    result = _post_or_get("POST", "/auth/token", payload={
        "api_key": pending["apiKey"], "signature": signature,
        "req_token": req_token,
    }, fetch=fetch)
    data = result.get("data")
    if not isinstance(data, dict):
        raise StoxkartAuthError("Stoxkart session response was incomplete")
    access = data.get("access_token") or data.get("accessToken") or data.get("request_token")
    if not isinstance(access, str) or not _OPAQUE.fullmatch(access):
        raise StoxkartAuthError("Stoxkart did not issue a valid session token")
    profile = _post_or_get("GET", "/auth/profile",
                           api_key=pending["apiKey"], token=access, fetch=fetch)
    info = profile.get("data")
    broker_id = info.get("client_id") if isinstance(info, dict) else None
    if not isinstance(broker_id, str) or broker_id.upper() != pending["expectedClient"]:
        raise StoxkartAuthError("Broker verified profile does not match intended Stoxkart account")
    with LOCK:
        _SESSIONS[user_id] = {
            "apiKey": pending["apiKey"], "accessToken": access,
            "maskedClientCode": _mask(broker_id),
            "verifiedAt": datetime.fromtimestamp(current, timezone.utc).isoformat(),
            "expires": current + SESSION_TTL,
        }
    return status(user_id, now=current)

def disconnect(user_id: str) -> dict:
    _owner(user_id)
    with LOCK:
        _PENDING.pop(user_id, None)
        _SESSIONS.pop(user_id, None)
    return {
        "connected": False, "readOnly": True,
        "orderExecutionEnabled": False, "canSubmitOrder": False,
        "note": "Temporary OptionX session cleared; broker app sign-out is separate.",
    }

def positions(user_id: str, *, fetch=None, now=None) -> dict:
    """Read only nonzero NFO derivative positions; no order API methods."""
    _owner(user_id)
    current = _now(now)
    _clean(user_id, current)
    with LOCK:
        active = _SESSIONS.get(user_id, {}).copy()
    if not active:
        raise StoxkartAuthError("Stoxkart login session missing or expired")
    response = _post_or_get("GET", "/portfolio/positions",
                            api_key=active["apiKey"], token=active["accessToken"], fetch=fetch)
    rows = response.get("data")
    if not isinstance(rows, list) or len(rows) > 500:
        raise StoxkartAuthError("Unexpected broker positions payload")
    clean = []
    for row in rows:
        if not isinstance(row, dict):
            raise StoxkartAuthError("Malformed broker position row")
        if row.get("exchange") != "NFO":
            continue
        token = row.get("token")
        net = row.get("net_quantity")
        if not isinstance(token, (str, int)) or not re.fullmatch(r"[0-9]{1,24}", str(token)):
            raise StoxkartAuthError("Broker NFO instrument token unverified")
        if not isinstance(net, (str, int)) or not re.fullmatch(r"-?[0-9]{1,10}", str(net)):
            raise StoxkartAuthError("Broker NFO net quantity invalid")
        net = int(net)
        if net:
            clean.append({"token": str(token), "exchange": "NFO",
                          "netQuantity": net,
                          "optionType": str(row.get("option_type", ""))[:12]})
    return {
        "broker": "Stoxkart", "market": "NIFTY/BANKNIFTY", "positions": clean,
        "records": len(clean), "readOnly": True, "canSubmitOrder": False,
        "orderExecutionEnabled": False,
        "notice": "NFO positions only. No order placement, stop/target or brokerage approval.",
    }
