"""Angel One owner-bound Order/Trade/Position Book GET adapter, NO orders.

Uses already verified short-lived server-RAM owner session from angel_gateway.
No login, no browser credential inputs, no place/modify/cancel and no real
trading enable. Isolated from execution transport (which remains source-locked).
The trusted fetch must be an authenticated TLS response from fixed Angel URL.
"""
from __future__ import annotations

from datetime import datetime, timezone
import json
import ssl
import urllib.error
import urllib.request
from typing import Callable

import angel_gateway
from live_v7.broker_readonly import (
    BrokerSnapshotError, angel_orders, angel_positions, readonly_route,
    snapshot_metadata
)

ROOT = "https://apiconnect.angelone.in"
RESOURCES = ("orderbook", "tradebook", "positions")
MAX_BYTES = 524288


class AngelBookReadError(ValueError):
    """Public-safe reason without leaking credentials or broker payload."""


def _bounded_rows(response):
    if not isinstance(response, dict) or response.get("status") is not True:
        raise AngelBookReadError("BROKER_READ_REJECTED")
    rows = response.get("data")
    if rows is None:
        rows = []
    if not isinstance(rows, list) or len(rows) > 500 or any(not isinstance(r, dict) for r in rows):
        raise AngelBookReadError("BROKER_BOOK_SHAPE_INVALID")
    return rows


def _tradebook_summary(response):
    """Deliberately do not guess heterogeneous fill or average-price fields.

    Until normalized broker fields and trade IDs are independently validated,
    count raw rows only, never mark any entry as filled or reconciled.
    """
    return {"tradeRows": len(_bounded_rows(response)),
            "fillsBrokerVerified": False, "avgFillPriceBrokerVerified": False,
            "reconciliationPending": True}


def read_book(user_id: str, resource: str, *, fetch: Callable | None = None,
              now: datetime | None = None) -> dict:
    """Fixed-path GET; caller must be authenticated owner in SAME server process.

    No token read from client. The existing RAM session expires on logout,
    restart, or midnight IST; no reload from filesystem or environment.
    """
    if resource not in RESOURCES:
        raise AngelBookReadError("RESOURCE_NOT_ALLOWLISTED")
    if not isinstance(user_id, str) or not angel_gateway._owner_bound(user_id):
        raise AngelBookReadError("OWNER_NOT_AUTHENTICATED")
    moment = now if now is not None else datetime.now(timezone.utc)
    if not isinstance(moment, datetime) or moment.utcoffset() is None:
        raise AngelBookReadError("SERVER_CLOCK_INVALID")
    session = angel_gateway._clean_session(user_id, moment.timestamp())
    if not session or not isinstance(session.get("jwt"), str) or not isinstance(session.get("apiKey"), str):
        raise AngelBookReadError("ANGEL_SESSION_EXPIRED_OR_UNAVAILABLE")
    route = readonly_route("Angel", resource)
    assert route["method"] == "GET"
    headers = {
        "Accept": "application/json",
        "Authorization": "Bearer " + session["jwt"],
        "X-PrivateKey": session["apiKey"],
        "X-UserType": "USER", "X-SourceID": "WEB",
        "User-Agent": "OptionX-Angel-Books-ReadOnly/1.0",
        **angel_gateway.angel_client_identity_headers(allow_public_lookup=False)
    }
    req = urllib.request.Request(ROOT + route["path"], headers=headers, method="GET")
    try:
        if fetch is None:
            opener = urllib.request.build_opener(
                angel_gateway.NoRedirect(),
                urllib.request.HTTPSHandler(context=ssl.create_default_context()))
            reply = opener.open(req, timeout=10)
        else:
            reply = fetch(req, timeout=10)
        with reply as stream:
            if getattr(stream, "status", 200) != 200:
                raise AngelBookReadError("BROKER_BOOK_HTTP_ERROR")
            raw = stream.read(MAX_BYTES + 1)
        if len(raw) > MAX_BYTES:
            raise AngelBookReadError("BROKER_BOOK_RESPONSE_OVERSIZED")
        obj = json.loads(raw)
        _bounded_rows(obj)
        if resource == "orderbook":
            result = {"orders": angel_orders(obj)}
        elif resource == "positions":
            result = {"positions": angel_positions(obj)}
        else:
            result = _tradebook_summary(obj)
    except AngelBookReadError:
        raise
    except (urllib.error.HTTPError, urllib.error.URLError, OSError, TimeoutError,
            ValueError, TypeError, UnicodeDecodeError, BrokerSnapshotError):
        raise AngelBookReadError("BROKER_BOOK_UNAVAILABLE_OR_INVALID") from None
    metadata = snapshot_metadata(
        broker="Angel", resource=resource, received_at=moment,
        now=moment, account_owner_verified=True)
    # This is not independent broker owner certification / not a trade fill.
    return {"broker": "Angel", "resource": resource,
            "mode": "OWNER_BOUND_READ_ONLY", **result,
            "metadata": metadata, "canSubmitOrder": False,
            "liveExecutionEnabled": False, "brokerOrderAckVerified": False,
            "orderTransportLinked": False}


def read_three_books(user_id: str, *, fetch: Callable | None = None,
                     now: datetime | None = None) -> dict:
    """Fail entire snapshot if ANY book fails. Do not silently return partial."""
    out = {}
    for resource in RESOURCES:
        out[resource] = read_book(user_id, resource, fetch=fetch, now=now)
    return {"broker": "Angel", "books": out, "allReadsSucceeded": True,
            "orderAcknowledgementVerified": False,
            "tradeFillReconciled": False, "canSubmitOrder": False,
            "liveExecutionEnabled": False}
