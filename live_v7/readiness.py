"""OptionX V7 server-only readiness summary — all real orders remain blocked.

Does NOT infer static IP registration, approvals or execution safety from a
broker profile login. No credential access or broker network requests.
This module is safe to show only to a verified signed-in owner; never send
tokens or personal broker account details back in status payloads.
"""
from __future__ import annotations

from typing import Mapping, Any


def status(angel_session: Mapping[str, Any] | None) -> dict[str, Any]:
    s = angel_session if isinstance(angel_session, Mapping) else {}
    confirmed = {
        "optionxUserSignedIn": True,  # caller MUST verify Supabase access token
        "ownerBindingConfigured": s.get("ownerConfigured") is True,
        "ownerBindingMatched": s.get("ownerMatch") is True,
        "angelProfileSessionActive": s.get("connected") is True,
    }
    not_verified = [
        "ANGEL_REGISTERED_STATIC_EGRESS_IPV4",
        "BROKER_ALGO_PERMISSIONS_AND_COMPLIANCE",
        "DERIVATIVE_INSTRUMENT_MASTER_FRESH",
        "BROKER_AUTHENTICATED_EXECUTION_QUOTES",
        "CONTRACT_AND_MARGIN_VERIFIED",
        "DURABLE_LEDGER_DEPLOYED",
        "EXCHANGE_HOURS_AND_HOLIDAYS",
        "ORDER_RECONCILIATION_TESTED",
        "STOP_TARGET_AND_PARTIAL_FILL_TESTED",
        "RISK_LIMITS_AND_KILL_SWITCH_TESTED",
        "OWNER_FINAL_LIVE_APPROVAL",
    ]
    return {
        "version": "V7_DEV_SOURCE",
        "mode": "READINESS_ONLY",
        "realOrders": "HARD_LOCKED",
        "liveExecutionEnabled": False,
        "canSubmitOrder": False,
        "checksConfirmedFromExistingAuth": confirmed,
        "notIndependentlyVerified": not_verified,
        "developmentModulesCommitted": [
            "contract_quote_validation", "read_only_transport", "journal",
            "reconciliation", "risk_intent_gate", "protective_exit",
            "kill_switch", "audit_chain", "sql_schema_draft"
        ],
        "unverifiedCode": True,
        "testsDeferred": True,
        "productionDeploymentOfV7": False,
        "notice": "Angel profile verification is not authority to execute real trades.",
    }
