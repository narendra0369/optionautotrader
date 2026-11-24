"""Offline, no-network tests for durable OptionX NFO research paper journal."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
import tempfile
from pathlib import Path
from unittest import TestCase

from ops.paper_ledger_v1 import PaperError, open_paper, monitor_paper, status
from live_gateway import hard_block_order

NOW = datetime(2026, 11, 24, 5, 0, tzinfo=timezone.utc)  # 10:30 AM IST
CONTRACT = {
    "market": "NIFTY", "exchange": "NFO", "side": "CE",
    "symbol": "NIFTY01DEC2626000CE", "token": "47895",
    "lotSize": 65, "tickSize": 0.05,
}

def quote(ltp, at=NOW, contract=CONTRACT):
    return {
        "ltp": ltp, "observedAt": at.isoformat(), "contract": contract,
        "exchangeTimestampVerified": False, "executionPriceVerified": False,
    }


class DurablePaperTests(TestCase):
    def setUp(self):
        self.td = tempfile.TemporaryDirectory()
        self.addCleanup(self.td.cleanup)
        self.db = Path(self.td.name) / "paper.sqlite3"

    def test_open_default_12_lots_at_500k_and_persist(self):
        p = open_paper(self.db, CONTRACT, quote(62.15), now=NOW)
        self.assertEqual(p["mode"], "PAPER_OPEN_SIMULATED")
        self.assertEqual(p["lots"], 12)
        self.assertEqual(p["qty"], 780)
        self.assertEqual(p["illustrativeStop"], "57.55")
        self.assertEqual(p["illustrativeTarget"], "71.40")
        self.assertFalse(p["canSubmitOrder"])
        s = status(self.db, now=NOW)
        self.assertEqual(s["openPosition"]["symbol"], CONTRACT["symbol"])
        self.assertEqual(s["tradesToday"], 1)
        self.assertEqual(s["paperPlan"]["illustrativeLots"], 12)

    def test_one_lot_open_manual_override(self):
        p = open_paper(self.db, CONTRACT, quote(62.15), now=NOW, lots=1)
        self.assertEqual(p["lots"], 1)
        self.assertEqual(p["qty"], 65)

    def test_duplicate_open_blocked(self):
        open_paper(self.db, CONTRACT, quote(62.15), now=NOW)
        with self.assertRaisesRegex(PaperError, "EXISTING_PAPER_POSITION_OPEN"):
            open_paper(self.db, CONTRACT, quote(62.15), now=NOW + timedelta(seconds=15))
        self.assertEqual(status(self.db, now=NOW)["tradesToday"], 1)

    def test_quote_observation_no_trigger_and_persist(self):
        open_paper(self.db, CONTRACT, quote(62.15), now=NOW, lots=1)
        later = NOW + timedelta(seconds=20)
        r = monitor_paper(self.db, CONTRACT, quote(63, later), now=later)
        self.assertFalse(r["paperClosed"])
        self.assertEqual(status(self.db, now=later)["openPosition"]["last_quote"], "63")

    def test_stop_trigger_at_actual_observed_ltp_not_guaranteed_stop(self):
        open_paper(self.db, CONTRACT, quote(62.15), now=NOW, lots=1)
        later = NOW + timedelta(minutes=15)
        r = monitor_paper(self.db, CONTRACT, quote(55, later), now=later)
        self.assertTrue(r["paperClosed"])
        self.assertEqual(r["trigger"], "STOP_OBSERVED")
        s = status(self.db, now=later)
        self.assertIsNone(s["openPosition"])
        self.assertEqual(s["realizedEquityBeforeChargesINR"], str(500000 + (55 - 62.15)*65))
        self.assertEqual(s["tradesToday"], 1)

    def test_target_trigger(self):
        open_paper(self.db, CONTRACT, quote(62.15), now=NOW, lots=1)
        later = NOW + timedelta(minutes=10)
        r = monitor_paper(self.db, CONTRACT, quote(72, later), now=later)
        self.assertEqual(r["trigger"], "TARGET_OBSERVED")
        self.assertFalse(status(self.db, now=later)["openPosition"])

    def test_wrong_token_blocked(self):
        open_paper(self.db, CONTRACT, quote(62.15), now=NOW, lots=1)
        wrong = {**CONTRACT, "token": "12345"}
        with self.assertRaisesRegex(PaperError, "PAPER_POSITION_CONTRACT_MISMATCH"):
            monitor_paper(self.db, wrong, quote(72, NOW+timedelta(minutes=1),wrong),
                          now=NOW+timedelta(minutes=1))

    def test_reject_after_hours(self):
        with self.assertRaisesRegex(PaperError, "OUTSIDE_NSE_SESSION"):
            open_paper(self.db, CONTRACT, quote(62.15, NOW+timedelta(hours=8)),
                       now=NOW+timedelta(hours=8))

    def test_reject_quote_stale(self):
        with self.assertRaisesRegex(PaperError, "QUOTE_OBSERVATION_STALE"):
            open_paper(self.db, CONTRACT, quote(62.15, NOW-timedelta(minutes=2)), now=NOW)

    def test_one_per_day_limit_from_risk_policy(self):
        open_paper(self.db, CONTRACT, quote(62.15), now=NOW, lots=1)
        later=NOW+timedelta(minutes=1)
        monitor_paper(self.db, CONTRACT, quote(72,later),now=later)
        open_paper(self.db, CONTRACT, quote(62.15,later+timedelta(minutes=1)),
                   now=later+timedelta(minutes=1),lots=1)
        later2=later+timedelta(minutes=2)
        monitor_paper(self.db, CONTRACT, quote(72,later2),now=later2)
        with self.assertRaisesRegex(PaperError, "DAILY_TRADE_COUNT_LIMIT"):
            open_paper(self.db, CONTRACT, quote(62.15,later2+timedelta(minutes=1)),
                       now=later2+timedelta(minutes=1),lots=1)

    def test_bad_contract_and_plan_rejected(self):
        with self.assertRaises(PaperError):
            open_paper(self.db, {**CONTRACT,"lotSize":True},quote(62.15),now=NOW)
        with self.assertRaises(PaperError):
            open_paper(self.db, CONTRACT, quote(62.15),now=NOW,lots=13)
        with self.assertRaises(PaperError):
            open_paper(self.db, CONTRACT, quote(62.15),now=NOW,capital="1000")

    def test_no_broker_orders_in_module(self):
        self.assertEqual(hard_block_order()["error"], "REAL_ORDERS_HARD_LOCKED")
        import inspect
        import ops.paper_ledger_v1 as ledger
        source = inspect.getsource(ledger)
        self.assertNotIn("placeOrder",source)
        self.assertNotIn("apiconnect.angelone.in",source)
