"""Angel SmartAPI order HTTP transport: isolated fail-closed implementation.

NOT INSTALLED in any worker or public route. Never obtains broker tokens from
a browser or the read-only Angel session. Deployment needs a separately audited
vault, persisted stop switch, owner-bound lifecycle and broker algo approval.

Angel endpoints are fixed; the only accepted operations are BUY LIMIT,
SELL STOPLOSS_LIMIT, cancel and read-only order book. HTTP status 200 does
NOT mean the broker accepted or filled an order. Ambiguous response is UNKNOWN,
must stop new entries and reconcile with independent broker orderbook; never
blindly retry. NEVER call with live credentials during offline tests.
"""
from __future__ import annotations

from dataclasses import dataclass
import json
import ssl
import urllib.error
import urllib.request
from typing import Callable, Mapping, Any

API = "https://apiconnect.angelone.in"
PATHS = {
    "place": "/rest/secure/angelbroking/order/v1/placeOrder",
    "cancel": "/rest/secure/angelbroking/order/v1/cancelOrder",
    "orderbook": "/rest/secure/angelbroking/order/v1/getOrderBook",
}
MAX_RESPONSE = 65536


class AngelTransportBlocked(PermissionError):
    """Fixed code; never contain broker response or secrets."""


@dataclass(frozen=True, repr=False)
class TrustedServerSession:
    api_key: str
    jwt: str
    owner_id: str
    egress_ip: str
    broker_api_approved: bool = False

    def __repr__(self) -> str:
        return "<TrustedServerSession redacted>"


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise AngelTransportBlocked("BROKER_REDIRECT_BLOCKED")


def _guard(session: TrustedServerSession, *, expected_owner_id: str,
           operation: str, execution_gate: Mapping[str, Any]) -> None:
    if operation not in PATHS:
        raise AngelTransportBlocked("OPERATION_NOT_ALLOWLISTED")
    if not isinstance(session, TrustedServerSession):
        raise AngelTransportBlocked("TRUSTED_SESSION_MISSING")
    if (not expected_owner_id or session.owner_id != expected_owner_id
            or len(expected_owner_id) < 8):
        raise AngelTransportBlocked("OWNER_MISMATCH")
    if (not session.api_key or not session.jwt):
        raise AngelTransportBlocked("BROKER_CREDENTIALS_MISSING")
    if session.egress_ip != "43.204.246.235":
        raise AngelTransportBlocked("EGRESS_IP_NOT_MATCHED")
    if not isinstance(execution_gate, Mapping):
        raise AngelTransportBlocked("EXECUTION_GATE_MISSING")
    # This module has an irreversible source-level lock until a separate
    # security-reviewed release. Neither env nor browser can override it.
    if not session.broker_api_approved or execution_gate.get("broker_approval_proven") is not True:
        raise AngelTransportBlocked("BROKER_EXECUTION_APPROVAL_UNVERIFIED")
    if (execution_gate.get("durable_journal_healthy") is not True
            or execution_gate.get("worker_owner_bound") is not True
            or execution_gate.get("protective_stop_recovery_tested") is not True
            or execution_gate.get("kill_switch_persisted_and_clear") is not True
            or execution_gate.get("broker_snapshot_reconciled") is not True
            or execution_gate.get("risk_budget_approved") is not True):
        raise AngelTransportBlocked("PRODUCTION_SAFETY_GATES_MISSING")
    raise AngelTransportBlocked("LIVE_ORDERS_SOURCE_LOCKED_PENDING_BROKER_CERTIFICATION")


def _validate_payload(operation: str, payload: Mapping[str, Any] | None) -> None:
    if operation == "orderbook":
        if payload:
            raise AngelTransportBlocked("ORDERBOOK_BODY_NOT_ALLOWED")
        return
    if not isinstance(payload, Mapping):
        raise AngelTransportBlocked("BROKER_PAYLOAD_MISSING")
    if operation == "place":
        allowed = {"variety", "tradingsymbol", "symboltoken", "transactiontype",
                   "exchange", "ordertype", "producttype", "duration", "price",
                   "quantity", "triggerprice"}
        if set(payload) - allowed:
            raise AngelTransportBlocked("ORDER_FIELDS_NOT_ALLOWED")
        if payload.get("exchange") != "NFO" or payload.get("duration") != "DAY":
            raise AngelTransportBlocked("WRONG_EXCHANGE_OR_DURATION")
        entry = payload.get("transactiontype") == "BUY" and payload.get("ordertype") == "LIMIT" and payload.get("variety") == "NORMAL" and "triggerprice" not in payload
        stop = payload.get("transactiontype") == "SELL" and payload.get("ordertype") == "STOPLOSS_LIMIT" and payload.get("variety") == "STOPLOSS" and "triggerprice" in payload
        if not entry and not stop:
            raise AngelTransportBlocked("ORDER_TYPE_NOT_ALLOWED")
    elif operation == "cancel":
        if set(payload) != {"variety", "orderid"} or not isinstance(payload.get("orderid"), str) or len(payload["orderid"]) < 4:
            raise AngelTransportBlocked("CANCEL_REQUIRES_BROKER_ORDER_ID")


def request(*, operation: str, session: TrustedServerSession,
            expected_owner_id: str, execution_gate: Mapping[str, Any],
            payload: Mapping[str, Any] | None = None,
            fetch: Callable | None = None) -> dict:
    """Fixed-path HTTP client; SOURCE LOCK prevents every actual network call.

    fetch is injectable ONLY for future integration simulation; the current
    source lock still prevents it. Do not replace guard using an env flag.
    """
    _validate_payload(operation, payload)
    _guard(session, expected_owner_id=expected_owner_id,
           operation=operation, execution_gate=execution_gate)
    # Unreachable by design pending independently reviewed broker certification.
    # The protocol logic below is prepared for that future audited release.
    headers = {
        "Accept": "application/json", "Content-Type": "application/json",
        "X-PrivateKey": session.api_key, "Authorization": "Bearer " + session.jwt,
        "X-UserType": "USER", "X-SourceID": "WEB",
        "X-ClientPublicIP": session.egress_ip,
        "User-Agent": "OptionX-Angel-Execution/1.0",
    }
    method = "GET" if operation == "orderbook" else "POST"
    body = None if method == "GET" else json.dumps(
        dict(payload), separators=(",", ":")).encode("utf-8")
    req = urllib.request.Request(API + PATHS[operation], headers=headers,
                                 data=body, method=method)
    try:
        if fetch is None:
            opener = urllib.request.build_opener(
                urllib.request.HTTPSHandler(context=ssl.create_default_context()),
                _NoRedirect())
            response = opener.open(req, timeout=8)
        else:
            response = fetch(req, timeout=8)
        with response as out:
            if out.status != 200:
                return {"state": "UNKNOWN_BROKER_OUTCOME", "newEntriesBlocked": True}
            data = out.read(MAX_RESPONSE + 1)
        if len(data) > MAX_RESPONSE:
            return {"state": "UNKNOWN_BROKER_OUTCOME", "newEntriesBlocked": True}
        result = json.loads(data)
        if not isinstance(result, dict) or result.get("status") is not True:
            return {"state": "UNKNOWN_BROKER_OUTCOME", "newEntriesBlocked": True}
        if operation == "place":
            order_id = result.get("data", {}).get("orderid") if isinstance(result.get("data"), dict) else None
            if not isinstance(order_id, str) or len(order_id) < 4:
                return {"state": "UNKNOWN_BROKER_OUTCOME", "newEntriesBlocked": True}
            return {"state": "ACK_RECEIVED_REQUIRES_ORDERBOOK_RECONCILIATION",
                    "orderId": order_id, "newEntriesBlocked": True}
        return {"state": "RESPONSE_REQUIRES_BROKER_RECONCILIATION", "newEntriesBlocked": True}
    except (OSError, TimeoutError, ValueError, UnicodeDecodeError, urllib.error.URLError):
        return {"state": "UNKNOWN_BROKER_OUTCOME", "newEntriesBlocked": True}


def capabilities() -> dict:
    return {"broker": "Angel", "transportContractPresent": True,
            "endpointOperations": sorted(PATHS),
            "realOrdersEnabled": False, "sourceLockEnabled": True,
            "canSubmitOrder": False, "canCancelOrder": False,
            "liveBrokerCertification": "PENDING"}
