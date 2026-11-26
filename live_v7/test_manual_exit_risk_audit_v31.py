"""V31 pure audit regression: no calls to broker order routes."""
import unittest
from datetime import datetime, timezone, timedelta
from pathlib import Path
from live_v7.manual_exit_risk_audit_v31 import audit_manual_limit_exit

NOW = datetime(2026, 11, 26, 6, 0, tzinfo=timezone.utc)


def evidence(**changes):
    obj = dict(
        owner_verified=True, contract="NIFTY29DEC2629000CE", token="38158",
        net_quantity=65, active_sell_quantity=0, orderbook_states_reconciled=True,
        ltp="10.80", best_bid="10.75", best_ask="10.85",
        broker_feed_timestamp_utc=NOW,
        feed_timestamp_independently_verified=True,
        official_tick_size="0.05", official_tick_verified=True,
        lpp_lower="10.00", lpp_upper="11.50", lpp_verified=True,
        nfo_sell_limit_entitlement_verified=True, order_fields_verified=True,
        product_type_verified=True, market_session_verified=True,
        durable_order_journal_certified=True,
        restart_and_unknown_ack_recovery_certified=True,
        final_order_specific_user_authorization=True,
        total_exit_and_entry_fees="50", fees_broker_verified=True,
        actual_average_entry_broker_verified=True,
    )
    obj.update(changes)
    return obj


class V31ReadOnlyAuditTests(unittest.TestCase):
    def check_blocked(self, reason, **changes):
        report = audit_manual_limit_exit(evidence(**changes), now=NOW)
        self.assertIn(reason, report["evidenceBlockers"])
        self.assertFalse(report["canSubmitOrder"])

    def test_complete_mock_evidence_is_still_source_locked(self):
        r = audit_manual_limit_exit(evidence(), now=NOW)
        self.assertTrue(r["allEvidenceChecksPassed"])
        self.assertFalse(r["canSubmitOrder"])
        self.assertFalse(r["realOrdersEnabled"])
        self.assertEqual(r["estimatedLossIncludingProvidedFees"], "207.30")
        self.assertFalse(r["stopLossOrder"])

    def test_missing_evidence_fails_closed(self):
        r = audit_manual_limit_exit({}, now=NOW)
        self.assertTrue(r["evidenceBlockers"])
        self.assertFalse(r["canSubmitOrder"])

    def test_owner_must_be_verified(self):
        self.check_blocked("OWNER_NOT_VERIFIED", owner_verified=False)

    def test_quantity_must_match(self):
        self.check_blocked("POSITION_NOT_EXACT", net_quantity=64)

    def test_active_sell_blocks(self):
        self.check_blocked("ACTIVE_SELL_CONFLICT_OR_UNKNOWN", active_sell_quantity=65)

    def test_orderbook_unknown_blocks(self):
        self.check_blocked("ORDERBOOK_UNRECONCILED", orderbook_states_reconciled=False)

    def test_stale_exchange_feed_blocks(self):
        self.check_blocked("EXCHANGE_FEED_STALE_OR_FUTURE",
                           broker_feed_timestamp_utc=NOW-timedelta(seconds=30))

    def test_ltp_receipt_alone_does_not_verify_feed(self):
        self.check_blocked("FEED_SOURCE_NOT_VERIFIED",
                           feed_timestamp_independently_verified=False)

    def test_missing_bid_ask_blocks(self):
        self.check_blocked("LIVE_BID_ASK_UNVERIFIED_OR_INVALID", best_bid=None)

    def test_bid_below_limit_blocks_immediate_fill_claim(self):
        self.check_blocked("BID_BELOW_SELL_LIMIT_NO_IMMEDIATE_FILL_ASSUMPTION",
                           best_bid="10.45")

    def test_tick_not_guessed_from_previous_session(self):
        self.check_blocked("OFFICIAL_TICK_NOT_VERIFIED", official_tick_verified=False)

    def test_lpp_unknown_blocks(self):
        self.check_blocked("BROKER_EXCHANGE_LPP_UNVERIFIED", lpp_verified=False)

    def test_lpp_outside_blocks(self):
        self.check_blocked("SELL_LIMIT_OUTSIDE_LPP",
                           lpp_lower="10.60")

    def test_broker_entitlement_not_implied_by_read_access(self):
        self.check_blocked("SELL_LIMIT_ENTITLEMENT_UNVERIFIED",
                           nfo_sell_limit_entitlement_verified=False)

    def test_missing_fees_blocks(self):
        self.check_blocked("ACTUAL_CHARGES_UNVERIFIED",
                           fees_broker_verified=False)

    def test_budget_exceeded_blocks(self):
        self.check_blocked("OWNER_DECLARED_BUDGET_EXCEEDED",
                           total_exit_and_entry_fees="700")

    def test_final_authorization_missing_blocks(self):
        self.check_blocked("FINAL_ORDER_AUTHORIZATION_MISSING",
                           final_order_specific_user_authorization=False)

    def test_source_has_no_order_transport(self):
        s = Path(__file__).with_name("manual_exit_risk_audit_v31.py").read_text()
        for forbidden in ("placeOrder", "modifyOrder", "cancelOrder",
                          "angel_execution_transport", "urllib.request"):
            self.assertNotIn(forbidden, s)


if __name__ == "__main__":
    unittest.main()
