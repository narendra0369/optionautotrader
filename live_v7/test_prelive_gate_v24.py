"""Offline SEBI/Angel pre-live gate tests; NO order side effects."""
import unittest
from dataclasses import replace
from live_v7.prelive_gate_v24 import (
    RetailAlgoAttestation,check_order_contract,evaluate_prelive
)
BASE=RetailAlgoAttestation(*([True]*9))
ENTRY={"kind":"ENTRY","exchange":"NFO","duration":"DAY",
       "side":"BUY","order_type":"LIMIT","variety":"NORMAL",
       "quantity":65,"instrument_token":"12345"}
STOP={"kind":"PROTECT","exchange":"NFO","duration":"DAY",
      "side":"SELL","order_type":"STOPLOSS_LIMIT","variety":"STOPLOSS",
      "quantity":65,"instrument_token":"12345"}
AUDIT={"liveOrdersEnabled":False,"manualOrUntrackedOrders":0,
       "brokerSnapshotFreshAndAuthenticated":True}

def eval_gate(att=BASE,audit=AUDIT,entry=ENTRY,stop=STOP,**kw):
 return evaluate_prelive(compliance=att,read_only_audit=audit,
   durable_guard_state=kw.get("guard","STOPPED"),
   daily_reserved_auto_entries=kw.get("count",0),
   recent_broker_orders_per_second=kw.get("ops",0),
   intended_entry=entry,intended_protection=stop,
   verified_account_exposure_count=kw.get("exposure",0),
   owner_authenticated=kw.get("owner_authenticated",True))

class V24PreliveGateTests(unittest.TestCase):
 def test_all_green_still_source_locked(self):
  r=eval_gate()
  self.assertFalse(r["canSubmitOrder"])
  self.assertFalse(r["liveOrdersEnabled"])
  self.assertIn("REAL_EXECUTION_SOURCE_LOCKED",r["blockedReasons"])
 def test_actual_user_manual_order_still_blocks(self):
  r=eval_gate(audit=dict(AUDIT,manualOrUntrackedOrders=1),exposure=1)
  self.assertIn("MANUAL_OR_UNTRACKED_ORDERS_PRESENT",r["blockedReasons"])
  self.assertIn("ACCOUNT_MANUAL_OR_UNTRACKED_EXPOSURE_PRESENT",r["blockedReasons"])
 def test_unapproved_static_ip_blocks(self):
  r=eval_gate(att=replace(BASE,hosted_on_own_registered_static_ip=False))
  self.assertIn("PRIMARY_STATIC_IP_APPROVAL_UNCONFIRMED",r["blockedReasons"])
 def test_broker_write_permission_not_inferred_from_get(self):
  r=eval_gate(att=replace(BASE,broker_writing_enabled_for_api_key=False))
  self.assertIn("BROKER_ORDER_API_PERMISSION_UNCONFIRMED",r["blockedReasons"])
 def test_algo_tag_required(self):
  r=eval_gate(att=replace(BASE,broker_confirmed_generic_algo_tag=False))
  self.assertIn("EXCHANGE_GENERIC_ALGO_TAG_UNCONFIRMED",r["blockedReasons"])
 def test_broker_stop_contract_required(self):
  r=eval_gate(att=replace(BASE,broker_confirmed_limit_and_sl_limit_for_nfo=False))
  self.assertIn("BROKER_NATIVE_LIMIT_STOP_API_UNCONFIRMED",r["blockedReasons"])
 def test_market_entry_is_prohibited(self):
  r=eval_gate(entry=dict(ENTRY,order_type="MARKET"))
  self.assertIn("ALGO_MARKET_OR_IOC_PROHIBITED",r["blockedReasons"])
 def test_ioc_prohibited(self):
  r=eval_gate(entry=dict(ENTRY,duration="IOC"))
  self.assertIn("ALGO_MARKET_OR_IOC_PROHIBITED",r["blockedReasons"])
 def test_stop_market_not_permitted(self):
  r=eval_gate(stop=dict(STOP,order_type="STOPLOSS_MARKET"))
  self.assertIn("NATIVE_SELL_SL_LIMIT_REQUIRED",r["blockedReasons"])
 def test_valid_limit_contracts(self):
  self.assertEqual(check_order_contract(ENTRY),[])
  self.assertEqual(check_order_contract(STOP),[])
 def test_order_rate_threshold(self):
  r=eval_gate(ops=10)
  self.assertIn("BROKER_OPS_THRESHOLD_REACHED_OR_UNKNOWN",r["blockedReasons"])
 def test_two_entries_count(self):
  r=eval_gate(count=2)
  self.assertIn("DAILY_TWO_ENTRY_LIMIT_REACHED",r["blockedReasons"])
 def test_bad_daily_count(self):
  r=eval_gate(count=3)
  self.assertIn("DAILY_TWO_ENTRY_BUDGET_INVALID",r["blockedReasons"])
 def test_broker_snapshot_stale(self):
  r=eval_gate(audit=dict(AUDIT,brokerSnapshotFreshAndAuthenticated=False))
  self.assertIn("FRESH_AUTHENTICATED_BROKER_SNAPSHOT_REQUIRED",r["blockedReasons"])
 def test_owner_auth_required(self):
  r=eval_gate(owner_authenticated=False)
  self.assertIn("OWNER_REAUTHENTICATION_REQUIRED",r["blockedReasons"])
 def test_bounded_real_test_requires_consent(self):
  r=eval_gate(att=replace(BASE,live_test_risk_authorized=False))
  self.assertIn("BOUNDED_REAL_MONEY_TEST_NOT_AUTHORIZED",r["blockedReasons"])
 def test_broker_test_window_confirmation(self):
  r=eval_gate(att=replace(BASE,broker_test_window_confirmed=False))
  self.assertIn("BROKER_TEST_WINDOW_UNCONFIRMED",r["blockedReasons"])
 def test_no_execution_imports(self):
  from pathlib import Path
  s=Path(__file__).with_name("prelive_gate_v24.py").read_text()
  self.assertNotIn("angel_execution_transport",s)
  self.assertNotIn("placeOrder",s)
  self.assertNotIn("cancelOrder",s)
  self.assertNotIn("psycopg",s)

if __name__=="__main__": unittest.main()
