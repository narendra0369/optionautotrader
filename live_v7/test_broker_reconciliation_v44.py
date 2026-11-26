"""V44 strict broker-book reconciliation fixtures; no HTTP or live orders."""
import unittest
from datetime import datetime,timezone,timedelta
from live_v7.broker_reconciliation_v44 import reconcile

NOW=datetime(2026,11,26,9,0,tzinfo=timezone.utc)
INTENT={"broker_order_id":"BRK-1234","tradingsymbol":"NIFTY29DEC2629000CE",
 "symboltoken":"38158","transactiontype":"SELL","quantity":65,
 "producttype":"CARRYFORWARD"}
ORDER={"orderid":"BRK-1234","tradingsymbol":INTENT["tradingsymbol"],
 "symboltoken":"38158","transactiontype":"SELL","quantity":"65",
 "producttype":"CARRYFORWARD","status":"complete","filledshares":"65"}
TRADE={"orderid":"BRK-1234","tradeid":"TRADE-1",
 "tradingsymbol":INTENT["tradingsymbol"],"symboltoken":"38158",
 "transactiontype":"SELL","producttype":"CARRYFORWARD",
 "fillshares":"65","fillprice":"10.50"}
def evaluate(orders=None,trades=None,intent=None,as_of=NOW,verified=True):
 return reconcile(intent=INTENT if intent is None else intent,
   orderbook=[ORDER] if orders is None else orders,
   tradebook=[TRADE] if trades is None else trades,
   as_of=as_of,now=NOW,owner_authenticated=verified,
   book_sources_verified=verified)
class BrokerReconciliationTests(unittest.TestCase):
 def test_complete_with_consistent_trade(self):
    r=evaluate()
    self.assertEqual(r["state"],"COMPLETE_BROKER_BOOKS_CONSISTENT")
    self.assertEqual(r["filledQuantityObserved"],65)
    self.assertFalse(r["canSubmitOrder"])
 def test_partial_fill_active(self):
    r=evaluate(orders=[dict(ORDER,status="partially filled",filledshares="30")],
      trades=[dict(TRADE,fillshares="30")])
    self.assertIn("ORDER_STILL_ACTIVE_OR_UNCERTAIN",r["blockers"])
 def test_fill_without_trade(self):
    self.assertIn("BROKER_FILLED_BUT_NO_TRADES",evaluate(trades=[])["blockers"])
 def test_duplicate_trade_id(self):
    self.assertIn("TRADE_ID_MISSING_OR_DUPLICATED",
      evaluate(trades=[dict(TRADE,fillshares="30"),dict(TRADE,fillshares="35")])["blockers"])
 def test_trade_total_mismatch(self):
    self.assertIn("ORDER_TRADE_FILL_TOTAL_MISMATCH",
      evaluate(trades=[dict(TRADE,fillshares="64")])["blockers"])
 def test_unknown_status(self):
    self.assertIn("BROKER_ORDER_STATUS_UNKNOWN",
      evaluate(orders=[dict(ORDER,status="unrecognized")])["blockers"])
 def test_wrong_token(self):
    self.assertIn("BROKER_ORDER_IDENTITY_MISMATCH",
      evaluate(orders=[dict(ORDER,symboltoken="999")])["blockers"])
 def test_wrong_producttype(self):
    self.assertIn("BROKER_ORDER_IDENTITY_MISMATCH",
      evaluate(orders=[dict(ORDER,producttype="INTRADAY")])["blockers"])
 def test_ambiguous_order_id(self):
    self.assertIn("BROKER_ORDER_ID_NOT_UNIQUELY_FOUND",
      evaluate(orders=[ORDER,ORDER])["blockers"])
 def test_missing_order_id(self):
    self.assertIn("BROKER_ORDER_ID_NOT_UNIQUELY_FOUND",
      evaluate(orders=[])["blockers"])
 def test_stale_book(self):
    self.assertIn("BROKER_BOOKS_STALE_OR_TIME_INVALID",
      evaluate(as_of=NOW-timedelta(seconds=11))["blockers"])
 def test_untrusted_books(self):
    self.assertIn("BROKER_BOOK_PROVENANCE_UNVERIFIED",evaluate(verified=False)["blockers"])
 def test_terminal_cancel_no_fill(self):
    r=evaluate(orders=[dict(ORDER,status="cancelled",filledshares="0")],trades=[])
    self.assertEqual(r["state"],"TERMINAL_NO_FILL_CONFIRMED_IN_BOOKS")
    self.assertFalse(r["canRetryUnknownOrder"])
 def test_cancel_partial_fill(self):
    r=evaluate(orders=[dict(ORDER,status="cancelled",filledshares="20")],
       trades=[dict(TRADE,fillshares="20")])
    self.assertIn("PARTIAL_FILL_AFTER_CANCEL_ACCOUNT_RECHECK",r["blockers"])
 def test_rejected_no_fill(self):
    r=evaluate(orders=[dict(ORDER,status="rejected",filledshares="0")],trades=[])
    self.assertEqual(r["state"],"TERMINAL_NO_FILL_CONFIRMED_IN_BOOKS")
 def test_rejected_with_fill(self):
    self.assertIn("REJECTED_STATUS_HAS_FILLS_VERIFY",
      evaluate(orders=[dict(ORDER,status="rejected",filledshares="65")])["blockers"])
 def test_fill_price_invalid(self):
    self.assertIn("TRADE_QUANTITY_OR_PRICE_INVALID",
      evaluate(trades=[dict(TRADE,fillprice="NaN")])["blockers"])
 def test_no_reconcile_can_dispatch(self):
    for result in (evaluate(),evaluate(orders=[]),evaluate(trades=[])):
       self.assertFalse(result["canSubmitOrder"])
       self.assertFalse(result["canRetryUnknownOrder"])
       self.assertFalse(result["canCancelOrder"])
       self.assertFalse(result["liveOrdersEnabled"])
if __name__=="__main__": unittest.main()
