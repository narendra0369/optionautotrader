"""OptionX V7 — verified-owner Angel read-only bridge (DISABLED BY DEFAULT).

Only an internally authenticated OPTIONX owner may use the temporary,
profile-matched RAM session from angel_gateway. No order endpoint or retry.
Do not enable this bridge before independent review and testing.

Delta private access is intentionally not included: there is no verified
Delta identity/session or secret vault in the current service.
"""
from __future__ import annotations

import time
from typing import Any

import angel_gateway
from live_v7.broker_readonly import angel_orders, angel_positions, BrokerSnapshotError
from live_v7.angel_books_readonly import _tradebook_summary
from live_v7.read_only_transport import (
    ServerOnlySession, fetch_readonly, ReadOnlyTransportError,
)


class ReadOnlyBridgeError(ValueError):
    def __init__(self, message: str, diagnostic_code: str = "BROKER_SNAPSHOT_UNAVAILABLE"):
        super().__init__(message)
        # Never expose API keys, session tokens, broker account rows or raw errors.
        self.diagnostic_code = diagnostic_code


def angel_owner_snapshot(
    *,
    verified_optionx_user_id: str,
    resource: str,
    server_feature_flag_enabled: bool = False,
) -> dict[str, Any]:
    """Never call from unverified/browser-owned parameters.

    Caller must first verify the bearer token via Supabase /auth/v1/user,
    verify personal owner binding, and restrict the request origin. Feature
    flag defaults to OFF. No local secrets or full broker payloads returned.
    """
    if server_feature_flag_enabled is not True:
        raise ReadOnlyBridgeError("V7 read-only broker inspection is not enabled", "FEATURE_DISABLED")
    if resource not in ("orderbook", "tradebook", "positions"):
        raise ReadOnlyBridgeError("Only fixed read-only broker books supported")
    if not angel_gateway._owner_bound(verified_optionx_user_id):
        raise ReadOnlyBridgeError("OptionX owner binding failed")

    # Reuse the V6 RAM-only, broker-profile-verified session. Never persist
    # its API key or JWT to DB, environment dumps or logs.
    data = angel_gateway._clean_session(verified_optionx_user_id, time.time())
    if not data:
        raise ReadOnlyBridgeError("No current verified Angel One session", "SESSION_EXPIRED")

    try:
        broker_session = ServerOnlySession(
            broker="Angel",
            owner_id=verified_optionx_user_id,
            api_key=data["apiKey"],
            bearer_token=data["jwt"],
            broker_account_verified=True,  # established by V6 getProfile
            session_current=True,          # established by V6 expiry check
        )
        response = fetch_readonly(
            session=broker_session,
            resource=resource,
            verified_owner_id=verified_optionx_user_id,
            external_read_authorized_by_server=True,
        )
        if not isinstance(response, dict) or response.get("status") is not True:
            # No raw broker message is logged or sent to the client.
            raise ReadOnlyBridgeError("Angel API rejected the account read",
                                      "ANGEL_API_REJECTED")
        normalized = (angel_orders(response) if resource == "orderbook" else
                      angel_positions(response) if resource == "positions" else None)
        trade_summary = _tradebook_summary(response) if resource == "tradebook" else None
    except ReadOnlyBridgeError:
        raise
    except ReadOnlyTransportError as exc:
        raise ReadOnlyBridgeError("Broker read transport is unavailable",
                                  exc.diagnostic_code) from None
    except (KeyError, BrokerSnapshotError, ValueError):
        raise ReadOnlyBridgeError("Broker returned unexpected NFO snapshot shape",
                                  "BROKER_DATA_FORMAT") from None

    return {
        "broker": "Angel",
        "resource": resource,
        "records": normalized if normalized is not None else [],
        "recordCount": len(normalized) if normalized is not None else trade_summary["tradeRows"],
        "tradeSummary": trade_summary,
        "fillsBrokerVerified": False,
        "acknowledgementVerified": False,
        "trustedAccount": "OWNER_PROFILE_MATCHED",
        "snapshotContract": "OPTIONX_V7_ANGEL_READONLY_V2",
        "quoteAndContractMasterVerified": False,
        "orderExecutionEnabled": False,
        "liveExecutionEnabled": False,  # Explicit legacy/frontend safety contract
        "canSubmitOrder": False,
        "notice": "Read-only account snapshot. Does not authorize execution.",
    }


def delta_private_access_status() -> dict[str, object]:
    return {
        "broker": "Delta",
        "accountVerified": False,
        "privateReadEnabled": False,
        "canSubmitOrder": False,
        "orderExecutionEnabled": False,
        "missing": [
            "OWNER_BOUND_DELTA_CONNECTION",
            "SECURE_API_SECRET_VAULT",
            "IP_WHITELIST",
            "BROKER_PERMISSION_REVIEW",
            "INTEGRATION_TESTS",
        ],
    }
