"""V26 mock-only; no API order calls."""
import unittest
from live_v7.manual_sl_preflight_v26 import assess_manual_positions,ManualPreflightError
P={"symbol":"NIFTY29DEC2629000CE","instrumentToken":"12345","net_quantity":65}
class V26ManualSlPreflightTests(unittest.TestCase):
 def test_long_visible(self):
  r=assess_manual_positions([P],[])
  self.assertEqual(r[0]["netLongQuantity"],65)
  self.assertFalse(r[0]["canSubmitOrder"])
 def test_short_excluded(self):
  self.assertEqual(assess_manual_positions([dict(P,net_quantity=-65)],[]),[])
 def test_zero_excluded(self):
  self.assertEqual(assess_manual_positions([dict(P,net_quantity=0)],[]),[])
 def test_pending_sell_conflict(self):
  s={"symbol":P["symbol"],"side":"SELL","status":"PENDING",
     "quantity":65,"filled_quantity":0}
  r=assess_manual_positions([P],[s])
  self.assertTrue(r[0]["conflictingOrdersRequireHumanReview"])
  self.assertEqual(r[0]["activeSellQuantity"],65)
 def test_cancelled_sell_not_active(self):
  s={"symbol":P["symbol"],"side":"SELL","status":"CANCELLED",
     "quantity":65,"filled_quantity":0}
  self.assertEqual(assess_manual_positions([P],[s])[0]["activeSellOrders"],0)
 def test_partial_sell_remaining(self):
  s={"symbol":P["symbol"],"side":"SELL","status":"PARTIALLY_FILLED",
     "quantity":65,"filled_quantity":25}
  self.assertEqual(assess_manual_positions([P],[s])[0]["activeSellQuantity"],40)
 def test_different_symbol_not_conflict(self):
  s={"symbol":"BANKNIFTY01DEC26CE","side":"SELL","status":"OPEN",
     "quantity":65,"filled_quantity":0}
  self.assertEqual(assess_manual_positions([P],[s])[0]["activeSellOrders"],0)
 def test_no_live_order_transport(self):
  from pathlib import Path
  s=Path(__file__).with_name("manual_sl_preflight_v26.py").read_text()
  self.assertNotIn("angel_execution_transport",s)
  self.assertNotIn("placeOrder",s)
  self.assertNotIn("cancelOrder",s)
  self.assertNotIn("modifyOrder",s)
 def test_invalid_position_fail_closed(self):
  with self.assertRaises(ManualPreflightError):
   assess_manual_positions([dict(P,net_quantity="65")],[])
if __name__=="__main__": unittest.main()
