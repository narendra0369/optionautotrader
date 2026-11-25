"""No-network mock tests: V25 never writes, never sends, always rolls back."""
import unittest
from datetime import datetime,timezone
from live_v7.pg_atomic_reservation_v25 import ReservationBlocked,reserve_under_guard

OWNER="11111111-1111-4111-8111-111111111111"
NOW=datetime(2026,11,25,12,0,tzinfo=timezone.utc)
ORDER={"broker":"Angel","market":"NIFTY","side":"ENTRY_BUY"}

class Cursor:
 def __init__(self,db):self.db=db
 def __enter__(self):return self
 def __exit__(self,*args):return False
 def execute(self,sql,params=None):
  self.db.sqls.append(sql)
  if not sql.strip().upper().startswith(("SET TRANSACTION","SELECT")):
   raise AssertionError("DB_MUTATION_NOT_PERMITTED")
 def fetchone(self):return self.db.guard

class DB:
 autocommit=False
 def __init__(self,guard=None):self.guard=guard;self.sqls=[];self.rolled=False
 def cursor(self):return Cursor(self)
 def rollback(self):self.rolled=True

def reserve(db,**kw):
 return reserve_under_guard(db,verified_owner_id=kw.get("owner",OWNER),
   broker_authenticated=kw.get("broker_authenticated",True),
   owner_authenticated=kw.get("owner_authenticated",True),
   order=kw.get("order",ORDER),idempotency_key=kw.get("key","abcdefgh1234"),
   now=kw.get("now",NOW))

class V25PostgresStoppedReservationTests(unittest.TestCase):
 def test_absent_guard_deny_and_rollback(self):
  db=DB()
  with self.assertRaisesRegex(ReservationBlocked,"GUARD_STOPPED"):
   reserve(db)
  self.assertTrue(db.rolled)
 def test_stopped_guard_deny(self):
  db=DB(("STOPPED",True))
  with self.assertRaisesRegex(ReservationBlocked,"GUARD_STOPPED"):
   reserve(db)
  self.assertTrue(db.rolled)
 def test_review_required_guard_deny(self):
  with self.assertRaisesRegex(ReservationBlocked,"GUARD_STOPPED"):
   reserve(DB(("REVIEW_REQUIRED",True)))
 def test_reset_requested_guard_deny(self):
  with self.assertRaisesRegex(ReservationBlocked,"GUARD_STOPPED"):
   reserve(DB(("RESET_REQUESTED",True)))
 def test_fake_running_guard_still_deny(self):
  db=DB(("RUNNING",False))
  with self.assertRaisesRegex(ReservationBlocked,"WORKER_NOT_CERTIFIED"):
   reserve(db)
  self.assertTrue(db.rolled)
 def test_missing_owner_rejected(self):
  with self.assertRaisesRegex(ReservationBlocked,"OWNER_UUID"):
   reserve(DB(),owner="bad")
 def test_bad_key_rejected(self):
  with self.assertRaisesRegex(ReservationBlocked,"IDEMPOTENCY"):
   reserve(DB(),key="x")
 def test_missing_broker_auth_rejected(self):
  with self.assertRaisesRegex(ReservationBlocked,"NOT_AUTHENTICATED"):
   reserve(DB(),broker_authenticated=False)
 def test_missing_owner_auth_rejected(self):
  with self.assertRaisesRegex(ReservationBlocked,"NOT_AUTHENTICATED"):
   reserve(DB(),owner_authenticated=False)
 def test_wrong_broker_rejected(self):
  with self.assertRaisesRegex(ReservationBlocked,"UNSUPPORTED_INTENT"):
   reserve(DB(),order=dict(ORDER,broker="Delta"))
 def test_wrong_order_side_rejected(self):
  with self.assertRaisesRegex(ReservationBlocked,"UNSUPPORTED_INTENT"):
   reserve(DB(),order=dict(ORDER,side="SELL"))
 def test_invalid_time_rejected(self):
  with self.assertRaisesRegex(ReservationBlocked,"AWARE"):
   reserve(DB(),now=datetime(2026,11,25))
 def test_autocommit_denied(self):
  db=DB();db.autocommit=True
  with self.assertRaisesRegex(ReservationBlocked,"TRANSACTION_REQUIRED"):
   reserve(db)
 def test_guard_row_locked_in_serializable_tx(self):
  db=DB(("STOPPED",True))
  with self.assertRaises(ReservationBlocked):
   reserve(db)
  self.assertIn("SERIALIZABLE",db.sqls[0])
  self.assertIn("FOR UPDATE",db.sqls[1])
  self.assertTrue(db.rolled)
 def test_no_order_or_db_write_calls(self):
  from pathlib import Path
  s=Path(__file__).with_name("pg_atomic_reservation_v25.py").read_text()
  self.assertNotIn("placeOrder",s)
  self.assertNotIn("INSERT INTO",s)
  self.assertNotIn("UPDATE optionx_private",s)
  self.assertNotIn("angel_gateway",s)
  self.assertNotIn("commit()",s)

if __name__=="__main__":unittest.main()
