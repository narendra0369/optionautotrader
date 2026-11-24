"""OptionX secure HTTPS/Android access design gate; NO web server or broker access.

Pure prospective policy checks only. Browser headers cannot be used as trusted
proof of TLS, owner identity, broker session or egress. Even when the
requirements are satisfied, this source alone NEVER enables a route:
a separately deployed authenticated reverse proxy and verified token backend
are necessary. No order route exists in the allowlist.
"""
from __future__ import annotations

from dataclasses import dataclass

# At present only the existing V7 staging UI should be considered for
# a future read-only authenticated bridge, and it is NOT enabled here.
STAGING_ORIGIN = "https://optionx-v7-frontend-test-staging.onrender.com"
PAPER_READ_ONLY_PATHS = frozenset({
    "/api/v8/paper/status",
    "/api/v8/paper/trades",
    "/api/v8/paper/health",
})


@dataclass(frozen=True)
class TrustedAccessContext:
    # These flags MUST originate from independent server/mTLS/auth checks.
    # A future implementation may not read them from request JSON or headers.
    tls_reverse_proxy_verified: bool = False
    mutual_trust_between_proxy_and_backend: bool = False
    signed_optionx_auth_verified_server_side: bool = False
    owner_id: str = ""
    configured_owner_id: str = ""
    request_origin: str = ""
    csrf_or_same_origin_protection_verified: bool = False
    request_method: str = "GET"
    request_path: str = ""
    rate_limit_enforced: bool = False
    broker_credentials_excluded_from_response: bool = False
    private_api_not_publicly_bound: bool = False


def assess_gateway(ctx: TrustedAccessContext | None) -> dict:
    """Inspect a *design*, never grant access or enable API endpoints."""
    reasons: list[str] = []
    if not isinstance(ctx, TrustedAccessContext):
        reasons.append("NO_SERVER_VERIFIED_REQUEST_CONTEXT")
        ctx = TrustedAccessContext()
    checks = (
        ("TLS_INGRESS_NOT_VERIFIED", ctx.tls_reverse_proxy_verified),
        ("PROXY_BACKEND_MUTUAL_TRUST_NOT_VERIFIED", ctx.mutual_trust_between_proxy_and_backend),
        ("SIGNED_OWNER_AUTH_NOT_VERIFIED", ctx.signed_optionx_auth_verified_server_side),
        ("CSRF_OR_ORIGIN_PROTECTION_NOT_VERIFIED", ctx.csrf_or_same_origin_protection_verified),
        ("RATE_LIMIT_NOT_VERIFIED", ctx.rate_limit_enforced),
        ("BROKER_SECRET_REDACTION_NOT_VERIFIED", ctx.broker_credentials_excluded_from_response),
        ("PRIVATE_BACKEND_BIND_NOT_VERIFIED", ctx.private_api_not_publicly_bound),
    )
    for name, condition in checks:
        if condition is not True:
            reasons.append(name)
    if not ctx.owner_id or not ctx.configured_owner_id or ctx.owner_id != ctx.configured_owner_id:
        reasons.append("OWNER_ID_MISMATCH_OR_UNKNOWN")
    if ctx.request_origin != STAGING_ORIGIN:
        reasons.append("STAGING_ORIGIN_NOT_ALLOWED")
    if ctx.request_method != "GET" or ctx.request_path not in PAPER_READ_ONLY_PATHS:
        reasons.append("ONLY_FIXED_GET_PAPER_ROUTES_ALLOWED")
    return {
        "mode": "UNDEPLOYED_HTTPS_ACCESS_DESIGN_GATE",
        "designChecksSatisfied": not reasons,
        "blockedReasons": sorted(set(reasons)),
        "publicHttpsGatewayDeployed": False,
        "authenticatedProductionAccessEnabled": False,
        "canReadBrokerData": False,
        "canReadPrivatePaperData": False,
        "canSubmitOrder": False,
        "realOrdersEnabled": False,
        "mobileAndroidAppConnected": False,
        "operatorAction": "Deploy separately audited TLS owner-authenticated read-only gateway only after documented review.",
    }
