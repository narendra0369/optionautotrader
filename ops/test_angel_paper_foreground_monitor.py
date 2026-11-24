"""Offline foreground paper monitor tests. No credentials, network or orders."""
from __future__ import annotations

from datetime import datetime, timezone
import io
from contextlib import redirect_stderr
from unittest import TestCase
from unittest.mock import patch

from ops import angel_paper_foreground_monitor as monitor


SAVED = {
    "id": 1, "status": "OPEN", "token": "47895",
    "symbol": "NIFTY01DEC2626000CE", "side": "CE",
    "market": "NIFTY", "lot_size": 65, "quantity": 65,
}
VERIFIED = {
    "token": "47895", "symbol": "NIFTY01DEC2626000CE",
    "side": "CE", "market": "NIFTY", "lotSize": 65, "exchange": "NFO",
}


class ForegroundMonitorOfflineTests(TestCase):
    def test_market_hours_ist_1030(self):
        self.assertTrue(monitor.exchange_hours(datetime(2026, 11, 24, 5, 0, tzinfo=timezone.utc)))

    def test_market_hours_reject_evening_and_weekend(self):
        self.assertFalse(monitor.exchange_hours(datetime(2026, 11, 24, 18, 0, tzinfo=timezone.utc)))
        self.assertFalse(monitor.exchange_hours(datetime(2026, 11, 22, 5, 0, tzinfo=timezone.utc)))

    def test_market_hours_invalid_timestamp_fails_closed(self):
        self.assertFalse(monitor.exchange_hours(datetime(2026, 11, 24, 5, 0)))

    def test_master_contract_matches_persisted_token_symbol_and_lot(self):
        self.assertEqual(
            monitor.verified_contract_for_position(SAVED, master={"47895": VERIFIED}),
            VERIFIED
        )

    def test_token_or_lot_mismatch_blocks_virtual_monitor(self):
        with self.assertRaisesRegex(monitor.MonitorError, "NOT_IN_CURRENT_MASTER"):
            monitor.verified_contract_for_position(SAVED, master={"47894": VERIFIED})
        with self.assertRaisesRegex(monitor.MonitorError, "CONTRACT_DOES_NOT_MATCH"):
            monitor.verified_contract_for_position(SAVED, master={"47895": {**VERIFIED, "lotSize": 50}})

    @patch.object(monitor, "monitor_paper")
    def test_quote_contract_change_is_blocked_before_ledger_write(self, ledger):
        with self.assertRaisesRegex(monitor.MonitorError, "BROKER_QUOTE_CONTRACT_CHANGED"):
            monitor.observe_once("ignored.sqlite3", SAVED, VERIFIED,
                                 {"contract": {**VERIFIED, "token": "999"}})
        ledger.assert_not_called()

    @patch.object(monitor, "monitor_paper")
    def test_quote_observation_only_in_virtual_ledger(self, ledger):
        ledger.return_value = {"brokerOrdersSent": 0, "canSubmitOrder": False,
                               "quoteLtp": "63.5", "paperClosed": False, "trigger": "NONE"}
        observed = monitor.observe_once("ignored.sqlite3", SAVED, VERIFIED, {"contract": VERIFIED})
        self.assertFalse(observed["paperClosed"])
        ledger.assert_called_once()

    @patch.object(monitor, "monitor_paper")
    def test_fail_closed_on_unexpected_order_capability(self, ledger):
        ledger.return_value = {"brokerOrdersSent": 1, "canSubmitOrder": True}
        with self.assertRaisesRegex(monitor.MonitorError, "PAPER_RESULT_NOT_SAFE"):
            monitor.observe_once("ignored.sqlite3", SAVED, VERIFIED, {"contract": VERIFIED})

    @patch.object(monitor, "run_foreground")
    def test_invalid_poll_interval_or_duration_never_connects(self, runner):
        with redirect_stderr(io.StringIO()):
            self.assertEqual(monitor.main(["--expected-ip", "43.204.246.235", "--interval", "1"]), 1)
            self.assertEqual(monitor.main(["--expected-ip", "43.204.246.235", "--minutes", "13"]), 1)
        runner.assert_not_called()
