"""Offline-only unit tests, deliberately never import a broker module."""
import unittest
from dataclasses import replace
from scripts.optionx_v83_offline_safety import (
    GateInputs, diagnostic_scope_allowed, live_execution_permitted,
    PaperRisk, OfflineOrder, OrderState, mock_fill, mock_cancel, mock_exit
)

class FourGateTests(unittest.TestCase):
    def test_default_stops_and_orders_never_authorized(self):
        self.assertFalse(diagnostic_scope_allowed(GateInputs("status.read")))
        strong = GateInputs("status.read", True, True, True, True, True, True, True, False)
        self.assertTrue(diagnostic_scope_allowed(strong))
        for scope in ("order.place", "order.cancel", "order.modify", "broker.call", "stop.clear", "other"):
            self.assertFalse(diagnostic_scope_allowed(replace(strong, scope=scope)))
            self.assertFalse(live_execution_permitted(replace(strong, scope=scope)))
        self.assertFalse(live_execution_permitted(strong))

    def test_missing_attestation_independence_or_freshness_denied(self):
        strong = GateInputs("diagnostics.read", True, True, True, True, True, True, True, True)
        for field in ("owner_authenticated", "independently_attested", "reviewer_separate",
                      "proof_fresh", "nonce_unique", "reviewer_not_revoked", "worker_verified"):
            with self.subTest(field=field):
                self.assertFalse(diagnostic_scope_allowed(replace(strong, **{field: False})))

    def test_paper_stepped_tier_preserved(self):
        for balance, lots in ((30000,1),(69999,1),(70000,2),(500000,12)):
            p = PaperRisk(balance, 0)
            self.assertEqual(p.lots, lots)
            self.assertEqual(p.trade_risk, 300 * lots)
            self.assertEqual(p.target, 600 * lots)
            self.assertEqual(p.daily_loss_limit, 600 * lots)
            self.assertFalse(p.new_paper_entry_allowed(True))
            self.assertTrue(p.new_paper_entry_allowed(False))
            self.assertFalse(replace(p, entries_today=2).new_paper_entry_allowed(False))

    def test_partial_fill_cancel_requires_reconciliation(self):
        order = mock_fill(OfflineOrder(65), 20)
        self.assertEqual(order.state, OrderState.PARTIAL)
        self.assertEqual(mock_cancel(order).state, OrderState.NEEDS_RECONCILIATION)

    def test_full_fill_sl_exit(self):
        order = mock_fill(OfflineOrder(65), 65)
        self.assertEqual(order.state, OrderState.FILLED)
        self.assertEqual(mock_exit(order, 65, "SL").state, OrderState.CLOSED)

    def test_target_partial_exit_not_marked_flat(self):
        order = mock_fill(OfflineOrder(65), 65)
        self.assertEqual(mock_exit(order, 20, "TARGET").state, OrderState.NEEDS_RECONCILIATION)

    def test_bad_quantities_and_double_cancel_denied(self):
        order = OfflineOrder(65)
        with self.assertRaises(ValueError): mock_fill(order, 66)
        cancelled = mock_cancel(order)
        with self.assertRaises(ValueError): mock_cancel(cancelled)
        with self.assertRaises(ValueError): mock_exit(order, 1, "SL")

if __name__ == "__main__":
    unittest.main()
