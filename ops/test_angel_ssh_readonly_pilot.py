"""Offline tests for the isolated SSH-only Angel One pilot.

Never contacts a broker, requests real credentials, or places orders.
"""
from __future__ import annotations

import io
from contextlib import redirect_stdout, redirect_stderr
from unittest import TestCase
from unittest.mock import patch

from ops.angel_ssh_readonly_pilot import PilotError, main, paper_preview
from live_gateway import hard_block_order


CONTRACT = {
    "symbol": "NIFTY01DEC2626000CE",
    "side": "CE",
    "lotSize": 50,
    "tickSize": 0.05,
}


class PaperPreviewTests(TestCase):
    def test_risk_reward_one_lot_ticks(self):
        preview = paper_preview(CONTRACT, 100, risk=300, reward=600)
        self.assertEqual(preview["mode"], "PAPER_PREVIEW_ONLY")
        self.assertEqual(preview["brokerOrdersSent"], 0)
        self.assertEqual(preview["oneLotQuantity"], 50)
        self.assertEqual(preview["illustrativeStopLevel"], 94)
        self.assertEqual(preview["illustrativeTargetLevel"], 112)
        self.assertEqual(preview["theoreticalLossAtStopBeforeCharges"], 300)
        self.assertEqual(preview["theoreticalGainAtTargetBeforeCharges"], 600)

    def test_one_lot_rounded_stop_never_exceeds_risk_theoretically(self):
        out = paper_preview(CONTRACT, 100.05, risk=301, reward=601)
        self.assertLessEqual(out["theoreticalLossAtStopBeforeCharges"], 301)
        self.assertGreaterEqual(out["theoreticalGainAtTargetBeforeCharges"], 601)

    def test_non_option_contract_is_blocked(self):
        with self.assertRaises(PilotError):
            paper_preview({**CONTRACT, "side": "FUT"}, 100)

    def test_bad_price_and_size_blocked(self):
        with self.assertRaises(PilotError):
            paper_preview(CONTRACT, -1)
        with self.assertRaises(PilotError):
            paper_preview({**CONTRACT, "lotSize": True}, 100)
        with self.assertRaises(PilotError):
            paper_preview(CONTRACT, 0.5, risk=300)

    def test_real_order_route_is_always_hard_blocked(self):
        assert hard_block_order()["error"] == "REAL_ORDERS_HARD_LOCKED"
        assert hard_block_order()["orderSent"] is False


class PilotIsolationTests(TestCase):
    @patch("ops.angel_ssh_readonly_pilot.verify_aws_readiness")
    @patch("ops.angel_ssh_readonly_pilot._safe_login_and_marketdata")
    def test_no_connect_does_not_prompt_for_secrets(self, connect, verify):
        stdout = io.StringIO()
        with redirect_stdout(stdout):
            status = main(["--expected-ip", "43.204.246.235"])
        self.assertEqual(status, 0)
        verify.assert_called_once_with("43.204.246.235")
        connect.assert_not_called()
        self.assertIn("NO_BROKER_LOGIN_ATTEMPTED", stdout.getvalue())

    @patch("ops.angel_ssh_readonly_pilot.verify_aws_readiness")
    @patch("ops.angel_ssh_readonly_pilot._safe_login_and_marketdata")
    def test_explicit_connect_only_after_precheck(self, connect, verify):
        self.assertEqual(main(["--expected-ip", "43.204.246.235", "--connect"]), 0)
        verify.assert_called_once()
        connect.assert_called_once()

    @patch("ops.angel_ssh_readonly_pilot.verify_aws_readiness")
    @patch("ops.angel_ssh_readonly_pilot._safe_login_and_marketdata")
    def test_precheck_failure_prevents_login(self, connect, verify):
        from ops.verify_angel_aws_readiness import ReadinessError
        verify.side_effect = ReadinessError("test mismatch")
        stderr = io.StringIO()
        with redirect_stderr(stderr):
            out = main(["--expected-ip", "43.204.246.235", "--connect"])
        self.assertEqual(out, 1)
        connect.assert_not_called()
        self.assertIn("AWS_SAFETY_PRECHECK_FAILED", stderr.getvalue())

    @patch("ops.angel_ssh_readonly_pilot.verify_aws_readiness")
    def test_non_public_ip_precheck_not_called(self, verify):
        with redirect_stderr(io.StringIO()):
            status = main(["--expected-ip", "127.0.0.1", "--connect"])
        self.assertEqual(status, 1)
        verify.assert_not_called()
