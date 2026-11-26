"""V36 mocked cross-book checks. No network or broker execution."""
import unittest
from datetime import datetime,timezone,timedelta
from pathlib import Path
from live_v7.shadow_recovery_v36 import shadow_reconcile,RecoveryBlocked

NOW=datetime(2026,11,26,7,0,tzinfo=timezone.utc)
P=[{"symbol":"NIFTY29DEC2629000CE","instrumentToken":"38158","net_quantity":65}]
O=[{"order_id":"manual-order-1","symbol":"NIFTY29DEC2629000CE",
    "side":"BUY","quantity":65,"filled_quantity":65,
    "status":"COMPLETE","statusKnown":True}]
T=[{"fill_id":"trade-1","order_id":"manual-order-1","quantity":65}]

def check(**kw):
    return shadow_reconcile(shadow_status=kw.get("status","DRAFT"),
        positions=kw.get("positions",P),orders=kw.get("orders",O),
        trades=kw.get("trades",T),
        broker_owner_verified=kw.get("owner",True),
        books_complete=kw.get("complete",True),
        received_at=kw.get("at",NOW),now=NOW)

class V36ShadowRecoveryTests(unittest.TestCase):
    def blocked(self,reason,**kw):
        r=check(**kw)
        self.assertIn(reason,r["blockers"])
        self.assertFalse(r["canSubmitOrder"])
        self.assertFalse(r["canRetryOrder"])
    def test_good_mock_is_still_locked(self):
        r=check()
        self.assertFalse(r["realOrdersEnabled"])
        self.assertFalse(r["manualPositionAdopted"])
        self.assertIn("SOURCE_LOCKED_NO_BROKER_ORDERS",r["blockers"])
    def test_unknown_outcome_no_retry(self):
        self.blocked("AMBIGUOUS_SIMULATED_OUTCOME_NO_RETRY",status="SIMULATED_SEND_UNKNOWN")
    def test_fake_ack_not_broker_approval(self):
        self.blocked("SIMULATED_ACK_NOT_BROKER_ACK",status="SIMULATED_ACK")
    def test_review_state_blocks(self):
        self.blocked("MANUAL_REVIEW_REQUIRED",status="REVIEW_REQUIRED")
    def test_invalid_state(self):
        self.blocked("UNKNOWN_SHADOW_STATE",status="ORDER_ACCEPTED")
    def test_owner_not_verified(self):
        self.blocked("OWNER_OR_BROKER_NOT_VERIFIED",owner=False)
    def test_stale_snapshot(self):
        self.blocked("INCOMPLETE_OR_STALE_BOOKS",at=NOW-timedelta(seconds=11))
    def test_incomplete_books(self):
        self.blocked("INCOMPLETE_OR_STALE_BOOKS",complete=False)
    def test_wrong_quantity(self):
        self.blocked("POSITION_CHANGED_OR_NOT_UNIQUE",positions=[dict(P[0],net_quantity=64)])
    def test_duplicate_positions(self):
        self.blocked("POSITION_CHANGED_OR_NOT_UNIQUE",positions=P+P)
    def test_token_conflict(self):
        self.blocked("POSITION_TOKEN_CONFLICT",positions=P+[dict(P[0],instrumentToken="other",net_quantity=0)])
    def test_active_sell(self):
        self.blocked("ACTIVE_OR_UNCERTAIN_SELL_CONFLICT",orders=O+[dict(O[0],order_id="s1",side="SELL",status="OPEN",filled_quantity=0)])
    def test_unknown_sell(self):
        self.blocked("ACTIVE_OR_UNCERTAIN_SELL_CONFLICT",orders=O+[dict(O[0],order_id="s2",side="SELL",status="UNKNOWN",statusKnown=False)])
    def test_duplicate_order_id(self):
        self.blocked("BROKER_ORDER_IDS_INVALID_OR_DUPLICATE",orders=O+O)
    def test_invalid_filled_quantity(self):
        self.blocked("INVALID_ORDER_QUANTITY_OR_FILL",orders=[dict(O[0],filled_quantity=70)])
    def test_trade_not_in_orderbook(self):
        self.blocked("TRADEBOOK_ORDER_NOT_IN_ORDERBOOK",trades=[dict(T[0],order_id="unseen")])
    def test_duplicate_fill(self):
        self.blocked("INVALID_OR_DUPLICATE_TRADE_ID",trades=T+T)
    def test_missing_trade_quantity(self):
        self.blocked("INVALID_TRADE_FILL_QUANTITY",trades=[dict(T[0],quantity=0)])
    def test_invalid_row_type_rejected(self):
        with self.assertRaisesRegex(RecoveryBlocked,"ORDERS_INVALID"):
            check(orders=[None])
    def test_source_has_no_order_routes(self):
        src=Path(__file__).with_name("shadow_recovery_v36.py").read_text()
        for bad in ("placeOrder","cancelOrder","modifyOrder","angel_gateway",
                    "angel_execution_transport","urllib.request","psycopg"):
            self.assertNotIn(bad,src)

if __name__=="__main__":
    unittest.main()
