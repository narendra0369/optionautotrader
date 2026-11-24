"""OptionX release-gate truthfulness tests; no network credentials or actual orders."""
from __future__ import annotations

import io
import json
from contextlib import redirect_stdout
from tempfile import TemporaryDirectory
from pathlib import Path
from unittest import TestCase
from unittest.mock import patch

from ops import optionx_release_gate_matrix as gates
from ops.paper_ledger_v1 import _db, _init


class ReleaseGateOfflineTests(TestCase):
    def test_no_runtime_evidence_must_not_claim_live_ready(self):
        report = gates.assess()
        self.assertFalse(report["liveTradingAuthorized"])
        self.assertFalse(report["realMoneyOrdersEnabled"])
        self.assertGreaterEqual(report["blockedCount"], 10)
        self.assertGreaterEqual(report["syntheticLifecycleCasesPassed"], 20)
        actual = {g["gate"]: g["state"] for g in report["gates"]}
        self.assertEqual(actual["AWS_MUMBAI_LOOPBACK_HEALTH_AND_EGRESS_IP"], "UNVERIFIED_THIS_RUN")
        self.assertEqual(actual["PRIVATE_LIVE_LEDGER"], "BLOCKED")
        self.assertEqual(actual["ANDROID_APPLICATION_SIGNING_DISTRIBUTION"], "BLOCKED")
        self.assertEqual(actual["BROKER_NATIVE_STOP_TARGET_PROTECTION"], "BLOCKED")
        self.assertEqual(actual["REAL_ORDER_ENDPOINT_HARD_LOCK"], "PASS")

    def test_local_paper_sqlite_verified_but_live_still_blocked(self):
        with TemporaryDirectory() as d:
            db = Path(d) / "virtual-paper.sqlite3"
            with _db(db) as connection:
                _init(connection, "500000")
            db.chmod(0o600)
            report = gates.assess(paper_db=str(db))
        self.assertFalse(report["liveTradingAuthorized"])
        self.assertGreaterEqual(report["blockedCount"], 10)
        v = {g["gate"]: g["state"] for g in report["gates"]}
        self.assertEqual(v["VIRTUAL_PAPER_JOURNAL_INTEGRITY"], "PASS")
        self.assertEqual(v["PAPER_POSITION_CONTINUOUS_PROTECTION"], "NOT_APPLICABLE")
        self.assertEqual(v["REAL_ORDER_LIFECYCLE_AND_RESTART_RECOVERY"], "BLOCKED")

    @patch("ops.verify_angel_aws_readiness.verify")
    def test_static_ip_check_requires_actual_verification_call(self, verify):
        report = gates.assess(verify_aws_ip="43.204.246.235")
        verify.assert_called_once_with("43.204.246.235")
        g = {row["gate"]: row["state"] for row in report["gates"]}
        self.assertEqual(g["AWS_MUMBAI_LOOPBACK_HEALTH_AND_EGRESS_IP"], "PASS")
        self.assertEqual(g["PRODUCTION_OWNER_AUTH_TLS_ACCESS_CONTROL"], "BLOCKED")

    @patch("ops.verify_angel_aws_readiness.verify")
    def test_failed_static_ip_check_cannot_claim_success(self, verify):
        verify.side_effect = RuntimeError("fake mismatch")
        with self.assertRaises(RuntimeError):
            gates.assess(verify_aws_ip="43.204.246.235")

    @patch("ops.optionx_release_gate_matrix.hard_block_order")
    def test_if_order_endpoint_unlocked_report_fails_closed(self, hard_block):
        hard_block.return_value = {"error": "NONE", "orderSent": True}
        with self.assertRaisesRegex(gates.GateError, "REAL_ORDER_HARD_LOCK_REGRESSED"):
            gates.assess()

    def test_cli_json_never_claims_live_approval(self):
        out = io.StringIO()
        with redirect_stdout(out):
            code = gates.main(["--json"])
        self.assertEqual(code, 0)
        result = json.loads(out.getvalue())
        self.assertFalse(result["liveTradingAuthorized"])
        self.assertFalse(result["realMoneyOrdersEnabled"])
        self.assertGreaterEqual(result["blockedCount"], 10)
