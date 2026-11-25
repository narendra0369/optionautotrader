"""V23 offline failure matrix; no credentials, broker network or SQL writes."""
import unittest
from datetime import datetime,timezone,timedelta
from live_v7.execution_coordinator_v23 import (
    OwnedPosition,CoordinationError,recover_snapshot,evaluate_exit,apply_verified_exit_fill
)
NOW=datetime(2026,11,25,12,0,tzinfo=timezone.utc)
SYM="NIFTY29DEC2629000CE"
POS=OwnedPosition(entry_order_id="entry123",contract_token="12345",
                  symbol=SYM,entry_filled=65,stop_order_id="stop123",
                  stop_active_remaining=65)
OWNED=[{"order_id":"entry123"},{"order_id":"stop123"}]
STOP={"order_id":"stop123","symbol":SYM,"contract_token":"12345",
      "side":"SELL","status":"TRIGGER_PENDING","remaining_quantity":65}

def recovery(positions=None,orders=None,account=None,**kw):
 return recover_snapshot(owned_positions=[] if positions is None else positions,
  broker_orders=[] if orders is None else orders,
  broker_positions=[] if account is None else account,
  authenticated_owner=kw.get("authenticated_owner",True),
  authenticated_broker=kw.get("authenticated_broker",True),
  books_complete=kw.get("books_complete",True),
  as_of=kw.get("as_of",NOW),now=NOW,
  persisted_guard_state=kw.get("persisted_guard_state","STOPPED"),
  daily_auto_entry_reservations=kw.get("daily_auto_entry_reservations",0))
def exit_eval(pos=POS,row=STOP,**kw):
 return evaluate_exit(position=pos,broker_stop_order=row,
     broker_authenticated=kw.get("broker_authenticated",True),
     as_of=kw.get("as_of",NOW),now=NOW,
     target_requested=kw.get("target_requested",False),
     stop_cancel_confirmation=kw.get("stop_cancel_confirmation",False))

class V23ExecutionCoordinatorTests(unittest.TestCase):
 def test_no_orders_never_unlocks(self):
  r=recovery()
  self.assertFalse(r["canSubmitOrder"])
  self.assertFalse(r["liveOrdersEnabled"])
 def test_manual_order_is_never_adopted(self):
  r=recovery(orders=OWNED+[{"order_id":"manual999"}],positions=[POS])
  self.assertEqual(r["untrackedBrokerOrderCount"],1)
  self.assertFalse(r["manualPositionsModified"])
  self.assertIn("MANUAL_OR_UNTRACKED_ORDER_PRESENT",r["blockedReasons"])
 def test_manual_position_same_symbol_blocked(self):
  r=recovery(orders=OWNED,positions=[POS],account=[{"symbol":SYM,"net_quantity":65}])
  self.assertIn("ACCOUNT_POSITION_OWNERSHIP_NOT_PARTITIONED",r["blockedReasons"])
 def test_restart_unknown_exit_requires_no_retry(self):
  from dataclasses import replace
  r=recovery(orders=OWNED,positions=[replace(POS,exit_outcome_unknown=True)])
  self.assertIn("UNKNOWN_EXIT_OUTCOME_NO_RETRY",r["blockedReasons"])
  self.assertFalse(r["canResendAmbiguousOrder"])
 def test_partial_fill_not_protected(self):
  pos=OwnedPosition("entry123","12345",SYM,65,exit_filled=25,stop_order_id="stop123",stop_active_remaining=0)
  r=recovery(orders=OWNED,positions=[pos])
  self.assertIn("OPEN_EXPOSURE_WITHOUT_FULL_STOP",r["blockedReasons"])
 def test_missing_stop_blocks(self):
  r=recovery(orders=[{"order_id":"entry123"}],positions=[POS])
  self.assertIn("OWNED_STOP_ORDER_NOT_FOUND",r["blockedReasons"])
 def test_missing_entry_blocks(self):
  r=recovery(orders=[{"order_id":"stop123"}],positions=[POS])
  self.assertIn("OWNED_ENTRY_ORDER_NOT_FOUND",r["blockedReasons"])
 def test_stale_snapshot_blocks(self):
  r=recovery(as_of=NOW-timedelta(seconds=11))
  self.assertIn("STALE_OR_INCOMPLETE_BROKER_BOOKS",r["blockedReasons"])
 def test_broker_disconnected_blocks(self):
  r=recovery(authenticated_broker=False)
  self.assertIn("UNAUTHENTICATED_RECOVERY_SNAPSHOT",r["blockedReasons"])
 def test_daily_cap_exceeded_blocks(self):
  r=recovery(daily_auto_entry_reservations=3)
  self.assertIn("DAILY_ENTRY_COUNTER_INVALID_OR_EXCEEDED",r["blockedReasons"])
 def test_guard_missing_running_blocks(self):
  r=recovery(persisted_guard_state="RUNNING")
  self.assertIn("PERSISTED_KILL_SWITCH_INVALID",r["blockedReasons"])
 def test_active_native_stop_passes_shadow_but_no_orders(self):
  r=exit_eval()
  self.assertTrue(r["stopCoverageShadowVerified"])
  self.assertFalse(r["targetOrderAllowed"])
  self.assertFalse(r["canPlaceOrCancelBrokerOrder"])
 def test_target_while_stop_active_blocks_oco(self):
  r=exit_eval(target_requested=True)
  self.assertIn("NO_CERTIFIED_ATOMIC_OCO_NO_TARGET_ORDER",r["blockedReasons"])
  self.assertIn("STOP_CANCELLATION_NOT_CONFIRMED",r["blockedReasons"])
 def test_confirmed_cancel_still_not_target_permission(self):
  r=exit_eval(target_requested=True,stop_cancel_confirmation=True)
  self.assertIn("POST_CANCEL_RECONCILIATION_REQUIRED",r["blockedReasons"])
  self.assertFalse(r["targetOrderAllowed"])
 def test_stop_partial_quantity_rejected(self):
  r=exit_eval(row=dict(STOP,remaining_quantity=25))
  self.assertIn("STOP_REMAINING_QUANTITY_MISMATCH",r["blockedReasons"])
 def test_stop_order_id_not_owned(self):
  r=exit_eval(row=dict(STOP,order_id="manual999"))
  self.assertIn("STOP_NOT_PLATFORM_OWNED",r["blockedReasons"])
 def test_stop_cancelled_not_active(self):
  r=exit_eval(row=dict(STOP,status="CANCELLED"))
  self.assertIn("STOP_NOT_BROKER_ACTIVE",r["blockedReasons"])
 def test_stop_missing(self):
  r=exit_eval(row=None)
  self.assertIn("BROKER_STOP_ORDER_MISSING",r["blockedReasons"])
 def test_stale_stop_snapshot(self):
  r=exit_eval(as_of=NOW-timedelta(seconds=20))
  self.assertIn("BROKER_STOP_BOOK_UNVERIFIED",r["blockedReasons"])
 def test_zero_open_position_does_not_sell(self):
  pos=OwnedPosition("entry123","12345",SYM,65,exit_filled=65)
  r=exit_eval(pos=pos,row=None,target_requested=True)
  self.assertIn("ALREADY_FLAT_NO_MORE_SELL",r["blockedReasons"])
 def test_exit_ownership_cannot_use_manual_order(self):
  with self.assertRaisesRegex(CoordinationError,"NOT_OWNED"):
   apply_verified_exit_fill(position=POS,exit_order_id="manual999",
        newly_confirmed_cumulative_exit_qty=25,
        broker_authenticated=True,tradebook_verified=True)
 def test_exit_fill_requires_tradebook_proof(self):
  with self.assertRaisesRegex(CoordinationError,"NOT_VERIFIED"):
   apply_verified_exit_fill(position=POS,exit_order_id="stop123",
        newly_confirmed_cumulative_exit_qty=25,
        broker_authenticated=True,tradebook_verified=False)
 def test_exit_fill_unknown_and_invalidates_stop(self):
  p=apply_verified_exit_fill(position=POS,exit_order_id="stop123",
      newly_confirmed_cumulative_exit_qty=25,
      broker_authenticated=True,tradebook_verified=True)
  self.assertEqual(p.net_open,40)
  self.assertEqual(p.stop_active_remaining,0)
  self.assertTrue(p.exit_outcome_unknown)
  self.assertFalse(exit_eval(pos=p,row=STOP)["stopCoverageShadowVerified"])
 def test_over_exit_qty_denied(self):
  with self.assertRaisesRegex(CoordinationError,"OVERSELL"):
   apply_verified_exit_fill(position=POS,exit_order_id="stop123",
     newly_confirmed_cumulative_exit_qty=66,
     broker_authenticated=True,tradebook_verified=True)
 def test_exit_regression_denied(self):
  p=OwnedPosition("entry123","12345",SYM,65,exit_filled=25,stop_order_id="stop123",stop_active_remaining=0)
  with self.assertRaisesRegex(CoordinationError,"REGRESSION"):
   apply_verified_exit_fill(position=p,exit_order_id="stop123",
     newly_confirmed_cumulative_exit_qty=20,
     broker_authenticated=True,tradebook_verified=True)
 def test_invalid_qty_never_supported(self):
  with self.assertRaisesRegex(CoordinationError,"QUANTITY"):
   recovery(positions=[OwnedPosition("entry123","12345",SYM,65,exit_filled=70)])
 def test_duplicate_own_id_blocks(self):
  r=recovery(positions=[POS,POS],orders=OWNED)
  self.assertIn("DUPLICATE_OWNED_ORDER_ID",r["blockedReasons"])
 def test_duplicate_broker_id_blocks(self):
  r=recovery(orders=[{"order_id":"manual999"},{"order_id":"manual999"}])
  self.assertIn("DUPLICATE_BROKER_ORDER_ID",r["blockedReasons"])
 def test_never_imports_execution_transport(self):
  from pathlib import Path
  s=Path(__file__).with_name("execution_coordinator_v23.py").read_text()
  self.assertNotIn("angel_execution_transport",s)
  self.assertNotIn("placeOrder",s)
  self.assertNotIn("cancelOrder",s)
  self.assertNotIn("psycopg.connect",s)

if __name__=="__main__":unittest.main()
