"""No-network tests of all synthetic broker lifecycle failures and live-order lock."""
from __future__ import annotations

from unittest import TestCase
from unittest.mock import patch

from ops.synthetic_live_lifecycle_matrix import scenarios, run_suite, main


class SyntheticLifecycleMatrixTests(TestCase):
    def test_all_synthetic_scenarios_stay_fail_closed(self):
        result = run_suite()
        self.assertGreaterEqual(result["scenarioCount"], 20)
        self.assertEqual(result["passed"], result["scenarioCount"])
        self.assertFalse(result["liveTradingApproved"])
        self.assertFalse(result["realBrokerOrderTestsPerformed"])
        self.assertTrue(result["realOrderEndpointsStillLocked"])
        self.assertTrue(all(row["newEntriesBlocked"] and row["brokerOrdersSent"] == 0
                            for row in result["scenarios"]))

    def test_required_failure_cases_are_covered(self):
        cases = {row["name"] for row in scenarios()}
        required = {
            "missing_stop", "stop_unknown", "stop_rejected", "cancel_race",
            "partial_fill_after_stop", "duplicate_event_id", "broker_evidence_stale",
            "restart_without_full_reconciliation", "unauthenticated_broker_snapshot",
            "entry_acknowledgement_unknown", "unknown_reconciliation_unverified",
            "oversize_exit", "filled_then_exit_stop_orphan",
            "entry_rejected_after_fill", "future_event_not_accepted",
        }
        self.assertTrue(required <= cases)

    def test_unauthorized_live_order_lock_fails_suite(self):
        with patch("ops.synthetic_live_lifecycle_matrix.hard_block_order",
                   return_value={"error":"OK", "orderSent":True}):
            with self.assertRaisesRegex(AssertionError, "LIVE_ORDER_LOCK_MISSING"):
                run_suite()

    def test_one_shot_cli_synthetic_success(self):
        self.assertEqual(main([]), 0)
