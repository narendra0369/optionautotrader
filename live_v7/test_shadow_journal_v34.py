"""V34 simulated persistence, duplicate and recovery tests, no broker writes."""
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from live_v7.shadow_journal_v34 import (
    open_shadow, stage, transition, recover, ShadowBlocked)

OWNER = "11111111-1111-4111-8111-111111111111"
OTHER = "22222222-2222-4222-8222-222222222222"
NOW = datetime(2026, 11, 26, 7, 0, tzinfo=timezone.utc)
KEY = "shadow-20261126"
DRAFT = {"contract": "NIFTY29DEC2629000CE", "token": "38158",
         "quantity": 65, "side": "SELL", "orderType": "LIMIT",
         "limit": "10.50", "canSubmitOrder": False,
         "submittedOrder": False, "realOrdersEnabled": False}


class V34ShadowJournalTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = str(Path(self.tmp.name) / "shadow.sqlite3")
        self.db = open_shadow(self.path)

    def tearDown(self):
        self.db.close()
        self.tmp.cleanup()

    def start(self, **kwargs):
        return stage(self.db, owner_id=kwargs.get("owner", OWNER),
                     idempotency_key=kwargs.get("key", KEY),
                     draft=kwargs.get("draft", DRAFT), now=NOW)

    def test_create_draft_is_not_order(self):
        row = self.start()
        self.assertEqual(row["status"], "DRAFT")
        self.assertFalse(row["canSubmitOrder"])

    def test_duplicate_same_payload_cannot_resend(self):
        self.start()
        row = self.start()
        self.assertEqual(row["result"], "EXISTING_SHADOW_NO_RESEND")
        self.assertFalse(row["canRetryBrokerSend"])

    def test_changed_payload_blocked_before_duplicate_check(self):
        self.start()
        with self.assertRaisesRegex(ShadowBlocked, "DRAFT_MISMATCH"):
            self.start(draft=dict(DRAFT, limit="10.55"))

    def test_unknown_send_is_simulated_only(self):
        self.start()
        x = transition(self.db, owner_id=OWNER, idempotency_key=KEY,
                       event="SIMULATE_UNKNOWN", now=NOW)
        self.assertEqual(x["status"], "SIMULATED_SEND_UNKNOWN")
        self.assertFalse(x["canRetryBrokerSend"])

    def test_unknown_state_persists_after_restart(self):
        self.start()
        transition(self.db, owner_id=OWNER, idempotency_key=KEY,
                   event="SIMULATE_UNKNOWN", now=NOW)
        self.db.close()
        self.db = open_shadow(self.path)
        rec = recover(self.db, owner_id=OWNER, idempotency_key=KEY)
        self.assertEqual(rec["status"], "SIMULATED_SEND_UNKNOWN")
        self.assertTrue(rec["requiresBrokerIndependentReconciliation"])
        self.assertFalse(rec["canSubmitOrder"])

    def test_unknown_cannot_transition_to_ack(self):
        self.start()
        transition(self.db, owner_id=OWNER, idempotency_key=KEY,
                   event="SIMULATE_UNKNOWN", now=NOW)
        with self.assertRaisesRegex(ShadowBlocked, "NOT_ALLOWED"):
            transition(self.db, owner_id=OWNER, idempotency_key=KEY,
                       event="SIMULATE_ACK", now=NOW)

    def test_unknown_only_moves_to_review(self):
        self.start()
        transition(self.db, owner_id=OWNER, idempotency_key=KEY,
                   event="SIMULATE_UNKNOWN", now=NOW)
        rec = transition(self.db, owner_id=OWNER, idempotency_key=KEY,
                         event="RECONCILE_REVIEW", now=NOW)
        self.assertEqual(rec["status"], "REVIEW_REQUIRED")

    def test_review_is_terminal(self):
        self.start()
        transition(self.db, owner_id=OWNER, idempotency_key=KEY,
                   event="HOLD", now=NOW)
        with self.assertRaises(ShadowBlocked):
            transition(self.db, owner_id=OWNER, idempotency_key=KEY,
                       event="SIMULATE_ACK", now=NOW)

    def test_ack_is_simulated_not_broker_verified(self):
        self.start()
        x = transition(self.db, owner_id=OWNER, idempotency_key=KEY,
                       event="SIMULATE_ACK", now=NOW)
        self.assertFalse(x["canSubmitOrder"])

    def test_owner_isolated(self):
        self.start()
        with self.assertRaisesRegex(ShadowBlocked, "NOT_FOUND"):
            recover(self.db, owner_id=OTHER, idempotency_key=KEY)

    def test_unknown_owner_is_not_valid(self):
        with self.assertRaisesRegex(ShadowBlocked, "OWNER_UUID"):
            self.start(owner="bad")

    def test_invalid_key_rejected(self):
        with self.assertRaisesRegex(ShadowBlocked, "IDEMPOTENCY_KEY"):
            self.start(key="short")

    def test_secrets_cannot_be_stored_in_draft(self):
        with self.assertRaisesRegex(ShadowBlocked, "EXTRA_DRAFT"):
            self.start(draft=dict(DRAFT, api_key="not-a-real-key"))

    def test_execution_flags_never_true(self):
        with self.assertRaisesRegex(ShadowBlocked, "EXECUTION_FLAG"):
            self.start(draft=dict(DRAFT, canSubmitOrder=True))

    def test_unauthorized_contract_rejected(self):
        with self.assertRaises(ShadowBlocked):
            self.start(draft=dict(DRAFT, contract="BANKNIFTY"))

    def test_missing_intent_cannot_recover(self):
        with self.assertRaisesRegex(ShadowBlocked, "NOT_FOUND"):
            recover(self.db, owner_id=OWNER, idempotency_key=KEY)

    def test_events_are_append_only_by_api(self):
        self.start()
        transition(self.db, owner_id=OWNER, idempotency_key=KEY,
                   event="SIMULATE_UNKNOWN", now=NOW)
        count=self.db.execute("SELECT COUNT(*) FROM shadow_events").fetchone()[0]
        self.assertEqual(count,2)

    def test_no_order_transport_imports(self):
        source=Path(__file__).with_name("shadow_journal_v34.py").read_text()
        for bad in ("placeOrder", "cancelOrder", "modifyOrder", "angel_gateway",
                    "angel_execution_transport", "psycopg", "requests.post"):
            self.assertNotIn(bad, source)

if __name__ == "__main__":
    unittest.main()
