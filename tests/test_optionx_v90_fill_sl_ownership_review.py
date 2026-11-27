"""V90 no-broker, no-secrets, no-DB tests."""
import unittest
from scripts.optionx_v90_fill_sl_ownership_review import adjudicate

def review(**overrides):
    args=dict(orders=[],fills=[],positions=[],owned_intents=[],protection_records=[],
              authenticated_broker=True,verified_trade_ids=False,
              verified_stop_types=False,verified_order_ack=False)
    args.update(overrides)
    return adjudicate(**args)

class Tests(unittest.TestCase):
    def test_manual_exposure_stays_unowned(self):
        r=review(positions=[{"symbol":"NIFTYTEST","net_quantity":65}])
        self.assertEqual(r["positions_with_exposure"],1)
        self.assertFalse(r["owner_partition_verified"])
        self.assertIn("MANUAL_POSITION_NOT_ADOPTED",r["issues"])
    def test_exact_user_snapshot_is_not_falsely_certified(self):
        r=review(positions=[{"symbol":"NIFTYTEST","net_quantity":65}])
        self.assertFalse(r["fill_reconciled"])
        self.assertFalse(r["sl_confirmed"])
        self.assertFalse(r["can_trade"])
    def test_one_zero_position_not_exposure(self):
        self.assertEqual(review(positions=[{"symbol":"TEST","net_quantity":0}])["positions_with_exposure"],0)
    def test_empty_books_not_live_proof(self):
        r=review();self.assertFalse(r["owner_partition_verified"])
    def test_broker_order_not_claimed(self):
        r=review(orders=[{"order_id":"ABC1","symbol":"TEST","side":"BUY","status":"OPEN"}])
        self.assertIn("BROKER_ORDERS_NOT_OWNED_BY_OPTIONX",r["issues"])
    def test_owned_order_missing_from_book(self):
        r=review(owned_intents=[{"broker_order_id":"ABC1","symbol":"TEST","side":"BUY"}])
        self.assertIn("OPTIONX_OWNED_ORDER_NOT_IN_BROKER_BOOK",r["issues"])
    def test_broker_unverified(self):
        self.assertIn("BROKER_SOURCE_NOT_AUTHENTICATED",review(authenticated_broker=False)["issues"])
    def test_unverified_trade_ids(self):
        self.assertIn("TRADE_IDS_NOT_BROKER_VERIFIED",review()["issues"])
    def test_duplicate_fills(self):
        f={"trade_id":"T1","order_id":"A1","quantity":1,"side":"BUY","symbol":"TEST"}
        self.assertIn("BROKER_TRADE_RECORD_INVALID",review(fills=[f,f])["issues"])
    def test_fill_without_broker_order(self):
        f={"trade_id":"T1","order_id":"A1","quantity":1,"side":"BUY","symbol":"TEST"}
        self.assertIn("FILL_ORDER_NOT_IN_BROKER_BOOK",review(fills=[f])["issues"])
    def test_stop_without_broker_ack(self):
        r=review(owned_intents=[{"broker_order_id":"A1","symbol":"TEST","side":"BUY"}],
            protection_records=[{"entry_order_id":"A1","stop_order_id":"S1","symbol":"TEST","side":"SELL","state":"STOP_ACKED","protected_quantity":1,"open_quantity":1}])
        self.assertIn("STOP_NOT_BOUND_TO_VERIFIED_ENTRY_AND_BROKER_ORDER",r["issues"])
    def test_stop_coverage_mismatch(self):
        r=review(
            orders=[{"order_id":"A1","symbol":"TEST","side":"BUY","filled_quantity":1,"status":"COMPLETE"},
                    {"order_id":"S1","symbol":"TEST","side":"SELL","quantity":2,"status":"OPEN","is_broker_verified_stop_limit":True}],
            owned_intents=[{"broker_order_id":"A1","symbol":"TEST","side":"BUY"}],
            protection_records=[{"entry_order_id":"A1","stop_order_id":"S1","symbol":"TEST","side":"SELL","state":"STOP_ACKED","protected_quantity":1,"open_quantity":1}])
        self.assertIn("STOP_ACK_OR_COVERAGE_MISMATCH",r["issues"])
    def test_not_permit_any_live_actions(self):
        r=review();self.assertFalse(r["can_trade"]);self.assertFalse(r["can_cancel"]);self.assertFalse(r["manual_positions_touched"])
    def test_invalid_input_fails_closed(self):
        r=review(orders="invalid");self.assertEqual(r["status"],"BLOCKED_INVALID_ORDERS")
    def test_bad_negative_qty(self):
        r=review(positions=[{"symbol":"TEST","net_quantity":True}])
        self.assertIn("BROKER_POSITION_INVALID",r["issues"])
    def test_unlinked_trade_count_cannot_substitute_trade_ids(self):
        r=review(fills=[])
        self.assertFalse(r["fill_reconciled"])

if __name__=="__main__":unittest.main()
