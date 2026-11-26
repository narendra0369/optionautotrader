"""Offline regression tests for the V82 pure policy. Never contacts a broker."""
import unittest
from dataclasses import replace
from datetime import datetime, timedelta, timezone

from scripts.optionx_v82_readonly_policy import ReadOnlyRequest, evaluate_read_only


class ReadOnlyPolicyTests(unittest.TestCase):
    def setUp(self):
        self.now = datetime(2026, 11, 26, 18, 0, tzinfo=timezone.utc)
        self.base = ReadOnlyRequest(
            scope="status.read", owner_authenticated=True,
            worker_status="VERIFIED", worker_id_matches=True,
            public_key_fingerprint_matches=True, independent_reviewer=True,
            process_identity_verified=True, reviewer_revoked=False,
            attestation_expires_at=self.now + timedelta(minutes=5),
            issued_at=self.now - timedelta(seconds=10), nonce_is_fresh=True,
            stop_engaged=True,
        )

    def check_denied(self, **changes):
        d = evaluate_read_only(replace(self.base, **changes), self.now)
        self.assertFalse(d.allowed, d.reason)

    def test_safe_status_read_if_externally_verified(self):
        self.assertTrue(evaluate_read_only(self.base, self.now).allowed)
        self.assertTrue(evaluate_read_only(replace(self.base, scope="diagnostics.read"), self.now).allowed)

    def test_trade_and_control_scopes_always_denied(self):
        for scope in ("order.place", "order.cancel", "broker.call",
                      "risk.write", "stop.clear", "key.promote", "unknown", ""):
            with self.subTest(scope=scope):
                self.check_denied(scope=scope)

    def test_missing_owner_or_unverified_worker(self):
        self.check_denied(owner_authenticated=False)
        self.check_denied(worker_status="PENDING")
        self.check_denied(worker_status="REVOKED")

    def test_attestation_and_binding_gaps(self):
        for changes in (
            dict(worker_id_matches=False), dict(public_key_fingerprint_matches=False),
            dict(independent_reviewer=False), dict(process_identity_verified=False),
            dict(reviewer_revoked=True), dict(nonce_is_fresh=False),
            dict(attestation_expires_at=None),
            dict(attestation_expires_at=self.now),
            dict(attestation_expires_at=self.now + timedelta(minutes=16)),
        ):
            with self.subTest(changes=changes):
                self.check_denied(**changes)

    def test_token_time_boundaries(self):
        self.check_denied(issued_at=None)
        self.check_denied(issued_at=self.now - timedelta(seconds=60))
        self.check_denied(issued_at=self.now + timedelta(seconds=1))


if __name__ == "__main__":
    unittest.main()
