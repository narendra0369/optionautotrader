"""Mocked offline tests for one-run AWS safety checks. NO broker connection."""
from __future__ import annotations

from contextlib import redirect_stderr, redirect_stdout
import io
from pathlib import Path
from unittest import TestCase
from unittest.mock import Mock, patch

from ops import optionx_batch_gatecheck as batch


class BatchGateTests(TestCase):
    def test_kill_switch_paper_tiers_and_real_order_gate(self):
        with redirect_stdout(io.StringIO()):
            batch.safety_gates()

    @patch.object(batch, "paper_state")
    @patch.object(batch, "safety_gates")
    @patch.object(batch, "offline_suite")
    @patch.object(batch, "verify_aws")
    def test_full_offline_checks_no_credential_prompt(self, verify, offline, safety, paper):
        out = io.StringIO()
        with redirect_stdout(out):
            code = batch.main(["--expected-ip", "43.204.246.235"])
        self.assertEqual(code, 0)
        verify.assert_called_once_with("43.204.246.235")
        offline.assert_called_once()
        safety.assert_called_once()
        paper.assert_called_once_with(batch.DEFAULT_DB)
        self.assertIn("OPTIONX_AWS_BATCH_CHECKS_COMPLETED", out.getvalue())
        self.assertIn("LIVE_TRADING_NOT_APPROVED", out.getvalue())

    @patch.object(batch, "broker_once")
    @patch.object(batch, "paper_state")
    @patch.object(batch, "safety_gates")
    @patch.object(batch, "offline_suite")
    @patch.object(batch, "verify_aws")
    def test_explicit_broker_runs_once_after_offline_gates(self, verify, offline, safety, paper, broker):
        events = []
        verify.side_effect = lambda *_: events.append("verify")
        offline.side_effect = lambda: events.append("offline")
        safety.side_effect = lambda: events.append("safety")
        paper.side_effect = lambda *_: events.append("paper")
        broker.side_effect = lambda *_: events.append("broker")
        with redirect_stdout(io.StringIO()):
            code = batch.main(["--expected-ip", "43.204.246.235", "--with-broker"])
        self.assertEqual(code, 0)
        self.assertEqual(events, ["verify", "offline", "safety", "paper", "broker"])

    @patch.object(batch, "broker_once")
    @patch.object(batch, "paper_state")
    @patch.object(batch, "safety_gates")
    @patch.object(batch, "offline_suite")
    @patch.object(batch, "verify_aws")
    def test_precheck_failure_never_calls_broker(self, verify, offline, safety, paper, broker):
        from ops.verify_angel_aws_readiness import ReadinessError
        verify.side_effect = ReadinessError("ip mismatch")
        with redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
            code = batch.main(["--expected-ip", "43.204.246.235", "--with-broker"])
        self.assertEqual(code, 1)
        broker.assert_not_called()
        offline.assert_not_called()

    @patch.object(batch, "verify_aws")
    def test_private_ip_fails_without_network(self, verify):
        with redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
            code = batch.main(["--expected-ip", "127.0.0.1", "--with-broker"])
        self.assertEqual(code, 1)
        verify.assert_not_called()

    @patch.object(batch.subprocess, "run")
    def test_offline_suite_without_network_or_secret_inputs(self, run):
        run.return_value = Mock(returncode=0, stderr="----------------------------------------------------------------------\nRan 201 tests in 0.13s\n\nOK\n")
        output = io.StringIO()
        with redirect_stdout(output):
            batch.offline_suite()
        self.assertIn("201 tests", output.getvalue())
        args, kwargs = run.call_args
        self.assertEqual(args[0][2:4], ["-m", "unittest"])
        self.assertEqual(kwargs["env"]["OPTIONX_REAL_ORDERS_ENABLED"], "0")
        self.assertNotIn("API_KEY", " ".join(args[0]))
        self.assertNotIn("PIN", " ".join(args[0]))

    @patch.object(batch.subprocess, "run")
    def test_failing_offline_tests_fail_closed(self, run):
        run.return_value = Mock(returncode=1, stdout="", stderr="FAILED")
        with self.assertRaisesRegex(RuntimeError, "OFFLINE_REGRESSION_FAILURE"):
            batch.offline_suite()

    @patch.object(batch, "broker_once")
    def test_uninitialized_paper_journal_is_not_created(self, broker):
        import tempfile
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "never-create.sqlite3"
            with redirect_stdout(io.StringIO()):
                batch.paper_state(path)
            self.assertFalse(path.exists())
            broker.assert_not_called()
