"""V18 offline lifecycle regression: no broker orders, no credentials."""
import os
import sqlite3
import tempfile
import unittest
from datetime import datetime,timezone,timedelta
from pathlib import Path

from live_v7.lifecycle_rehearsal_v18 import (
 LifecycleError, open_rehearsal, reserve, before_possible_send,
 broker_fill_observed, confirm_protection, recovery_review,
)

OWNER="11111111-1111-4111-8111-111111111111"
T=datetime(2026,11,25,6,30,tzinfo=timezone.utc)
SYMBOL="NIFTY29DEC2629000CE"
DAY="2026-11-25"

class V18LifecycleTests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory()
  self.p=Path(self.tmp.name)/"lifecycle.sqlite3"
  self.c=open_rehearsal(self.p)
 def tearDown(self):
  self.c.close();self.tmp.cleanup()
 def reserve(self,key="abcde123"):
  return reserve(self.c,verified_owner_id=OWNER,owner_authenticated=True,intent_key=key,
    symbol=SYMBOL,instrument_token="12345",quantity=65,now=T)
 def sent(self,key="abcde123"):
  self.reserve(key)
  return before_possible_send(self.c,verified_owner_id=OWNER,intent_key=key,
                             day_ist=DAY,now=T)
 def fill(self,status,quantity,key="abcde123"):
  return broker_fill_observed(self.c,verified_owner_id=OWNER,intent_key=key,
    day_ist=DAY,broker_order_id="broker987" if key=="abcde123" else "broker988",filled_quantity=quantity,
    status=status,source_authenticated=True,now=T)
 def stop(self, qty=65, oid="stop987", status="TRIGGER_PENDING"):
  return confirm_protection(self.c,verified_owner_id=OWNER,intent_key="abcde123",day_ist=DAY,
    broker_snapshot={"as_of":T,"order_id":oid,"symbol":SYMBOL,
        "instrument_token":"12345","side":"SELL","ordertype":"STOPLOSS_LIMIT",
        "variety":"STOPLOSS","status":status,"remaining_quantity":qty},
    source_authenticated=True,now=T)
 def test_idempotent_reserve(self):
  self.assertTrue(self.reserve()["reserved"])
  self.assertTrue(self.reserve()["duplicate"])
  self.assertEqual(self.c.execute("select count(*) from owned_entries").fetchone()[0],1)
 def test_missing_owner_auth(self):
  with self.assertRaisesRegex(LifecycleError,"OWNER_AUTH"):
   reserve(self.c,verified_owner_id=OWNER,owner_authenticated=False,intent_key="abcde123",symbol=SYMBOL,instrument_token="12345",quantity=65,now=T)
 def test_two_entry_cap_including_rejected(self):
  self.sent()
  self.fill("REJECTED",0)
  self.sent("abcde124")
  self.fill("REJECTED",0,key="abcde124")
  with self.assertRaisesRegex(LifecycleError,"TWO_AUTO"):
   self.reserve("abcde125")
 def test_unresolved_blocks_new(self):
  self.reserve()
  with self.assertRaisesRegex(LifecycleError,"REQUIRES_RECONCILIATION"):
   self.reserve("abcde124")
 def test_send_barrier_is_durable_and_not_replayable(self):
  self.sent()
  self.c.close()
  self.c=open_rehearsal(self.p)
  with self.assertRaisesRegex(LifecycleError,"SEND_ALREADY"):
   before_possible_send(self.c,verified_owner_id=OWNER,intent_key="abcde123",day_ist=DAY,now=T)
  self.assertEqual(self.c.execute("select state from owned_entries").fetchone()[0],"SEND_UNCERTAIN")
 def test_unknown_status_never_clear(self):
  self.sent()
  with self.assertRaisesRegex(LifecycleError,"UNKNOWN"):
   self.fill("WEIRD",0)
  self.assertEqual(self.c.execute("select state from owned_entries").fetchone()[0],"SEND_UNCERTAIN")
 def test_partial_fills_monotonic(self):
  self.sent()
  self.fill("PARTIALLY_FILLED",25)
  with self.assertRaisesRegex(LifecycleError,"REGRESSION"):
   self.fill("PARTIALLY_FILLED",20)
  self.assertEqual(self.fill("COMPLETE",65)["filledQuantity"],65)
 def test_complete_requires_quantity(self):
  self.sent()
  with self.assertRaisesRegex(LifecycleError,"COMPLETE_QUANTITY"):
   self.fill("COMPLETE",25)
 def test_rejected_cannot_have_fill(self):
  self.sent()
  with self.assertRaisesRegex(LifecycleError,"REJECTED_WITH_FILL"):
   self.fill("REJECTED",25)
 def test_stop_rejects_wrong_qty(self):
  self.sent();self.fill("COMPLETE",65)
  with self.assertRaisesRegex(LifecycleError,"STOP_NOT_FULLY"):
   self.stop(qty=25)
 def test_stop_requires_independent_broker_evidence(self):
  self.sent();self.fill("COMPLETE",65)
  with self.assertRaisesRegex(LifecycleError,"STOP_EVIDENCE"):
   confirm_protection(self.c,verified_owner_id=OWNER,intent_key="abcde123",day_ist=DAY,broker_snapshot={},source_authenticated=False,now=T)
 def test_stop_status_rejected(self):
  self.sent();self.fill("COMPLETE",65)
  with self.assertRaisesRegex(LifecycleError,"STOP_NOT_FULLY"):
   self.stop(status="CANCELLED")
 def test_stop_stale(self):
  self.sent();self.fill("COMPLETE",65)
  with self.assertRaisesRegex(LifecycleError,"STOP_SNAPSHOT_STALE"):
   confirm_protection(self.c,verified_owner_id=OWNER,intent_key="abcde123",day_ist=DAY,
    broker_snapshot={"as_of":T-timedelta(minutes=1)},source_authenticated=True,now=T)
 def test_stop_positive_but_entries_stay_blocked(self):
  self.sent();self.fill("COMPLETE",65)
  r=self.stop()
  self.assertTrue(r["protectiveStopBrokerObserved"])
  self.assertFalse(r["canSubmitOrder"])
  self.assertFalse(r["stopFillGuaranteed"])
 def test_manual_position_never_modified(self):
  self.sent();self.fill("COMPLETE",65)
  result=recovery_review(self.c,verified_owner_id=OWNER,
    broker_orders=[{"order_id":"manual111"}],
    broker_positions=[{"symbol":SYMBOL,"net_quantity":65}],
    source_authenticated=True,now=T)
  self.assertEqual(result["manualOrUntrackedOrders"],1)
  self.assertFalse(result["manualOrdersModified"])
  self.assertFalse(result["canCancelOrder"])
  self.assertIn("MANUAL_OR_UNTRACKED_ACCOUNT_EXPOSURE",result["blocks"])
 def test_restart_recovery_blocks_despite_confirmed_stop(self):
  self.sent();self.fill("COMPLETE",65);self.stop()
  self.c.close();self.c=open_rehearsal(self.p)
  r=recovery_review(self.c,verified_owner_id=OWNER,broker_orders=[],
        broker_positions=[],source_authenticated=True,now=T)
  self.assertTrue(r["newEntriesBlocked"])
  self.assertIn("PRODUCTION_LEDGER_NOT_CONNECTED",r["blocks"])
 def test_unauthenticated_recovery_is_blocked(self):
  r=recovery_review(self.c,verified_owner_id=OWNER,broker_orders=[],
       broker_positions=[],source_authenticated=False,now=T)
  self.assertIn("BROKER_BOOKS_UNAUTHENTICATED",r["blocks"])
 def test_append_only_events(self):
  self.reserve()
  with self.assertRaises(sqlite3.IntegrityError):
   self.c.execute("DELETE FROM lifecycle_events")
 def test_permissions_file(self):
  self.c.close();os.chmod(self.p,0o644)
  with self.assertRaisesRegex(LifecycleError,"PERMISSIONS_UNSAFE"):
   open_rehearsal(self.p)
  os.chmod(self.p,0o600);self.c=open_rehearsal(self.p)
 def test_date_boundary_reservation(self):
  self.reserve()
  next_day=T+timedelta(days=1)
  with self.assertRaisesRegex(LifecycleError,"REQUIRES_RECONCILIATION"):
   reserve(self.c,verified_owner_id=OWNER,owner_authenticated=True,intent_key="another123",
      symbol=SYMBOL,instrument_token="12345",quantity=65,now=next_day)

if __name__=="__main__":
 unittest.main()
