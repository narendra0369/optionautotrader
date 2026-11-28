"""V22 private broker/ledger join regression, NO network or live orders."""
import unittest
from datetime import datetime, timezone, timedelta
from live_v7.aws_runtime_evidence_v22 import review_runtime_evidence,RuntimeEvidenceError

OWNER="11111111-1111-4111-8111-111111111111"
NOW=datetime(2026,11,25,12,0,tzinfo=timezone.utc)
SYM="NIFTY29DEC2629000CE"
ENTRY={"orderid":"owned123","tradingsymbol":SYM,"symboltoken":"12345",
       "transactiontype":"BUY","quantity":"65","filledshares":"65"}
STOP={"orderid":"stop123","exchange":"NFO","tradingsymbol":SYM,
      "symboltoken":"12345","transactiontype":"SELL","variety":"STOPLOSS",
      "ordertype":"STOPLOSS_LIMIT","orderstatus":"trigger pending",
      "quantity":"65","filledshares":"0","unfilledshares":"65",
      "triggerprice":"90","price":"89"}
TRADE={"exchange":"NFO","orderid":"owned123","fillid":"fill001",
       "fillsize":"65","fillprice":"100","tradingsymbol":SYM,
       "transactiontype":"BUY"}

class Cursor:
 def __init__(self,db):self.db=db
 def __enter__(self):return self
 def __exit__(self,*args):return False
 def execute(self,sql,params):
  assert "SELECT" in sql and "optionx_private" in sql
  assert "INSERT" not in sql and "UPDATE" not in sql and "DELETE" not in sql
  self.db.queries+=1
 def fetchall(self):return self.db.rows

class Database:
 autocommit=False
 def __init__(self,rows=()):self.rows=list(rows);self.queries=0
 def cursor(self):return Cursor(self)

def review(db,orders=None,trades=None,**kwargs):
 return review_runtime_evidence(
   db,verified_owner_id=OWNER,
   owner_authenticated=kwargs.get("owner_authenticated",True),
   broker_authenticated=kwargs.get("broker_authenticated",True),
   orderbook_raw=orders if orders is not None else [],
   tradebook_raw=trades if trades is not None else [],
   snapshot_at=kwargs.get("snapshot_at",NOW),now=NOW)

class V22RuntimeEvidenceTests(unittest.TestCase):
 def test_empty_ledger_no_adoption(self):
  r=review(Database(),orders=[dict(ENTRY,orderid="manual123")],trades=[TRADE])
  self.assertEqual(r["trackedEntries"],0)
  self.assertEqual(r["manualOrUntrackedOrders"],1)
  self.assertIn("NO_OPTIONX_OWNED_ORDERS_TO_VERIFY",r["blockedReasons"])
  self.assertFalse(r["liveOrdersEnabled"])
 def test_valid_owned_order_and_owned_stop_evidence(self):
  db=Database([("owned123",SYM,"12345",65,65,"stop123",65,65,"STOP_ACKED")])
  r=review(db,orders=[ENTRY,STOP],trades=[TRADE])
  self.assertEqual(r["verifiedFillOrders"],1)
  self.assertEqual(r["verifiedStopsObserved"],1)
  self.assertFalse(r["canSubmitOrder"])
  self.assertEqual(r["manualOrUntrackedOrders"],0)
 def test_manual_matching_symbol_does_not_get_adopted(self):
  db=Database([("owned123",SYM,"12345",65,65,"stop123",65,65,"STOP_ACKED")])
  manual=dict(ENTRY,orderid="manual456")
  r=review(db,orders=[ENTRY,STOP,manual],trades=[TRADE])
  self.assertEqual(r["manualOrUntrackedOrders"],1)
  self.assertIn("MANUAL_OR_UNTRACKED_BROKER_ORDER",r["blockedReasons"])
 def test_missing_owned_order(self):
  db=Database([("owned123",SYM,"12345",65,65,None,None,None,None)])
  r=review(db)
  self.assertIn("OWNED_ORDER_MISSING_FROM_BROKER_BOOK",r["blockedReasons"])
 def test_no_broker_order_id(self):
  db=Database([(None,SYM,"12345",65,0,None,None,None,None)])
  r=review(db)
  self.assertIn("OWNED_ORDER_WITHOUT_BROKER_ID",r["blockedReasons"])
 def test_stop_not_found(self):
  db=Database([("owned123",SYM,"12345",65,65,"stop123",65,65,"STOP_ACKED")])
  r=review(db,orders=[ENTRY],trades=[TRADE])
  self.assertIn("OWNED_STOP_NOT_IN_BROKER_BOOK",r["blockedReasons"])
 def test_partial_stop_quantity_mismatch(self):
  db=Database([("owned123",SYM,"12345",65,65,"stop123",65,65,"STOP_ACKED")])
  r=review(db,orders=[ENTRY,dict(STOP,unfilledshares="40",filledshares="25")],trades=[TRADE])
  self.assertIn("OWNED_ENTRY_OR_STOP_PROOF_FAILED",r["blockedReasons"])
 def test_stored_fill_mismatch(self):
  db=Database([("owned123",SYM,"12345",65,25,"stop123",25,25,"STOP_ACKED")])
  r=review(db,orders=[ENTRY,STOP],trades=[TRADE])
  self.assertIn("LEDGER_FILL_NOT_YET_RECONCILED",r["blockedReasons"])
 def test_tradebook_fill_mismatch(self):
  db=Database([("owned123",SYM,"12345",65,65,"stop123",65,65,"STOP_ACKED")])
  r=review(db,orders=[ENTRY,STOP],trades=[])
  self.assertIn("OWNED_ENTRY_OR_STOP_PROOF_FAILED",r["blockedReasons"])
 def test_duplicate_order_ids(self):
  with self.assertRaisesRegex(RuntimeEvidenceError,"DUPLICATED"):
   review(Database(),orders=[ENTRY,ENTRY])
 def test_unauthenticated_owner(self):
  with self.assertRaisesRegex(RuntimeEvidenceError,"UNVERIFIED"):
   review(Database(),owner_authenticated=False)
 def test_unauthenticated_broker(self):
  with self.assertRaisesRegex(RuntimeEvidenceError,"UNVERIFIED"):
   review(Database(),broker_authenticated=False)
 def test_stale_snapshot(self):
  with self.assertRaisesRegex(Exception,"STALE"):
   review(Database(),snapshot_at=NOW-timedelta(seconds=12))
 def test_no_pg_autocommit(self):
  db=Database();db.autocommit=True
  with self.assertRaisesRegex(RuntimeEvidenceError,"TRANSACTIONAL"):
   review(db)
 def test_unrecognized_rows(self):
  with self.assertRaisesRegex(RuntimeEvidenceError,"ROW_INVALID"):
   review(Database(),orders=["secret"])
 def test_only_pg_select(self):
  db=Database()
  r=review(db)
  self.assertEqual(db.queries,1)
  self.assertFalse(r["databaseMutated"])
 def test_no_broker_order_transport_reference(self):
  from pathlib import Path
  for file in ["aws_runtime_evidence_v22.py","aws_runtime_evidence_cli_v22.py"]:
   s=Path(__file__).with_name(file).read_text()
   self.assertNotIn("angel_execution_transport",s)
   self.assertNotIn("placeOrder",s)
   self.assertNotIn("cancelOrder",s)

if __name__=="__main__":unittest.main()
