"""Offline tests: API transport is present but impossible to invoke LIVE."""
import unittest
from live_v7.angel_execution_transport import (
    AngelTransportBlocked, TrustedServerSession,
    request, capabilities,
)

OWNER = "verified-owner-001"


def session(**updates):
    obj = {"api_key": "local_test_api_key", "jwt": "synthetic.jwt.value",
           "owner_id": OWNER, "egress_ip": "43.204.246.235",
           "broker_api_approved": True}
    obj.update(updates)
    return TrustedServerSession(**obj)


def gates(**updates):
    x = dict.fromkeys((
        "broker_approval_proven", "durable_journal_healthy",
        "worker_owner_bound", "protective_stop_recovery_tested",
        "kill_switch_persisted_and_clear", "broker_snapshot_reconciled",
        "risk_budget_approved",
    ), True)
    x.update(updates)
    return x


def entry():
    return {"variety": "NORMAL", "tradingsymbol": "NIFTY01DEC2624450CE",
            "symboltoken": "123456", "transactiontype": "BUY",
            "exchange": "NFO", "ordertype": "LIMIT",
            "producttype": "INTRADAY", "duration": "DAY",
            "price": "100.05", "quantity": "65"}


class AngelExecutionTransportTests(unittest.TestCase):
    def test_source_lock_even_with_all_approval_flags_true(self):
        called = []
        with self.assertRaisesRegex(AngelTransportBlocked, "SOURCE_LOCKED"):
            request(operation="place", session=session(), expected_owner_id=OWNER,
                    execution_gate=gates(), payload=entry(),
                    fetch=lambda *a, **k: called.append(True))
        self.assertEqual(called, [])

    def test_no_network_for_orderbook_or_cancel(self):
        seen = []
        for op, payload in (("orderbook", None),
                            ("cancel", {"variety": "NORMAL", "orderid": "123456"})):
            with self.assertRaisesRegex(AngelTransportBlocked, "SOURCE_LOCKED"):
                request(operation=op, session=session(), expected_owner_id=OWNER,
                        execution_gate=gates(), payload=payload,
                        fetch=lambda *a, **k: seen.append(True))
        self.assertEqual(seen, [])

    def test_wrong_owner_blocked(self):
        with self.assertRaisesRegex(AngelTransportBlocked, "OWNER"):
            request(operation="place", session=session(), expected_owner_id="other-owner-01",
                    execution_gate=gates(), payload=entry())

    def test_wrong_egress_blocked(self):
        with self.assertRaisesRegex(AngelTransportBlocked, "EGRESS"):
            request(operation="place", session=session(egress_ip="8.8.8.8"),
                    expected_owner_id=OWNER, execution_gate=gates(), payload=entry())

    def test_missing_broker_approval_blocked(self):
        with self.assertRaisesRegex(AngelTransportBlocked, "BROKER_EXECUTION_APPROVAL"):
            request(operation="place", session=session(broker_api_approved=False),
                    expected_owner_id=OWNER, execution_gate=gates(), payload=entry())

    def test_missing_durable_journal_blocked(self):
        with self.assertRaisesRegex(AngelTransportBlocked, "PRODUCTION_SAFETY"):
            request(operation="place", session=session(), expected_owner_id=OWNER,
                    execution_gate=gates(durable_journal_healthy=False), payload=entry())

    def test_market_order_blocked(self):
        p = entry(); p["ordertype"] = "MARKET"
        with self.assertRaisesRegex(AngelTransportBlocked, "ORDER_TYPE"):
            request(operation="place", session=session(), expected_owner_id=OWNER,
                    execution_gate=gates(), payload=p)

    def test_reject_entry_from_wrong_exchange(self):
        p = entry(); p["exchange"] = "NSE"
        with self.assertRaisesRegex(AngelTransportBlocked, "WRONG_EXCHANGE"):
            request(operation="place", session=session(), expected_owner_id=OWNER,
                    execution_gate=gates(), payload=p)

    def test_stoploss_limit_payload_accepted_but_source_locked(self):
        p = entry(); p.update(variety="STOPLOSS", transactiontype="SELL",
                              ordertype="STOPLOSS_LIMIT", triggerprice="95.00", price="94.50")
        with self.assertRaisesRegex(AngelTransportBlocked, "SOURCE_LOCKED"):
            request(operation="place", session=session(), expected_owner_id=OWNER,
                    execution_gate=gates(), payload=p)

    def test_unexpected_operation_rejected(self):
        with self.assertRaisesRegex(AngelTransportBlocked, "OPERATION_NOT_ALLOWLISTED"):
            request(operation="modify", session=session(), expected_owner_id=OWNER,
                    execution_gate=gates(), payload=None)

    def test_redacted_session_and_false_live_capability(self):
        self.assertNotIn("local_test_api_key", repr(session()))
        cap = capabilities()
        self.assertFalse(cap["canSubmitOrder"])
        self.assertFalse(cap["realOrdersEnabled"])
        self.assertTrue(cap["sourceLockEnabled"])


if __name__ == "__main__":
    unittest.main()
