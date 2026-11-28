"""No-network Angel lifecycle rehearsal tests; real orders are always OFF."""
import unittest
from copy import deepcopy
from datetime import datetime, timedelta, timezone
from pathlib import Path
from live_v7.angel_execution_rehearsal import verify_rehearsal

NOW = datetime(2026, 11, 25, 4, 0, tzinfo=timezone.utc)


def fixture():
    return dict(
        expected_owner_id="verified-owner-123",
        expected_entry_order_id="order_12345",
        expected_symbol="NIFTY01DEC2624450CE",
        expected_token="token987",
        expected_quantity=65,
        count_entries_today=1,
        broker_orderbook=[dict(
            order_id="order_12345", symbol="NIFTY01DEC2624450CE",
            side="BUY", quantity=65, filled_quantity=65, status="COMPLETE")],
        broker_positions=[dict(
            symbol="NIFTY01DEC2624450CE", instrumentToken="token987", net_quantity=65)],
        protection_orderbook=[dict(
            broker="Angel", broker_order_id="stop_78910",
            contract_token="token987", contract_symbol="NIFTY01DEC2624450CE",
            action="EXIT_SELL", status="TRIGGER_PENDING",
            protected_quantity=65, as_of=NOW)],
        trusted_meta=dict(
            broker="Angel", owner_id="verified-owner-123",
            broker_tls_authenticated=True, owner_session_verified=True,
            source_is_readonly=True, unknown_order_outcomes=False,
            manual_intervention_pending=False, observed_at=NOW),
        now=NOW,
    )


class AngelLifecycleRehearsalTests(unittest.TestCase):
    def verify(self, **overrides):
        data=fixture()
        data.update(overrides)
        return verify_rehearsal(**data)

    def test_full_snapshot_may_pass_rehearsal_but_never_authorizes_real_order(self):
        result=self.verify()
        self.assertTrue(result["protectiveStopVerifiedForRehearsal"])
        self.assertEqual(result["blockedReasons"], ["BROKER_EXECUTION_NOT_IMPLEMENTED"])
        self.assertFalse(result["canSubmitOrder"])
        self.assertFalse(result["canModifyOrder"])
        self.assertFalse(result["canCancelOrder"])
        self.assertTrue(result["newEntriesBlocked"])

    def test_partial_fill_always_blocks(self):
        d=fixture()
        d["broker_orderbook"][0].update(status="PARTIALLY_FILLED", filled_quantity=20)
        d["broker_positions"][0]["net_quantity"]=20
        d["protection_orderbook"][0]["protected_quantity"]=20
        r=verify_rehearsal(**d)
        self.assertIn("ENTRY_NOT_FULLY_CONFIRMED",r["blockedReasons"])

    def test_rejected_stop_blocks(self):
        d=fixture()
        d["protection_orderbook"][0]["status"]="REJECTED"
        r=verify_rehearsal(**d)
        self.assertIn("STOP_NOT_ACTIVE_ON_BROKER",r["blockedReasons"])

    def test_stale_broker_account_snapshot_blocks(self):
        d=fixture()
        d["trusted_meta"]["observed_at"]=NOW-timedelta(minutes=2)
        r=verify_rehearsal(**d)
        self.assertIn("BROKER_SNAPSHOT_STALE_OR_MISSING",r["blockedReasons"])

    def test_wrong_owner_blocks(self):
        d=fixture()
        d["trusted_meta"]["owner_id"]="another-owner"
        r=verify_rehearsal(**d)
        self.assertIn("BROKER_OWNER_MISMATCH",r["blockedReasons"])

    def test_duplicate_broker_order_blocks(self):
        d=fixture()
        d["broker_orderbook"].append(deepcopy(d["broker_orderbook"][0]))
        r=verify_rehearsal(**d)
        self.assertIn("ENTRY_MISSING_OR_DUPLICATE_IN_BROKER_BOOK",r["blockedReasons"])

    def test_quantity_mismatch_blocks(self):
        d=fixture()
        d["broker_positions"][0]["net_quantity"]=20
        d["protection_orderbook"][0]["protected_quantity"]=20
        r=verify_rehearsal(**d)
        self.assertIn("BROKER_POSITION_FILL_MISMATCH",r["blockedReasons"])
        self.assertIn("STOP_DOES_NOT_COVER_CONFIRMED_FILL",r["blockedReasons"])

    def test_unknown_order_outcome_blocks(self):
        d=fixture()
        d["trusted_meta"]["unknown_order_outcomes"]=True
        r=verify_rehearsal(**d)
        self.assertIn("UNKNOWN_ORDER_OUTCOME",r["blockedReasons"])

    def test_daily_two_entries_block_new_trades(self):
        r=self.verify(count_entries_today=2)
        self.assertIn("TWO_DAILY_ENTRIES_ALREADY_USED",r["blockedReasons"])

    def test_noninteger_or_boolean_quantity_blocks(self):
        r=self.verify(expected_quantity=True)
        self.assertIn("EXPECTED_QUANTITY_INVALID",r["blockedReasons"])

    def test_missing_book_blocks(self):
        r=self.verify(protection_orderbook=None)
        self.assertIn("BROKER_BOOKS_MISSING",r["blockedReasons"])

    def test_no_live_broker_write_code_or_urls(self):
        src=Path(__file__).with_name("angel_execution_rehearsal.py").read_text()
        for forbidden in ("placeOrder(", "modifyOrder(", "cancelOrder(", "urlopen(", "requests.post(", "smartapi.angelone.in/rest/secure/angelbroking/order/v1/placeOrder"):
            self.assertNotIn(forbidden,src)


if __name__=="__main__":
    unittest.main()
