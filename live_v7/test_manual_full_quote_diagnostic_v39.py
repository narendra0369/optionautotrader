"""V39 offline privacy and block-stage regression checks."""
import unittest
from pathlib import Path
from unittest.mock import patch
from live_v7.manual_full_quote_diagnostic_v39 import stage_failure, assess_position

VALID={"contract":"NIFTY29DEC2629000CE",
       "instrumentToken":"38158","netLongQuantity":65,"activeSellOrders":0}

class V39DiagnosticTests(unittest.TestCase):
 def test_known_stage(self):
  x=stage_failure("AUTHENTICATION")
  self.assertEqual(x["stage"],"AUTHENTICATION")
  self.assertFalse(x["canSubmitOrder"])
 def test_unknown_stage_redacted(self):
  self.assertEqual(stage_failure("secret-example")["stage"],"UNKNOWN")
 def test_all_stages_never_trade(self):
  for stage in ("CONFIG","AUTHENTICATION","POSITIONS_READ","ORDERS_READ",
                "POSITION_CHECK","FULL_QUOTE","FEED_FRESHNESS"):
   row=stage_failure(stage)
   self.assertFalse(row["canSubmitOrder"])
   self.assertFalse(row["realOrdersEnabled"])
 def check(self,ret,orders=None):
  with patch("live_v7.manual_full_quote_diagnostic_v39.assess_manual_positions",return_value=ret):
   return assess_position([],[] if orders is None else orders)
 def test_position_match_pass(self):
  self.assertEqual(self.check([VALID]),"PASS")
 def test_position_absent_blocked(self):
  self.assertEqual(self.check([]),"POSITION_COUNT_CHANGED")
 def test_multiple_positions_blocked(self):
  self.assertEqual(self.check([VALID,VALID]),"POSITION_COUNT_CHANGED")
 def test_contract_changed_blocked(self):
  self.assertEqual(self.check([dict(VALID,contract="DIFFERENT")]),"POSITION_CONTRACT_CHANGED")
 def test_token_changed_blocked(self):
  self.assertEqual(self.check([dict(VALID,instrumentToken="777")]),"POSITION_CONTRACT_CHANGED")
 def test_quantity_changed_blocked(self):
  self.assertEqual(self.check([dict(VALID,netLongQuantity=0)]),"POSITION_QUANTITY_CHANGED")
 def test_conflicting_sell_blocked(self):
  self.assertEqual(self.check([dict(VALID,activeSellOrders=1)]),"SELL_ORDER_CONFLICT")
 def test_unknown_order_blocked(self):
  self.assertEqual(self.check([VALID],orders=[{"symbol":VALID["contract"],"statusKnown":False}]),"ORDER_STATUS_UNKNOWN")
 def test_no_token_or_secret_prints(self):
  s=Path(__file__).with_name("manual_full_quote_diagnostic_v39.py").read_text()
  for unsafe in ("print(client)", "print(owner)", "print(positions)", "print(orders)",
                 "print(quote)", "print(exc)", "traceback.print_exc"):
   self.assertNotIn(unsafe,s)
 def test_no_broker_order_transport(self):
  s=Path(__file__).with_name("manual_full_quote_diagnostic_v39.py").read_text()
  for unsafe in ("placeOrder","cancelOrder","modifyOrder","angel_execution_transport"):
   self.assertNotIn(unsafe,s)

if __name__=="__main__":
 unittest.main()
