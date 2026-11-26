"""No live orders. Unit test V28 manual SL preflight with mock market data."""
import unittest
from decimal import Decimal
from live_v7.manual_sl_combined_preflight_v28 import (
    evaluate,verify_master,PreflightBlocked,SYMBOL,TOKEN)
P=[{"symbol":SYMBOL,"instrumentToken":TOKEN,"net_quantity":65}]
M=[{"symbol":SYMBOL,"token":TOKEN,"exch_seg":"NFO",
    "instrumenttype":"OPTIDX","expiry":"29DEC2026","lotsize":"65","tick_size":"5"}]
class V28CombinedManualSLPreflightTests(unittest.TestCase):
 def calc(self,**kw):
  return evaluate(position=kw.get("position",P),
      orders=kw.get("orders",[]),master=kw.get("master",M),
      ltp=kw.get("ltp","11.30"))
 def test_baseline(self):
  r=self.calc()
  self.assertEqual(r["premium_loss"],Decimal("193.05"))
  self.assertEqual(r["headroom_before_charges"],Decimal("606.95"))
  self.assertFalse(r["canSubmitOrder"])
 def test_master_tick(self):
  self.assertEqual(verify_master(M)["tick"],Decimal("0.05"))
 def test_unrecognized_contract(self):
  with self.assertRaises(PreflightBlocked):
   self.calc(master=[dict(M[0],token="999")])
 def test_wrong_lot(self):
  with self.assertRaisesRegex(PreflightBlocked,"LOT_OR_TICK_CHANGED"):
   self.calc(master=[dict(M[0],lotsize="75")])
 def test_wrong_tick(self):
  with self.assertRaisesRegex(PreflightBlocked,"LOT_OR_TICK_CHANGED"):
   self.calc(master=[dict(M[0],tick_size="10")])
 def test_wrong_expiry(self):
  with self.assertRaises(PreflightBlocked):
   self.calc(master=[dict(M[0],expiry="30DEC2026")])
 def test_changed_position(self):
  with self.assertRaises(PreflightBlocked):
   self.calc(position=[dict(P[0],net_quantity=130)])
 def test_short_position(self):
  with self.assertRaises(PreflightBlocked):
   self.calc(position=[dict(P[0],net_quantity=-65)])
 def test_conflicting_sell(self):
  o=[{"symbol":SYMBOL,"side":"SELL","status":"OPEN","quantity":65,"filled_quantity":0}]
  with self.assertRaises(PreflightBlocked):
   self.calc(orders=o)
 def test_price_at_trigger(self):
  with self.assertRaisesRegex(PreflightBlocked,"LTP_AT_OR_BELOW"):
   self.calc(ltp="10.00")
 def test_price_below_trigger(self):
  with self.assertRaises(PreflightBlocked):
   self.calc(ltp="9.80")
 def test_bad_ltp(self):
  with self.assertRaises(PreflightBlocked):
   self.calc(ltp="NaN")
 def test_does_not_certify_broker_or_fill(self):
  r=self.calc()
  self.assertFalse(r["verifiedBrokerOrderPermission"])
  self.assertFalse(r["verifiedLppAndLiveBidAsk"])
  self.assertFalse(r["estimatedFeesVerified"])
 def test_no_execution_calls(self):
  from pathlib import Path
  s=Path(__file__).with_name("manual_sl_combined_preflight_v28.py").read_text()
  for token in ("placeOrder","cancelOrder","modifyOrder","angel_execution_transport","psycopg"):
   self.assertNotIn(token,s)
if __name__=="__main__":unittest.main()
