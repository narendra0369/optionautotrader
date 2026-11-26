"""V43 durable intent prototype tests: filesystem, restart, idempotency."""
import os
import sqlite3
import tempfile
import unittest
from datetime import datetime,timezone
from pathlib import Path
from live_v7.durable_intent_v43 import open_ledger,reserve,seal_uncertain,recover,IntentBlocked

OWNER="11111111-1111-4111-8111-111111111111"
OTHER="22222222-2222-4222-8222-222222222222"
KEY="v43-test-20261126"
NOW=datetime(2026,11,26,8,0,tzinfo=timezone.utc)
ORDER={"exchange":"NFO","symbol":"NIFTY29DEC2629000CE","token":"38158",
       "side":"SELL","type":"LIMIT","price":"10.50","quantity":65,
       "producttype":"CARRYFORWARD","duration":"DAY"}

class V43DurableIntentTests(unittest.TestCase):
 def setUp(self):
    self.temp=tempfile.TemporaryDirectory()
    self.private=Path(self.temp.name)/"private"
    self.private.mkdir(mode=0o700)
    self.path=self.private/"intent.sqlite3"
    self.db=open_ledger(self.path)
 def tearDown(self):
    self.db.close()
    self.temp.cleanup()
 def reserve(self,**kw):
    return reserve(self.db,owner_id=kw.get("owner",OWNER),
                   idempotency_key=kw.get("key",KEY),
                   order=kw.get("order",ORDER),now=NOW)
 def test_reserve_only_not_order(self):
    r=self.reserve()
    self.assertEqual(r["state"],"RESERVED_UNSENT")
    self.assertFalse(r["canSubmitOrder"])
 def test_duplicate_reservation_not_dispatch(self):
    self.reserve()
    self.assertEqual(self.reserve()["result"],"ALREADY_RESERVED_NO_DISPATCH")
 def test_draft_changed_rejected(self):
    self.reserve()
    with self.assertRaisesRegex(IntentBlocked,"FIXED_DRAFT_MISMATCH"):
       self.reserve(order=dict(ORDER,price="10.55"))
 def test_crash_restart_still_reserved(self):
    self.reserve()
    self.db.close()
    self.db=open_ledger(self.path)
    self.assertEqual(recover(self.db,owner_id=OWNER,idempotency_key=KEY,now=NOW)["state"],"RESERVED_UNSENT")
 def test_uncertain_seal_persists_restart(self):
    self.reserve()
    seal_uncertain(self.db,owner_id=OWNER,idempotency_key=KEY,now=NOW)
    self.db.close()
    self.db=open_ledger(self.path)
    r=recover(self.db,owner_id=OWNER,idempotency_key=KEY,now=NOW)
    self.assertEqual(r["state"],"MAY_HAVE_SENT_RECONCILE")
    self.assertFalse(r["canRetry"])
 def test_repeat_seal_idempotent(self):
    self.reserve()
    seal_uncertain(self.db,owner_id=OWNER,idempotency_key=KEY,now=NOW)
    seal_uncertain(self.db,owner_id=OWNER,idempotency_key=KEY,now=NOW)
    self.assertEqual(self.db.execute("SELECT COUNT(*) FROM events").fetchone()[0],2)
 def test_unknown_owner_blocked(self):
    self.reserve()
    with self.assertRaisesRegex(IntentBlocked,"INTENT_UNKNOWN"):
        recover(self.db,owner_id=OTHER,idempotency_key=KEY,now=NOW)
 def test_missing_reservation_seal_blocked(self):
    with self.assertRaisesRegex(IntentBlocked,"INTENT_UNKNOWN"):
       seal_uncertain(self.db,owner_id=OWNER,idempotency_key=KEY,now=NOW)
 def test_same_key_different_owner_isolated(self):
    self.reserve()
    self.reserve(owner=OTHER)
    self.assertEqual(self.db.execute("SELECT COUNT(*) FROM intents").fetchone()[0],2)
 def test_file_permissions(self):
    self.assertEqual(self.path.stat().st_mode&0o777,0o600)
 def test_world_readable_directory_blocked(self):
    with self.assertRaisesRegex(IntentBlocked,"PRIVATE_DIRECTORY_PERMISSIONS"):
       open_ledger(Path(self.temp.name)/"public.db")
 def test_relative_path_blocked(self):
    with self.assertRaisesRegex(IntentBlocked,"ABSOLUTE"):
       open_ledger("test.db")
 def test_symlink_blocked(self):
    link=self.private/"alias.sqlite3"
    link.symlink_to(self.path)
    with self.assertRaisesRegex(IntentBlocked,"ABSOLUTE_NON_SYMLINK"):
       open_ledger(link)
 def test_trading_credentials_cannot_be_persisted(self):
    with self.assertRaisesRegex(IntentBlocked,"EXACT_ORDER_FIELDS"):
       self.reserve(order=dict(ORDER,api_key="forbidden"))
 def test_invalid_owner_blocked(self):
    with self.assertRaisesRegex(IntentBlocked,"OWNER_UUID"):
       self.reserve(owner="not-an-owner")
 def test_no_broker_transport(self):
    src=Path(__file__).with_name("durable_intent_v43.py").read_text()
    for forbidden in ("placeOrder","cancelOrder","modifyOrder","angel_gateway","urllib.request","psycopg"):
       self.assertNotIn(forbidden,src)

if __name__=="__main__":unittest.main()
