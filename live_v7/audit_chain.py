"""OptionX V7: pure append-only audit-chain formatter, no storage/network.

DEV ONLY and NOT validated. Do not include raw broker messages, credentials,
PIN/TOTP, access tokens, emails, personal IDs or order payloads in audit records.

Audit chains are tamper-evident only when the HMAC key is protected and the
records plus head digest are persisted in an independently durable store.
A local ephemeral Render filesystem is insufficient for live execution.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import re
from datetime import datetime, timezone
from typing import Any, Mapping, Sequence

EVENT_TYPES = frozenset({
    "STRATEGY_SELECTED",
    "PREFLIGHT_BLOCKED",
    "BROKER_SNAPSHOT_REQUESTED",
    "BROKER_SNAPSHOT_REJECTED",
    "BROKER_SNAPSHOT_ACCEPTED",
    "RISK_BREACH_DETECTED",
    "DUPLICATE_INTENT_BLOCKED",
    "KILL_SWITCH_STOPPED",
    "KILL_SWITCH_RESET_REQUESTED",
    "RECONCILIATION_DISCREPANCY",
    "MANUAL_REVIEW_REQUIRED",
})
BROKERS = {"Angel", "Delta", "NONE"}
MARKETS = {"NIFTY", "BANKNIFTY", "BTC", "NONE"}
CODE = re.compile(r"^[A-Z][A-Z0-9_]{1,63}$")
IDENTIFIER = re.compile(r"^[A-Za-z0-9_-]{8,96}$")
DIGEST = re.compile(r"^[a-f0-9]{64}$")
GENESIS = "0" * 64


class AuditError(ValueError):
    pass


def _canonical(event: Mapping[str, Any]) -> bytes:
    return json.dumps(
        event, sort_keys=True, separators=(",", ":"), ensure_ascii=True
    ).encode("ascii")


def _key(secret: bytes) -> bytes:
    if not isinstance(secret, bytes) or len(secret) < 32:
        raise AuditError("Trusted server-side audit MAC key required")
    return secret


def record(
    *,
    previous_digest: str,
    secret: bytes,
    event_id: str,
    event_type: str,
    broker: str,
    market: str,
    reason_code: str,
    now: datetime,
) -> dict[str, str]:
    """Return a minimal, HMAC-chained event. Does not write or publish it."""
    _key(secret)
    if not isinstance(previous_digest, str) or not DIGEST.fullmatch(previous_digest):
        raise AuditError("Invalid previous audit digest")
    if not isinstance(event_id, str) or not IDENTIFIER.fullmatch(event_id):
        raise AuditError("Invalid opaque event id")
    if event_type not in EVENT_TYPES:
        raise AuditError("Unknown event type")
    if broker not in BROKERS or market not in MARKETS:
        raise AuditError("Unknown broker/market")
    if not isinstance(reason_code, str) or not CODE.fullmatch(reason_code):
        raise AuditError("Only fixed status codes may be logged")
    if not isinstance(now, datetime) or now.utcoffset() is None:
        raise AuditError("Aware server time required")
    fields = {
        "event_id": event_id,
        "event_type": event_type,
        "broker": broker,
        "market": market,
        "reason_code": reason_code,
        "created_at": now.astimezone(timezone.utc).isoformat(),
        "previous_digest": previous_digest,
    }
    fields["digest"] = hmac.new(secret, _canonical(fields), hashlib.sha256).hexdigest()
    return fields


def verify(
    entries: Sequence[Mapping[str, Any]],
    *,
    secret: bytes,
    expected_head_digest: str | None = None,
) -> dict[str, object]:
    """Verify ordering, uniqueness and HMAC. Treat absence as unverified.

    If a trusted external head digest is provided, truncation/rewrite is
    detectable. Without independent anchoring, this is not full audit security.
    """
    _key(secret)
    if not isinstance(entries, (tuple, list)) or not entries:
        return {"verified": False, "error": "AUDIT_CHAIN_EMPTY"}
    if expected_head_digest is not None and (
        not isinstance(expected_head_digest, str)
        or not DIGEST.fullmatch(expected_head_digest)
    ):
        raise AuditError("Invalid anchored head digest")
    previous = GENESIS
    seen: set[str] = set()
    for position, raw in enumerate(entries):
        if not isinstance(raw, Mapping):
            return {"verified": False, "error": "MALFORMED_RECORD", "position": position}
        if set(raw) != {
            "event_id", "event_type", "broker", "market",
            "reason_code", "created_at", "previous_digest", "digest"
        }:
            return {"verified": False, "error": "UNEXPECTED_RECORD_FIELDS", "position": position}
        if (
            raw["previous_digest"] != previous
            or not isinstance(raw["digest"], str)
            or not DIGEST.fullmatch(raw["digest"])
        ):
            return {"verified": False, "error": "CHAIN_LINK_BROKEN", "position": position}
        event_id = raw["event_id"]
        if not isinstance(event_id, str) or not IDENTIFIER.fullmatch(event_id):
            return {"verified": False, "error": "INVALID_EVENT_ID", "position": position}
        if event_id in seen:
            return {"verified": False, "error": "DUPLICATE_EVENT_ID", "position": position}
        if (
            raw["event_type"] not in EVENT_TYPES
            or raw["broker"] not in BROKERS
            or raw["market"] not in MARKETS
            or not isinstance(raw["reason_code"], str)
            or not CODE.fullmatch(raw["reason_code"])
            or not isinstance(raw["created_at"], str)
        ):
            return {"verified": False, "error": "INVALID_EVENT_DATA", "position": position}
        seen.add(event_id)
        fields = {k: v for k, v in raw.items() if k != "digest"}
        try:
            candidate = hmac.new(secret, _canonical(fields), hashlib.sha256).hexdigest()
        except (TypeError, ValueError):
            return {"verified": False, "error": "UNENCODABLE_RECORD", "position": position}
        if not hmac.compare_digest(candidate, raw["digest"]):
            return {"verified": False, "error": "HMAC_MISMATCH", "position": position}
        previous = raw["digest"]
    if expected_head_digest is not None and not hmac.compare_digest(previous, expected_head_digest):
        return {"verified": False, "error": "ANCHOR_MISMATCH"}
    return {
        "verified": True,
        "records": len(entries),
        "head_digest": previous,
        "independentlyAnchored": expected_head_digest is not None,
    }
