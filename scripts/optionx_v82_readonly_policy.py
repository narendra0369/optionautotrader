"""OPTIONX V82: side-effect-free, deny-by-default scope policy prototype.

No broker clients, network calls, database writes or secret access. This is not
authorization for trading, and must not be wired to a production execution path.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional

READ_SCOPES = frozenset({"status.read", "diagnostics.read"})
MAX_TOKEN_AGE_SECONDS = 60
MAX_ATTESTATION_AGE_SECONDS = 15 * 60


@dataclass(frozen=True)
class ReadOnlyRequest:
    scope: str
    owner_authenticated: bool
    worker_status: str
    worker_id_matches: bool
    public_key_fingerprint_matches: bool
    independent_reviewer: bool
    process_identity_verified: bool
    reviewer_revoked: bool
    attestation_expires_at: Optional[datetime]
    issued_at: Optional[datetime]
    nonce_is_fresh: bool
    stop_engaged: bool = True


@dataclass(frozen=True)
class Decision:
    allowed: bool
    reason: str


def evaluate_read_only(req: ReadOnlyRequest, now: datetime) -> Decision:
    """Evaluate a request with NO side effects. STOP does not permit trading.

    An external server must authenticate the caller, verify signatures and
    consume nonces atomically. Booleans passed here are NOT evidence by themselves.
    """
    if now.tzinfo is None:
        return Decision(False, "CLOCK_UNTRUSTED")
    now = now.astimezone(timezone.utc)
    if req.scope not in READ_SCOPES:
        return Decision(False, "SCOPE_FORBIDDEN")
    if not req.owner_authenticated:
        return Decision(False, "OWNER_AUTH_REQUIRED")
    if req.worker_status != "VERIFIED":
        return Decision(False, "WORKER_NOT_VERIFIED")
    if not (req.worker_id_matches and req.public_key_fingerprint_matches):
        return Decision(False, "WORKER_BINDING_INVALID")
    if not (req.independent_reviewer and req.process_identity_verified):
        return Decision(False, "INDEPENDENT_ATTESTATION_REQUIRED")
    if req.reviewer_revoked:
        return Decision(False, "REVIEWER_REVOKED")
    if not req.nonce_is_fresh:
        return Decision(False, "NONCE_INVALID")
    if req.issued_at is None or req.issued_at.tzinfo is None:
        return Decision(False, "TOKEN_TIME_INVALID")
    token_age = (now - req.issued_at.astimezone(timezone.utc)).total_seconds()
    if token_age < 0 or token_age >= MAX_TOKEN_AGE_SECONDS:
        return Decision(False, "TOKEN_EXPIRED")
    if req.attestation_expires_at is None or req.attestation_expires_at.tzinfo is None:
        return Decision(False, "ATTESTATION_TIME_INVALID")
    expiry = req.attestation_expires_at.astimezone(timezone.utc)
    # The evaluator cannot verify issuance age; upper-bound horizon to avoid
    # accepting a user-supplied far-future attestation expiry.
    seconds_remaining = (expiry - now).total_seconds()
    if not 0 < seconds_remaining <= MAX_ATTESTATION_AGE_SECONDS:
        return Decision(False, "ATTESTATION_EXPIRED_OR_UNBOUNDED")
    return Decision(True, "READ_ONLY_SCOPE_ALLOWED")
