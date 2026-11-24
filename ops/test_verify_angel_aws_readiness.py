"""Offline regression tests for AWS readiness script. No outbound requests."""
import io
import unittest
from contextlib import redirect_stdout
from ops.verify_angel_aws_readiness import verify, ReadinessError

class FakeResponse:
    def __init__(self, status, body):
        self.status, self.body = status, body
    def __enter__(self): return self
    def __exit__(self, *args): return None
    def getcode(self): return self.status
    def read(self, limit=None): return self.body[:limit] if limit else self.body

class OfflineReadinessTests(unittest.TestCase):
    def opener(self, *, ip=b"43.204.246.235", health=b'{"status":"ok","paperOnly":true,"liveOrdersEnabled":false}', orders=b'{"error":"REAL_ORDERS_HARD_LOCKED","orderSent":false}', order_status=423, angel_status=401):
        def perform(req, timeout):
            u = req.full_url
            if u.endswith("api.ipify.org"): return FakeResponse(200, ip)
            if u.endswith("/health"): return FakeResponse(200, health)
            if u.endswith("/api/live/orders"): return FakeResponse(order_status, orders)
            if u.endswith("/api/brokers/angel/status"): return FakeResponse(angel_status, b'{"error":"Sign in required"}')
            raise AssertionError("Unexpected destination " + u)
        return perform

    def test_valid_read_only_gate(self):
        out = io.StringIO()
        with redirect_stdout(out):
            verify("43.204.246.235", opener=self.opener())
        self.assertIn("AWS_PRECHECK_PASSED", out.getvalue())
        self.assertIn("NOT trading approval", out.getvalue())

    def test_mismatched_outbound_ip(self):
        with self.assertRaisesRegex(ReadinessError, "EGRESS_IPV4_MISMATCH"):
            verify("43.204.246.235", opener=self.opener(ip=b"13.235.33.252"))

    def test_fake_health_flag_blocks(self):
        with self.assertRaisesRegex(ReadinessError, "LOCAL_RESEARCH_BACKEND_NOT_SAFE"):
            verify("43.204.246.235", opener=self.opener(health=b'{"status":"ok","paperOnly":true,"liveOrdersEnabled":true}'))

    def test_real_order_gate_must_be_locked(self):
        with self.assertRaisesRegex(ReadinessError, "REAL_ORDER_GATE_NOT_LOCKED"):
            verify("43.204.246.235", opener=self.opener(order_status=200, orders=b'{"orderSent":true}'))

    def test_angel_status_must_be_authenticated(self):
        with self.assertRaisesRegex(ReadinessError, "ANGEL_ACCOUNT_STATUS_PUBLICLY_EXPOSED"):
            verify("43.204.246.235", opener=self.opener(angel_status=200))

    def test_expected_ip_must_be_global_ipv4(self):
        for ip in ("not-an-ip", "127.0.0.1", "::1", "192.168.1.5"):
            with self.subTest(ip=ip), self.assertRaises(ReadinessError):
                verify(ip, opener=self.opener())

if __name__ == "__main__":
    unittest.main()
