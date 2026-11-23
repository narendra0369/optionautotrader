"""OptionX V7 — restricted READ-ONLY broker transport (NOT CONNECTED).

No caller is wired to this module; no network requests are made by importing
it. Owner verification and credential retrieval MUST happen inside a trusted
backend before use. Do not expose this function on a public HTTP route.

Only fixed GET endpoints are permitted. This module cannot place, change or
cancel an order. It does not turn on any live execution capability.

Delta India private orders/positions APIs may require a Trading-scoped API
key even when reading. Obtain explicit approval and follow least privilege;
never infer that API access is permitted from a successful broker login.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import ssl
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Any, Mapping

HOSTS = {
    "Angel": "https://apiconnect.angelone.in",
    "Delta": "https://api.india.delta.exchange",
}
READ_ENDPOINTS = {
    "Angel": {
        "orderbook": "/rest/secure/angelbroking/order/v1/getOrderBook",
        "tradebook": "/rest/secure/angelbroking/order/v1/getTradeBook",
        "positions": "/rest/secure/angelbroking/order/v1/getPosition",
        "funds": "/rest/secure/angelbroking/user/v1/getRMS",
    },
    "Delta": {
        "orders": "/v2/orders",
        "positions": "/v2/positions/margined",
    },
}
MAX_RESPONSE = 512 * 1024
TIMEOUT_SECONDS = 7


class ReadOnlyTransportError(ValueError):
    pass


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise ReadOnlyTransportError("Broker redirect rejected")


@dataclass(frozen=True, repr=False)
class ServerOnlySession:
    broker: str
    owner_id: str
    api_key: str
    bearer_token: str = ""      # Angel only: existing temporary JWT
    api_secret: str = ""        # Delta only: never from browser after setup
    broker_account_verified: bool = False
    session_current: bool = False

    def __repr__(self) -> str:
        return "<ServerOnlySession redacted>"


def _session_valid(s: ServerOnlySession, resource: str, owner_id: str) -> str:
    if not isinstance(s, ServerOnlySession):
        raise ReadOnlyTransportError("Trusted broker session not available")
    if (
        not isinstance(owner_id, str)
        or not owner_id
        or s.owner_id != owner_id
        or s.broker_account_verified is not True
        or s.session_current is not True
    ):
        raise ReadOnlyTransportError("Broker owner or session not verified")
    route = READ_ENDPOINTS.get(s.broker, {}).get(resource)
    if route is None:
        raise ReadOnlyTransportError("Unknown or unsafe broker resource")
    if not isinstance(s.api_key, str) or not 8 <= len(s.api_key) <= 256:
        raise ReadOnlyTransportError("Broker key missing")
    if s.broker == "Angel" and (not isinstance(s.bearer_token, str) or len(s.bearer_token) < 20):
        raise ReadOnlyTransportError("Angel login token missing")
    if s.broker == "Delta" and (not isinstance(s.api_secret, str) or len(s.api_secret) < 20):
        raise ReadOnlyTransportError("Delta API secret missing")
    return route


def request_headers(s: ServerOnlySession, *, path: str, timestamp: int | None = None) -> dict[str, str]:
    """Create credentials for a FIXED GET resource, never arbitrary paths.

    Never write these headers to logs or return them to a browser.
    """
    if path not in READ_ENDPOINTS.get(s.broker, {}).values():
        raise ReadOnlyTransportError("Non-allowlisted resource blocked")
    base = {"Accept": "application/json", "User-Agent": "OptionX-ReadOnly-V7/1.0"}
    if s.broker == "Angel":
        base.update({
            "Authorization": "Bearer " + s.bearer_token,
            "X-PrivateKey": s.api_key,
            "X-UserType": "USER",
            "X-SourceID": "WEB",
        })
    elif s.broker == "Delta":
        stamp = int(time.time()) if timestamp is None else timestamp
        if isinstance(stamp, bool) or not isinstance(stamp, int) or stamp < 1:
            raise ReadOnlyTransportError("Invalid Delta request time")
        data = "GET" + str(stamp) + path
        sig = hmac.new(s.api_secret.encode("utf-8"), data.encode("utf-8"), hashlib.sha256).hexdigest()
        base.update({"api-key": s.api_key, "timestamp": str(stamp), "signature": sig})
    else:
        raise ReadOnlyTransportError("Unsupported broker")
    return base


def fetch_readonly(
    *,
    session: ServerOnlySession,
    resource: str,
    verified_owner_id: str,
    external_read_authorized_by_server: bool = False,
    fetch=None,
) -> Mapping[str, Any]:
    """Restricted GET; disabled by default and NOT called anywhere.

    A future owner-authenticated backend may pass a transport callback for
    isolated integration testing. Browser JSON must never set authorization
    flags. Redirects are disallowed to prevent credential exfiltration.
    """
    if external_read_authorized_by_server is not True:
        raise ReadOnlyTransportError("External private broker reads disabled")
    path = _session_valid(session, resource, verified_owner_id)
    req = urllib.request.Request(
        HOSTS[session.broker] + path,
        headers=request_headers(session, path=path),
        method="GET",
    )
    try:
        # Python's HTTPS default trust validation; no disabling TLS verification.
        if fetch is None:
            response = urllib.request.build_opener(
                NoRedirect(), urllib.request.HTTPSHandler(context=ssl.create_default_context())
            ).open(req, timeout=TIMEOUT_SECONDS)
        else:
            response = fetch(req, timeout=TIMEOUT_SECONDS)
        with response as handle:
            if getattr(handle, "status", 200) != 200:
                raise ReadOnlyTransportError("Broker read returned non-200")
            raw = handle.read(MAX_RESPONSE + 1)
        if len(raw) > MAX_RESPONSE:
            raise ReadOnlyTransportError("Broker response exceeded safe limit")
        parsed = json.loads(raw)
    except (urllib.error.HTTPError, urllib.error.URLError, OSError, TimeoutError,
            UnicodeDecodeError, ValueError, json.JSONDecodeError) as exc:
        # Never leak auth headers, server body, signatures or tokens.
        raise ReadOnlyTransportError("Broker read failed or permission denied") from None
    if not isinstance(parsed, dict):
        raise ReadOnlyTransportError("Broker returned unexpected response structure")
    # Raw broker data is server-only. Sanitize via broker_readonly.py before
    # returning any status to authenticated caller.
    return parsed


def public_capabilities() -> dict[str, object]:
    return {
        "stage": "SOURCE_ONLY_UNTESTED",
        "brokerReadIntegrationDeployed": False,
        "privateAccountReadCurrentlyEnabled": False,
        "liveOrderExecutionEnabled": False,
        "allowlistedResources": {broker: list(resources.keys()) for broker, resources in READ_ENDPOINTS.items()},
        "notice": "Requires server-verified owner, vault, IP approvals and explicit read authorization.",
    }
