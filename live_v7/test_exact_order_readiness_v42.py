"""V42 exact-order contract tests. No broker account calls or orders."""
import unittest
from datetime import datetime,timezone,timedelta
from pathlib import Path
from live_v7.exact_order_readiness_v42 import evaluate_exact_order

NOW=datetime(2026,11,26,8,0,tzinfo=timezone.utc)
ORDER={"exchange":"NFO","side":"SELL","type":"LIMIT","duration":"DAY",
       "variety":"NORMAL","symbol":"NIFTY29DEC2629000CE","token":"38158",
       "quantity":65,"producttype":"CARRYFORWARD","price":"10.50"}
EVIDENCE={"master_tick":"0.05","net_long_quantity":65,
          "symbol":ORDER["symbol"],"token":ORDER["token"],
          "producttype":ORDER["producttype"],
          "active_or_unknown_sell_count":0,
          "books_complete":True,"books_at":NOW,
          "quote_complete":True,"quote_at":NOW,
          "broker_technical_and_compliance_final_approval":True,
          "account_trading_entitlement_verified":True,
          "durable_pre_send_intent_committed":True,
          "unknown_outcome_recovery_certified":True,
          "owner_exact_order_consent":True,
          "fee_and_risk_limit_verified":True,
          "lpp_and_exchange_constraints_checked":True}

def check(order=None,evidence=None,now=NOW):
    return evaluate_exact_order(order=ORDER if order is None else order,
                                evidence=EVIDENCE if evidence is None else evidence,now=now)

class V42ExactOrderReadinessTests(unittest.TestCase):
    def assertBlocked(self,reason,order=None,evidence=None,now=NOW):
        r=check(order,evidence,now)
        self.assertIn(reason,r["blockedReasons"])
        self.assertFalse(r["canSubmitOrder"])
        self.assertFalse(r["canRetryUnknownOrder"])
    def test_even_all_mock_flags_cannot_trade(self):
        r=check()
        self.assertFalse(r["liveOrdersEnabled"])
        self.assertIn("LIVE_ORDER_TRANSPORT_SOURCE_LOCKED",r["blockedReasons"])
    def test_missing_exact_consent(self):
        self.assertBlocked("EXACT_ORDER_CONSENT_MISSING",evidence=dict(EVIDENCE,owner_exact_order_consent=False))
    def test_journal_missing(self):
        self.assertBlocked("DURABLE_PRE_SEND_INTENT_MISSING",evidence=dict(EVIDENCE,durable_pre_send_intent_committed=False))
    def test_unknown_recovery_missing(self):
        self.assertBlocked("UNKNOWN_BROKER_ACK_RECOVERY_MISSING",evidence=dict(EVIDENCE,unknown_outcome_recovery_certified=False))
    def test_quote_stale(self):
        self.assertBlocked("FRESH_BID_ASK_REQUIRED",evidence=dict(EVIDENCE,quote_at=NOW-timedelta(seconds=11)))
    def test_orderbook_stale(self):
        self.assertBlocked("FRESH_ORDER_POSITION_TRADEBOOK_REQUIRED",evidence=dict(EVIDENCE,books_at=NOW-timedelta(seconds=11)))
    def test_active_sell(self):
        self.assertBlocked("ACTIVE_OR_UNKNOWN_SELL_ORDER",evidence=dict(EVIDENCE,active_or_unknown_sell_count=1))
    def test_quantity_exceeds_long(self):
        self.assertBlocked("FRESH_POSITION_QUANTITY_INSUFFICIENT",order=dict(ORDER,quantity=130))
    def test_producttype_mismatch(self):
        self.assertBlocked("POSITION_IDENTITY_OR_PRODUCTTYPE_MISMATCH",order=dict(ORDER,producttype="INTRADAY"))
    def test_tick_wrong(self):
        self.assertBlocked("PRICE_OR_TICK_NOT_VERIFIED",order=dict(ORDER,price="10.53"))
    def test_market_rejected(self):
        self.assertBlocked("UNSUPPORTED_EXIT_TYPE",order=dict(ORDER,type="MARKET"))
    def test_normal_stop_trigger_rejected(self):
        self.assertBlocked("NORMAL_LIMIT_HAS_TRIGGER",order=dict(ORDER,trigger="10.55"))
    def test_stop_loss_sell_valid_shape_still_locked(self):
        r=check(order=dict(ORDER,type="STOPLOSS_LIMIT",variety="STOPLOSS",trigger="10.55"))
        self.assertFalse(r["canSubmitOrder"])
    def test_stop_loss_invalid_trigger(self):
        self.assertBlocked("SELL_STOP_LIMIT_TRIGGER_INVALID",order=dict(ORDER,type="STOPLOSS_LIMIT",variety="STOPLOSS",trigger="10.45"))
    def test_approval_missing(self):
        self.assertBlocked("FINAL_BROKER_AUTHORIZATION_UNVERIFIED",evidence=dict(EVIDENCE,broker_technical_and_compliance_final_approval=False))
    def test_fee_risk_missing(self):
        self.assertBlocked("FEES_AND_RISK_NOT_VERIFIED",evidence=dict(EVIDENCE,fee_and_risk_limit_verified=False))
    def test_no_order_transport_code(self):
        s=Path(__file__).with_name("exact_order_readiness_v42.py").read_text()
        for forbidden in ("placeOrder","cancelOrder","modifyOrder","angel_gateway","psycopg"):
            self.assertNotIn(forbidden,s)

if __name__=="__main__": unittest.main()
