"""Offline tests: private HTML dashboard, on-disk recovery audit and safe backups."""
from __future__ import annotations

from datetime import datetime, timezone, timedelta
from pathlib import Path
import os
import sqlite3
import tempfile
from unittest import TestCase

from ops import private_paper_dashboard as dashboard
from ops.paper_recovery_audit import AuditError, integrity_report, backup_private
from ops.paper_ledger_v1 import _db, _init, open_paper

NOW = datetime(2026, 11, 24, 5, 0, tzinfo=timezone.utc)
CONTRACT = {
    "market": "NIFTY", "exchange": "NFO", "side": "CE",
    "symbol": "NIFTY01DEC2626000CE", "token": "47895",
    "lotSize": 65, "tickSize": 0.05,
}
QUOTE = {"contract": CONTRACT, "ltp": 62.15, "observedAt": NOW.isoformat()}


class PaperDashboardSafetyTests(TestCase):
    def test_binds_loopback_only_fixed_port(self):
        self.assertEqual(dashboard.BIND_HOST, "127.0.0.1")
        self.assertEqual(dashboard.BIND_PORT, 10001)
        self.assertEqual(dashboard.PUBLIC_TUNNEL_PORT, 18751)
        self.assertNotIn("43.204.246.235:10001", dashboard._ALLOWED_HOSTS)

    def test_premium_dashboard_is_readonly_and_escapes_symbols(self):
        preview = {
            "initialCapitalINR": "500000",
            "realizedEquityBeforeChargesINR": "500000",
            "todayGrossPnlBeforeChargesINR": "-300",
            "tradesToday": 1, "maxTradesPerDay": 2,
            "paperPlan": {"illustrativeLots": 12},
            "openPosition": {
                "symbol": '<script>alert("evil")</script>', "lots": 1,
                "quantity": 65, "indicative_entry": "62.15",
                "illustrative_stop": "57.55", "illustrative_target": "71.4",
                "last_quote": "62.15", "last_observed_utc": NOW.isoformat(),
            },
            "recentTrades": [{"symbol": '<img src=x onerror="alert(1)">',
                              "status": "OPEN", "quantity": 65, "gross_pnl": None}],
        }
        page = dashboard.make_view(preview, now=NOW)
        self.assertIn("OPTION", page)
        self.assertIn("AI TRADER", page)
        self.assertIn("₹500,000.00", page)
        self.assertIn("₹-300.00", page)
        self.assertNotIn('<script>alert("evil")', page)
        self.assertNotIn('<img src=x onerror=', page)
        self.assertIn("&lt;script&gt;", page)
        self.assertIn("PAPER ONLY", page)
        self.assertIn("not exchange fills", page)

    def test_missing_paper_snapshot_has_no_fake_returns(self):
        html = dashboard.make_view(error="UNAVAILABLE", now=NOW)
        self.assertIn("Not available", html)
        self.assertIn("will not", html)
        self.assertNotIn("₹500,000.00", html)


class RecoveryAuditOfflineTests(TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / "paper.sqlite3"
        old_mask = os.umask(0o077)
        try:
            with _db(self.path) as conn:
                _init(conn, "500000")
        finally:
            os.umask(old_mask)
        self.path.chmod(0o600)

    def test_audit_one_initialized_paper_account_no_broker(self):
        summary = integrity_report(self.path, now=NOW, strict_ownership=True)
        self.assertEqual(summary["audit"], "PASS")
        self.assertEqual(summary["sqliteQuickCheck"], "ok")
        self.assertEqual(summary["virtualCapitalINR"], "500000")
        self.assertEqual(summary["virtualOpenPositions"], 0)
        self.assertFalse(summary["liveOrdersEnabled"])

    def test_open_paper_trade_is_just_virtual(self):
        open_paper(self.path, CONTRACT, QUOTE, now=NOW, lots=1)
        outcome = integrity_report(self.path, now=NOW)
        self.assertEqual(outcome["virtualOpenPositions"], 1)
        self.assertIn("OPEN_VIRTUAL_POSITION_REQUIRES_ACTIVE_MANUAL_MONITORING",
                      outcome["warnings"])

    def test_missing_database_does_not_create_it(self):
        missing = Path(self.temp.name) / "not-here.sqlite3"
        with self.assertRaisesRegex(AuditError, "PAPER_DB_MISSING"):
            integrity_report(missing)
        self.assertFalse(missing.exists())

    def test_symlink_source_is_rejected(self):
        pointer = Path(self.temp.name) / "point.sqlite3"
        pointer.symlink_to(self.path)
        with self.assertRaisesRegex(AuditError, "PAPER_DB_MISSING_OR_UNSAFE"):
            integrity_report(pointer)

    def test_corrupt_database_blocked(self):
        bad = Path(self.temp.name) / "corrupt.sqlite3"
        bad.write_bytes(b"corrupt database not sqlite")
        with self.assertRaises(sqlite3.DatabaseError):
            integrity_report(bad)

    def test_private_backup_is_consistent_and_never_restores(self):
        stamp = datetime(2026, 11, 24, 5, 25, 10, tzinfo=timezone.utc)
        output = backup_private(self.path, now=stamp, strict_ownership=True)
        backup_path = Path(output["file"])
        self.assertTrue(backup_path.is_file())
        self.assertEqual(backup_path.stat().st_mode & 0o777, 0o600)
        with sqlite3.connect(f"file:{backup_path}?mode=ro", uri=True) as check:
            self.assertEqual(check.execute("PRAGMA quick_check").fetchone(), ("ok",))
            self.assertEqual(check.execute("SELECT initial_capital FROM account").fetchone()[0], "500000")
        self.assertFalse(output["restoreAttempted"])
        self.assertFalse(output["liveOrdersEnabled"])
        with self.assertRaisesRegex(AuditError, "BACKUP_ALREADY_EXISTS"):
            backup_private(self.path, now=stamp)
        self.assertEqual(integrity_report(self.path)["virtualCapitalINR"], "500000")

    def test_backup_directory_must_remain_private(self):
        backups = self.path.parent / "backups"
        backups.mkdir(mode=0o700)
        backups.chmod(0o755)
        with self.assertRaisesRegex(AuditError, "BACKUP_DIRECTORY_NOT_PRIVATE"):
            backup_private(self.path)

    def test_broker_order_routes_absent_from_rollback_tools(self):
        import inspect
        from ops import paper_recovery_audit
        code = inspect.getsource(paper_recovery_audit)
        self.assertNotIn("placeOrder", code)
        self.assertNotIn("broker.connect", code)
        self.assertNotIn("rest/secure/angelbroking/order", code)
