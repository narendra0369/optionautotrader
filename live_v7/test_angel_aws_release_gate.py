"""Offline AWS release inspector tests: never authorize trading."""
import tempfile
from pathlib import Path
import unittest

from live_v7.angel_aws_release_gate import (
    REGISTERED_IP, REQUIRED_MODULES, inspect_source, observed_egress, evaluate
)

class AwsReleaseGateTests(unittest.TestCase):
    def test_matching_egress_does_not_approve_broker(self):
        result = observed_egress(fetch=lambda _: REGISTERED_IP)
        self.assertTrue(result["matchesRegisteredIp"])
        self.assertFalse(result["brokerRegistrationIndependentlyVerified"])
        self.assertFalse(result["dedicatedEgressProven"])

    def test_disagreeing_observations_reject(self):
        result = observed_egress(fetch=lambda u: REGISTERED_IP if "ipify" in u else "8.8.8.8")
        self.assertFalse(result["matchesRegisteredIp"])

    def test_unavailable_network_fail_closed(self):
        def fail(_):
            raise OSError("offline")
        result = observed_egress(fetch=fail)
        self.assertFalse(result["matchesRegisteredIp"])

    def test_source_inspection_and_lock(self):
        with tempfile.TemporaryDirectory() as folder:
            base = Path(folder) / "live_v7"
            base.mkdir()
            for name in REQUIRED_MODULES:
                (base / name).write_text("LIVE_ORDERS_SOURCE_LOCKED_PENDING_BROKER_CERTIFICATION")
            result = inspect_source(Path(folder))
            self.assertTrue(result["requiredModulesPresent"])
            self.assertTrue(result["sourceLockPresent"])
            (base / REQUIRED_MODULES[0]).unlink()
            self.assertFalse(inspect_source(Path(folder))["requiredModulesPresent"])

    def test_release_never_on_even_when_all_source_and_ip_match(self):
        with tempfile.TemporaryDirectory() as folder:
            base = Path(folder) / "live_v7"
            base.mkdir()
            for name in REQUIRED_MODULES:
                (base / name).write_text("LIVE_ORDERS_SOURCE_LOCKED_PENDING_BROKER_CERTIFICATION")
            outcome = evaluate(source=inspect_source(Path(folder)),
                               egress=observed_egress(fetch=lambda _: REGISTERED_IP))
            self.assertFalse(outcome["canSubmitOrder"])
            self.assertFalse(outcome["liveOrdersEnabled"])
            self.assertIn("REAL_ORDER_ACK_AND_NATIVE_STOP_NOT_VERIFIED",
                          outcome["blockedReasons"])

    def test_wrong_ip_cannot_enable(self):
        with tempfile.TemporaryDirectory() as folder:
            out = evaluate(source=inspect_source(Path(folder)),
                           egress=observed_egress(fetch=lambda _: "8.8.8.8"))
            self.assertIn("OUTBOUND_IPV4_MISMATCH_OR_UNKNOWN",out["blockedReasons"])
            self.assertFalse(out["canSubmitOrder"])


if __name__ == "__main__":
    unittest.main()
