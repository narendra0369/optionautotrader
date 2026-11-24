"""Offline testing of read-only egress observations, no broker network."""
import unittest
from unittest.mock import patch
from live_v7.egress_diagnostic import check_egress, _public_ipv4
from market_api import Handler, V7_STAGING_ORIGIN, _permitted_origin


class EgressDiagnosticTests(unittest.TestCase):
    def test_two_observed_ips_match_but_do_not_certify_static(self):
        result = check_egress(fetch=lambda url: "8.8.8.8",
                              registered_ipv4="8.8.8.8")
        self.assertTrue(result["sourcesAgreed"])
        self.assertTrue(result["observedMatchesConfiguredIpv4"])
        self.assertFalse(result["dedicatedStaticIpVerified"])
        self.assertFalse(result["angelBrokerRegistrationVerified"])
        self.assertFalse(result["angelAlgoExecutionApprovalVerified"])
        self.assertFalse(result["canSubmitOrder"])

    def test_observed_ip_mismatch_fails(self):
        answers = iter(["8.8.8.8", "1.1.1.1"])
        result = check_egress(fetch=lambda _: next(answers),
                              registered_ipv4="8.8.8.8")
        self.assertFalse(result["sourcesAgreed"])
        self.assertFalse(result["observedMatchesConfiguredIpv4"])

    def test_wrong_registered_ip_never_accepted(self):
        result = check_egress(fetch=lambda _: "8.8.8.8",
                              registered_ipv4="1.1.1.1")
        self.assertFalse(result["observedMatchesConfiguredIpv4"])

    def test_invalid_private_and_ipv6_rejected(self):
        for ip in ("127.0.0.1", "10.1.2.3", "192.168.1.1", "::1",
                   "2001:4860:4860::8888", "not-an-ip", ""):
            self.assertIsNone(_public_ipv4(ip))

    def test_network_failure_is_not_silently_verified(self):
        result = check_egress(fetch=lambda _: None,
                              registered_ipv4="8.8.8.8")
        self.assertFalse(result["sourcesAgreed"])
        self.assertFalse(result["observedMatchesConfiguredIpv4"])

    def test_staging_origin_allowed_cors_for_diagnostic(self):
        with patch.dict("os.environ", {"OPTIONX_V7_STAGING_CORS": "0"}):
            self.assertTrue(_permitted_origin(V7_STAGING_ORIGIN, "/api/v7/owner/egress"))
            self.assertFalse(_permitted_origin(V7_STAGING_ORIGIN, "/api/v7/angel/orderbook"))
        self.assertFalse(_permitted_origin("https://evil.example", "/api/v7/owner/egress"))

    def test_owner_token_and_origin_are_checked_in_http(self):
        import inspect
        source = inspect.getsource(Handler.do_GET)
        self.assertIn("user_from_token", source)
        self.assertIn("angel_status(user).get('ownerMatch')", source)
        self.assertIn("OPTIONX_V7_EGRESS_DIAGNOSTIC_ENABLED", source)

    def test_no_send_trade_capability_or_credentials(self):
        from pathlib import Path
        source = Path(__file__).with_name("egress_diagnostic.py").read_text("utf-8")
        for unsafe in ("placeOrder(", "cancelOrder(", "modifyOrder(",
                       "Authorization", "X-PrivateKey", "SmartConnect",
                       "broker_api_key", "token=", "requests.post("):
            self.assertNotIn(unsafe, source)


if __name__ == "__main__":
    unittest.main()
