"""Untrusted browser or Android calls can never activate the undeployed HTTPS gate."""
from __future__ import annotations

from dataclasses import replace
from unittest import TestCase

from ops.https_mobile_access_gate import (
    STAGING_ORIGIN, TrustedAccessContext, assess_gateway,
    PAPER_READ_ONLY_PATHS,
)


class MobileHttpsGateTests(TestCase):
    def trusted_context(self):
        return TrustedAccessContext(
            tls_reverse_proxy_verified=True,
            mutual_trust_between_proxy_and_backend=True,
            signed_optionx_auth_verified_server_side=True,
            owner_id="u-demo-owner",
            configured_owner_id="u-demo-owner",
            request_origin=STAGING_ORIGIN,
            csrf_or_same_origin_protection_verified=True,
            request_method="GET",
            request_path="/api/v8/paper/status",
            rate_limit_enforced=True,
            broker_credentials_excluded_from_response=True,
            private_api_not_publicly_bound=True,
        )

    def test_all_static_design_factors_still_do_not_authorize_unbuilt_gateway(self):
        result = assess_gateway(self.trusted_context())
        self.assertTrue(result["designChecksSatisfied"])
        self.assertFalse(result["publicHttpsGatewayDeployed"])
        self.assertFalse(result["canReadPrivatePaperData"])
        self.assertFalse(result["canSubmitOrder"])
        self.assertFalse(result["mobileAndroidAppConnected"])

    def test_unverified_or_browser_claimed_context_fails_closed(self):
        result = assess_gateway(None)
        self.assertFalse(result["designChecksSatisfied"])
        self.assertFalse(result["canReadBrokerData"])
        self.assertFalse(result["realOrdersEnabled"])

    def test_wrong_owner_and_untrusted_origin_are_blocked(self):
        bad = replace(self.trusted_context(), owner_id="u-stranger", request_origin="https://evil.example")
        result = assess_gateway(bad)
        self.assertFalse(result["designChecksSatisfied"])
        self.assertIn("OWNER_ID_MISMATCH_OR_UNKNOWN", result["blockedReasons"])
        self.assertIn("STAGING_ORIGIN_NOT_ALLOWED", result["blockedReasons"])

    def test_post_and_order_routes_never_on_allowlist(self):
        self.assertFalse(any("order" in p for p in PAPER_READ_ONLY_PATHS))
        for path, method in [
            ("/api/live/orders", "GET"),
            ("/api/v8/paper/status", "POST"),
            ("/api/v8/paper/health", "DELETE"),
        ]:
            result = assess_gateway(replace(self.trusted_context(),
                                            request_path=path, request_method=method))
            self.assertIn("ONLY_FIXED_GET_PAPER_ROUTES_ALLOWED", result["blockedReasons"])
            self.assertFalse(result["canSubmitOrder"])

    def test_missing_mutual_tls_backend_trust_is_blocked(self):
        result = assess_gateway(replace(self.trusted_context(),mutual_trust_between_proxy_and_backend=False))
        self.assertIn("PROXY_BACKEND_MUTUAL_TRUST_NOT_VERIFIED", result["blockedReasons"])
