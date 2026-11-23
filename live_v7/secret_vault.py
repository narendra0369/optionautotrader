"""OptionX V7 — external secret-vault contract, LOCKED in this stage.

NO credentials, broker passwords, TOTP secrets, API keys, access tokens,
refresh tokens or Delta HMAC secrets are stored in this repository or database
schema. A production vault/KMS integration is missing, so reads FAIL CLOSED.

The temporary Angel V6 session is server RAM only and lasts 15 minutes.
A persistent broker session may not be assumed from a profile verification.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


class VaultUnavailable(PermissionError):
    pass


@dataclass(frozen=True)
class VaultReference:
    """Opaque non-secret pointer only; never include raw credential values."""
    owner_uuid: str
    broker: str
    reference_id: str


class SecretVault(Protocol):
    def get_for_verified_server_owner(
        self, reference: VaultReference, *, server_owner_verified: bool
    ) -> "SecretEnvelope": ...


@dataclass(frozen=True, repr=False)
class SecretEnvelope:
    """Only ephemeral trusted backend memory may hold this object."""
    api_key: str
    api_secret: str | None
    access_token: str | None
    client_code: str | None

    def __repr__(self):
        return "<SecretEnvelope redacted>"


class LockedVault:
    """There is intentionally no working backend connector or secret store."""

    def get_for_verified_server_owner(
        self, reference: VaultReference, *, server_owner_verified: bool
    ) -> SecretEnvelope:
        raise VaultUnavailable(
            "External encrypted credential vault is not configured or reviewed"
        )

    def save(self, *args, **kwargs):
        raise VaultUnavailable("Do not write broker secrets to application storage")


def vault_readiness() -> dict[str, object]:
    return {
        "encryptedVaultConfigured": False,
        "brokerSecretsPersisted": False,
        "deltaPrivateSessionConnected": False,
        "canSubmitOrder": False,
        "liveExecutionEnabled": False,
        "missing": [
            "PROTECTED_KMS_AND_SECRETS_BACKEND",
            "ACCOUNT_BOUND_PERMISSION_CHECKS",
            "ROTATION_REVOKE_AND_EXPIRY_HANDLING",
            "BROKER_APPROVED_EGRESS_IP",
            "INDEPENDENT_SECURITY_TESTS",
        ],
    }
