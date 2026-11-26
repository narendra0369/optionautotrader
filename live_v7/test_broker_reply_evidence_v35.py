"""V35 broker reply evidence tests. Pure offline; no execution authorization."""
import unittest
from pathlib import Path
from live_v7.broker_reply_evidence_v35 import review_broker_reply_evidence

BASE={
 "written_reply_authenticated": True,
 "account_trading_api_entitlement_confirmed": True,
 "fno_segment_active": True,
 "registered_static_ip_confirmed": True,
 "self_declaration_undertaking_confirmed": True,
 "algo_tagging_requirements_confirmed": True,
 "same_account_producttype_broker_verified": True,
 "broker_current_position_and_orders_reconciled": True,
 "independent_live_order_journal_certified": True,
 "unknown_order_outcome_recovery_certified": True,
 "actual_fees_and_taxes_verified": True,
 "final_exact_order_authorization": True,
 "contract":"NIFTY29DEC2629000CE", "token":"38158",
 "net_long_quantity":65,"order_type":"LIMIT",
 "market_session_verified":True, "lpp_band_broker_confirmed":True,
 "all_in_fees":"30.00",
}

class V35BrokerReplyEvidenceTests(unittest.TestCase):
 def check_block(self, expected, **kwargs):
  p=dict(BASE,**kwargs)
  r=review_broker_reply_evidence(p)
  self.assertIn(expected,r["blockers"])
  self.assertFalse(r["canSubmitOrder"])
 def test_missing_all_blocks(self):
  self.assertGreater(len(review_broker_reply_evidence({})["blockers"]),10)
 def test_mock_all_true_still_cannot_trade(self):
  r=review_broker_reply_evidence(BASE)
  self.assertTrue(r["brokerReplyChecklistComplete"])
  self.assertFalse(r["canSubmitOrder"])
  self.assertFalse(r["realOrdersEnabled"])
 def test_reply_not_authenticated(self):
  self.check_block("BROKER_REPLY_AUTHENTICITY_UNVERIFIED",written_reply_authenticated=False)
 def test_trading_entitlement_unverified(self):
  self.check_block("ACCOUNT_TRADING_API_PERMISSION_UNVERIFIED",account_trading_api_entitlement_confirmed=False)
 def test_fno_segment_not_confirmed(self):
  self.check_block("FNO_SEGMENT_UNVERIFIED",fno_segment_active=False)
 def test_static_ip_not_confirmed(self):
  self.check_block("STATIC_IP_WHITELIST_UNVERIFIED",registered_static_ip_confirmed=False)
 def test_undertaking_not_confirmed(self):
  self.check_block("UNDERTAKING_UNVERIFIED",self_declaration_undertaking_confirmed=False)
 def test_algo_tagging_not_confirmed(self):
  self.check_block("ALGO_TAGGING_UNVERIFIED",algo_tagging_requirements_confirmed=False)
 def test_producttype_unverified(self):
  self.check_block("POSITION_PRODUCTTYPE_UNVERIFIED",same_account_producttype_broker_verified=False)
 def test_stale_broker_books(self):
  self.check_block("BROKER_POSITION_ORDERBOOK_STALE_OR_UNVERIFIED",broker_current_position_and_orders_reconciled=False)
 def test_recovery_not_certified(self):
  self.check_block("UNKNOWN_OUTCOME_RECOVERY_UNCERTIFIED",unknown_order_outcome_recovery_certified=False)
 def test_dynamic_lpp_unverified(self):
  self.check_block("DYNAMIC_LPP_UNVERIFIED",lpp_band_broker_confirmed=False)
 def test_missing_real_fees(self):
  self.check_block("FEES_VALUE_UNKNOWN",all_in_fees=None)
 def test_quantity_changed(self):
  self.check_block("QUANTITY_NOT_RECONFIRMED",net_long_quantity=0)
 def test_stop_or_limit_only(self):
  self.check_block("ORDER_TYPE_UNVERIFIED",order_type="MARKET")
 def test_no_final_authorization(self):
  self.check_block("FINAL_ORDER_AUTHORIZATION_MISSING",final_exact_order_authorization=False)
 def test_no_lpp_retry_even_on_mock_complete(self):
  r=review_broker_reply_evidence(BASE)
  self.assertFalse(r["automaticResubmitOn17070"])
  self.assertFalse(r["automaticRetryOnUnknownOutcome"])
 def test_no_network_or_order_transport(self):
  src=Path(__file__).with_name("broker_reply_evidence_v35.py").read_text()
  for forbidden in ("placeOrder","cancelOrder","angel_gateway","angel_execution_transport","urllib.request","psycopg"):
   self.assertNotIn(forbidden,src)
if __name__=="__main__":unittest.main()
