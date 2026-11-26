"""Offline V29 order-readiness tests; never submit a broker order."""
import unittest
from decimal import Decimal
from pathlib import Path
from live_v7.manual_sl_order_readiness_v29 import (
 draft_packet, assess_risk, format_preflight_report, ReadinessBlocked
)

class V29ManualSlOrderReadinessTests(unittest.TestCase):
 def test_no_producttype_assumption(self):
  with self.assertRaisesRegex(ReadinessBlocked,"PRODUCT_TYPE"):
   draft_packet()
 def test_explicit_carryforward_fields(self):
  x=draft_packet(product_type="CARRYFORWARD")
  self.assertEqual((x["transactiontype"],x["ordertype"],x["duration"]),("SELL","STOPLOSS_LIMIT","DAY"))
  self.assertFalse(x["submissionAuthorized"])
 def test_intraday_supported_only_with_verified_product(self):
  x=draft_packet(product_type="INTRADAY")
  self.assertEqual(x["producttype"],"INTRADAY")
 def test_wrong_contract_blocked(self):
  with self.assertRaisesRegex(ReadinessBlocked,"MISMATCH"):
   draft_packet(product_type="CARRYFORWARD",contract="NIFTY01DEC2629000CE")
 def test_wrong_token_blocked(self):
  with self.assertRaises(ReadinessBlocked):
   draft_packet(product_type="CARRYFORWARD",token="38159")
 def test_wrong_quantity_blocked(self):
  with self.assertRaises(ReadinessBlocked):
   draft_packet(product_type="CARRYFORWARD",quantity=130)
 def test_wrong_tick_blocked(self):
  with self.assertRaises(ReadinessBlocked):
   draft_packet(product_type="CARRYFORWARD",trigger=Decimal("10.01"))
 def test_reverse_stop_relation_blocked(self):
  with self.assertRaises(ReadinessBlocked):
   draft_packet(product_type="CARRYFORWARD",limit=Decimal("10.00"))
 def test_price_as_bool_rejected(self):
  with self.assertRaises(ReadinessBlocked):
   draft_packet(product_type="CARRYFORWARD",trigger=True)
 def test_premium_loss(self):
  x=assess_risk(verified_avg_buy=Decimal("12.92"),verified_quantity=65,broker_ltp="11.25")
  self.assertEqual(x["premiumLossIfFilledExactlyAtLimit"],"193.05")
  self.assertEqual(x["unrealizedPnlBeforeCosts"],"-108.55")
  self.assertIsNone(x["estimatedLossAtLimitIncludingFees"])
 def test_fee_charges_exact(self):
  x=assess_risk(verified_avg_buy=Decimal("12.92"),verified_quantity=65,
    broker_ltp="11.25",quoted_exit_fees=Decimal("30.00"),estimated_tax=Decimal("5"))
  self.assertEqual(x["estimatedLossAtLimitIncludingFees"],"228.05")
 def test_budget_exceed(self):
  x=assess_risk(verified_avg_buy=Decimal("12.92"),verified_quantity=65,
    broker_ltp="11.25",quoted_exit_fees=Decimal("650"),estimated_tax=Decimal("1"))
  self.assertTrue(x["wouldExceedBudgetAtExactLimit"])
 def test_invalid_ltp(self):
  with self.assertRaises(ReadinessBlocked):
   assess_risk(verified_avg_buy=Decimal("12.92"),verified_quantity=65,broker_ltp="-1")
 def test_invalid_entry(self):
  with self.assertRaises(ReadinessBlocked):
   assess_risk(verified_avg_buy=Decimal("12.00"),verified_quantity=65,broker_ltp="11.25")
 def test_report_is_explicitly_blocked(self):
  s=format_preflight_report(product_type="CARRYFORWARD")
  self.assertIn("BROKER_NATIVE_STOP_ACK: NOT_TESTED",s)
  self.assertIn("LIVE_ORDERS: OFF",s)
 def test_no_side_effect_calls(self):
  s=Path(__file__).with_name("manual_sl_order_readiness_v29.py").read_text()
  for name in ("placeOrder","cancelOrder","modifyOrder","urllib","requests","angel_gateway","psycopg","commit()"):
   self.assertNotIn(name,s)
if __name__=="__main__": unittest.main()
