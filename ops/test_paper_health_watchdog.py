"""No-network safety tests for the permanent, credential-free paper watchdog."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import os
from tempfile import TemporaryDirectory
from unittest import TestCase

from ops.paper_health_watchdog import (
    _age_seconds, inspect_one, market_clock_session, write_private_health,
    WatchdogError,
)

NOW = datetime(2026, 11, 24, 6, 0, tzinfo=timezone.utc)
AUDIT = {"audit": "PASS"}
HEALTHY = {
    "canSubmitOrder": False, "liveExecutionEnabled": False,
    "openPosition": None,
}


class PaperWatchdogTest(TestCase):
    def test_no_position_health_never_claims_execution(self):
        r = inspect_one(now=NOW, audit=AUDIT, snapshot=HEALTHY)
        self.assertEqual(r["status"], "HEALTHY_PAPER_LEDGER")
        self.assertFalse(r["continuousBrokerPriceStreaming"])
        self.assertFalse(r["automaticPaperEntryEnabled"])
        self.assertFalse(r["automaticPaperExitGuaranteed"])
        self.assertEqual(r["brokerOrdersSent"], 0)

    def test_stale_position_detected_and_never_claims_broker_stop(self):
        snapshot = {**HEALTHY, "openPosition": {
            "last_observed_utc": (NOW - timedelta(minutes=11)).isoformat(),
        }}
        r = inspect_one(now=NOW, audit=AUDIT, snapshot=snapshot)
        self.assertEqual(r["status"], "VIRTUAL_POSITION_UNMONITORED")
        self.assertIn("VIRTUAL_LAST_LTP_STALE", r["warnings"])
        self.assertFalse(r["angelSessionConnected"])
        self.assertFalse(r["automaticPaperExitGuaranteed"])

    def test_recent_local_quote_is_not_guaranteed_protection(self):
        r = inspect_one(now=NOW, audit=AUDIT, snapshot={
            **HEALTHY, "openPosition": {
                "last_observed_utc": NOW.isoformat()
            }
        })
        self.assertIn("RECENT_LOCAL_LTP_IS_NOT_BROKER_STOP_COVERAGE", r["warnings"])
        self.assertFalse(r["brokerQuoteFreshnessVerified"])

    def test_unknown_quote_timestamp_marks_unmonitored(self):
        r = inspect_one(now=NOW, audit=AUDIT, snapshot={
            **HEALTHY, "openPosition": {"last_observed_utc": "broken"}
        })
        self.assertIsNone(r["indicativeQuoteAgeSeconds"])
        self.assertIn("VIRTUAL_LTP_AGE_UNKNOWN", r["warnings"])

    def test_invalid_paper_safety_snapshot_fails_closed(self):
        with self.assertRaisesRegex(WatchdogError, "UNSAFE"):
            inspect_one(now=NOW, audit=AUDIT, snapshot={**HEALTHY, "canSubmitOrder": True})
        with self.assertRaisesRegex(WatchdogError, "UNSAFE"):
            inspect_one(now=NOW, audit={"audit":"FAILED"}, snapshot=HEALTHY)

    def test_clock_is_not_exchange_holiday_calendar(self):
        self.assertTrue(market_clock_session(NOW))
        self.assertFalse(market_clock_session(datetime(2026, 11, 22, 6, 0, tzinfo=timezone.utc)))
        self.assertFalse(market_clock_session(datetime(2026, 11, 24, 19, 0, tzinfo=timezone.utc)))
        self.assertFalse(inspect_one(now=NOW, audit=AUDIT, snapshot=HEALTHY)["exchangeHolidayCalendarVerified"])

    def test_owner_only_atomic_write(self):
        with TemporaryDirectory() as root:
            directory=Path(root)
            directory.chmod(0o700)
            health=directory/"health.json"
            report=inspect_one(now=NOW, audit=AUDIT, snapshot=HEALTHY)
            write_private_health(report, health)
            self.assertEqual(health.stat().st_mode & 0o777, 0o600)
            self.assertEqual(json.loads(health.read_text())["status"], "HEALTHY_PAPER_LEDGER")
            write_private_health(report, health)
            self.assertEqual(json.loads(health.read_text())["brokerOrdersSent"], 0)

    def test_symlink_output_refused(self):
        with TemporaryDirectory() as root:
            directory=Path(root)
            directory.chmod(0o700)
            original=directory/"other"
            original.write_text("do not overwrite")
            target=directory/"watchdog-health.json"
            target.symlink_to(original)
            with self.assertRaisesRegex(WatchdogError, "SYMLINK"):
                write_private_health({"status": "x"}, target)
            self.assertEqual(original.read_text(), "do not overwrite")

    def test_world_readable_parent_refused(self):
        with TemporaryDirectory() as root:
            directory=Path(root)
            directory.chmod(0o755)
            with self.assertRaisesRegex(WatchdogError, "PERMISSIONS_UNSAFE"):
                write_private_health({"status": "x"}, directory/"health.json")
