"""Offline tests: Angel private orderbook and positions read-only count audit."""
from __future__ import annotations

from unittest import TestCase
from unittest.mock import patch

from ops.angel_private_account_readonly_audit import (
    AccountAuditError, audit_snapshot, main,
)


def envelope(resource, rows):
    return {
        "broker": "Angel", "resource": resource,
        "trustedAccount": "OWNER_PROFILE_MATCHED",
        "recordCount": len(rows), "records": rows,
        "canSubmitOrder": False,
        "orderExecutionEnabled": False,
    }


class AngelPrivateAccountAuditTests(TestCase):
    def test_empty_orderbook_and_positions_not_live_authorized(self):
        result = audit_snapshot(envelope("positions", []),
                                envelope("orderbook", []))
        self.assertEqual(result["nfoOrderRowsCount"], 0)
        self.assertEqual(result["nonzeroNfoPositionRows"], 0)
        self.assertFalse(result["accountHasUnresolvedOrdersOrPositions"])
        self.assertFalse(result["canSubmitOrder"])
        self.assertFalse(result["brokerFillReconciliationCompleted"])

    def test_open_order_and_position_require_manual_review(self):
        positions = [{"symbol": "NIFTY01DEC2626000CE", "net_quantity": 65,
                      "instrumentToken": "47895", "exchange": "NFO"}]
        orders = [{"order_id": "abc123456", "status": "PARTIALLY_FILLED",
                   "quantity": 65, "filled_quantity": 20, "statusKnown": True}]
        result = audit_snapshot(envelope("positions", positions),
                                envelope("orderbook", orders))
        self.assertTrue(result["accountHasUnresolvedOrdersOrPositions"])
        self.assertEqual(result["pendingOrOpenNfoOrderRows"], 1)
        self.assertFalse(result["liveOrdersEnabled"])
        self.assertEqual(result["nextAction"], "MANUAL_REVIEW_BROKER_ORDERBOOK_AND_POSITIONS_REQUIRED")

    def test_historical_final_broker_order_is_not_open(self):
        orders = [{"order_id": "order0001", "status": "COMPLETE",
                   "statusKnown": True}]
        result = audit_snapshot(envelope("positions", []), envelope("orderbook", orders))
        self.assertFalse(result["accountHasUnresolvedOrdersOrPositions"])
        self.assertEqual(result["historicalFinalOrderRows"], 1)

    def test_unknown_order_status_rejected(self):
        orders = [{"order_id": "abc123", "status": "UNKNOWN", "statusKnown": False}]
        with self.assertRaisesRegex(AccountAuditError, "UNKNOWN_BROKER_ORDER_STATE"):
            audit_snapshot(envelope("positions", []), envelope("orderbook", orders))

    def test_unverified_owner_contract_rejected(self):
        wrong = envelope("positions", [])
        wrong["trustedAccount"] = "NOT_OWNER"
        with self.assertRaisesRegex(AccountAuditError, "BROKER_READONLY_CONTRACT_MISMATCH"):
            audit_snapshot(wrong, envelope("orderbook", []))

    def test_malformed_position_and_count_rejected(self):
        pos = envelope("positions", [{"net_quantity": "65"}])
        with self.assertRaisesRegex(AccountAuditError, "POSITION_QUANTITY_UNVERIFIED"):
            audit_snapshot(pos, envelope("orderbook", []))
        pos2 = envelope("positions", [])
        pos2["recordCount"] = 1
        with self.assertRaisesRegex(AccountAuditError, "BROKER_SNAPSHOT_COUNT_MISMATCH"):
            audit_snapshot(pos2, envelope("orderbook", []))

    @patch("ops.angel_private_account_readonly_audit.run_owner_readonly")
    def test_cli_reports_failure_without_real_network(self, runner):
        runner.side_effect = AccountAuditError("BROKER_SNAPSHOT_MISSING")
        self.assertEqual(main(["--expected-ip", "43.204.246.235"]), 1)

    @patch("ops.angel_private_account_readonly_audit.run_owner_readonly")
    def test_cli_success_cannot_authorize_order(self, runner):
        runner.return_value = {"canSubmitOrder": False}
        self.assertEqual(main(["--expected-ip", "43.204.246.235"]), 0)
        runner.assert_called_once()
