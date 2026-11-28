"""V19 no-network PostgreSQL/Angel reconciliation safety tests."""
import unittest
from datetime import datetime,timezone,timedelta
from unittest.mock import patch
from live_v7.aws_pg_recovery_v19 import read_recovery,PostgresRecoveryError

OWNER="11111111-1111-4111-8111-111111111111"
NOW=datetime(2026,11,25,9,0,tzinfo=timezone.utc)

def snapshot(orders=None,positions=None,status=True):
 return {"allReadsSucceeded":status,"broker":"Angel","books":{
    "orderbook":{"orders":orders if orders is not None else []},
    "tradebook":{"tradeRows":0,"fillsBrokerVerified":False,"reconciliationPending":True},
    "positions":{"positions":positions if positions is not None else []}}}

class Cursor:
 def __init__(self,db):
  self.db=db; self.kind=None
 def __enter__(self):return self
 def __exit__(self,*exc):return False
 def execute(self,sql,params):
  self.db.sql.append(sql)
  self.db.params.append(params)
  assert "optionx_private." in sql
  if "engine_guard" in sql:self.kind="guard"
  elif "order_intents" in sql:self.kind="intents"
  elif "position_protection" in sql:self.kind="stops"
  else:raise AssertionError("Unexpected SQL")
 def fetchone(self):
  assert self.kind=="guard"
  return self.db.guard
 def fetchall(self):
  return self.db.intents if self.kind=="intents" else self.db.stops

class FakeDB:
 autocommit=False
 def __init__(self,guard=None,intents=None,stops=None):
  self.guard=guard;self.intents=intents if intents is not None else []
  self.stops=stops if stops is not None else []
  self.sql=[];self.params=[]
 def cursor(self):return Cursor(self)

def call(db,s=None,**kw):
 return read_recovery(db,verified_owner_id=OWNER,
   owner_authenticated=kw.get("owner_authenticated",True),
   broker_authenticated=kw.get("broker_authenticated",True),
   snapshot=s if s is not None else snapshot(),
   snapshot_at=kw.get("snapshot_at",NOW),now=NOW)

class V19PostgresRecoveryTests(unittest.TestCase):
 def test_empty_ledger_and_books_remain_locked(self):
  db=FakeDB()
  r=call(db)
  self.assertTrue(r["ledgerConnected"])
  self.assertEqual(r["engineGuard"],"ABSENT_DEFAULT_DENY")
  self.assertFalse(r["liveOrdersEnabled"])
  self.assertFalse(r["databaseMutated"])
  self.assertFalse(r["canSubmitOrder"])
  self.assertTrue(all(x.lstrip().startswith("SELECT") for x in db.sql))
 def test_existing_stop_guard_denies(self):
  r=call(FakeDB(guard=("STOPPED",True)))
  self.assertEqual(r["engineGuard"],"STOPPED")
 def test_running_guard_rejected(self):
  with self.assertRaisesRegex(PostgresRecoveryError,"GUARD"):
   call(FakeDB(guard=("RUNNING",False)))
 def test_owner_must_be_authenticated(self):
  db=FakeDB()
  with self.assertRaisesRegex(PostgresRecoveryError,"AUTH"):
   call(db,owner_authenticated=False)
  self.assertFalse(db.sql)
 def test_broker_must_be_authenticated(self):
  with self.assertRaisesRegex(PostgresRecoveryError,"AUTH"):
   call(FakeDB(),broker_authenticated=False)
 def test_stale_broker_data_denied(self):
  with self.assertRaisesRegex(PostgresRecoveryError,"STALE"):
   call(FakeDB(),snapshot_at=NOW-timedelta(seconds=11))
 def test_manual_order_not_adopted(self):
  order={"order_id":"manual111","symbol":"NIFTY29DEC2629000CE",
         "quantity":65,"filled_quantity":65,"status":"COMPLETE"}
  s=snapshot(orders=[order])
  r=call(FakeDB(),s)
  self.assertEqual(r["manualOrUntrackedOrderCount"],1)
  self.assertIn("MANUAL_OR_UNTRACKED_BROKER_ORDER",r["blockedReasons"])
  self.assertFalse(r["manualPositionModified"])
 def test_manual_position_never_adopted(self):
  pos={"symbol":"NIFTY29DEC2629000CE","net_quantity":65}
  r=call(FakeDB(),snapshot(positions=[pos]))
  self.assertEqual(r["positionsWithExposure"],1)
  self.assertIn("ACCOUNT_POSITION_OWNERSHIP_UNRESOLVED",r["blockedReasons"])
 def test_missing_owned_broker_order_denied(self):
  db=FakeDB(intents=[("owned123", "NIFTY29DEC2629000CE",65,0,"AWAITING_BROKER_ACK")])
  r=call(db)
  self.assertIn("OWNED_BROKER_ORDER_NOT_FOUND",r["blockedReasons"])
  self.assertIn("UNRESOLVED_OWNED_ENTRY",r["blockedReasons"])
 def test_owned_fill_discrepancy_denied(self):
  db=FakeDB(intents=[("owned123","NIFTY29DEC2629000CE",65,0,"PARTIALLY_FILLED")])
  order={"order_id":"owned123","symbol":"NIFTY29DEC2629000CE",
         "quantity":65,"filled_quantity":25,"status":"PARTIALLY_FILLED"}
  r=call(db,snapshot(orders=[order]))
  self.assertIn("BROKER_LEDGER_ORDER_DISCREPANCY",r["blockedReasons"])
 def test_stop_cannot_be_inferred_from_database_ack_alone(self):
  db=FakeDB(stops=[("stop123",65,65,"STOP_ACKED")])
  r=call(db)
  self.assertIn("PROTECTIVE_STOP_NOT_BROKER_CONFIRMED_NOW",r["blockedReasons"])
 def test_unknown_broker_order_blocks_without_any_sql(self):
  db=FakeDB()
  bad={"order_id":"manual111","symbol":"NIFTY29DEC2629000CE",
       "quantity":65,"filled_quantity":0,"status":"UNKNOWN"}
  with self.assertRaisesRegex(PostgresRecoveryError,"STATUS_UNKNOWN"):
   call(db,snapshot(orders=[bad]))
  self.assertFalse(db.sql)
 def test_malformed_book_blocks(self):
  with self.assertRaisesRegex(PostgresRecoveryError,"SNAPSHOT_REQUIRED"):
   call(FakeDB(),{"allReadsSucceeded":False,"broker":"Angel"})
 def test_nontransactional_db_denied(self):
  db=FakeDB();db.autocommit=True
  with self.assertRaisesRegex(PostgresRecoveryError,"TRANSACTIONAL"):
   call(db)
 def test_no_broker_transport_import_or_sql_write(self):
  from pathlib import Path
  s=Path(__file__).with_name("aws_pg_recovery_v19.py").read_text()
  self.assertNotIn("angel_execution_transport",s)
  self.assertNotIn("placeOrder",s)
  self.assertNotIn("cursor.execute(\"INSERT",s)
  self.assertNotIn("UPDATE optionx_private",s)
 def test_driver_connect_forces_tls_verify_full(self):
  from live_v7.aws_pg_recovery_cli_v19 import connect_postgres
  class Driver:
   args=None
   @staticmethod
   def connect(uri,**kw):
    Driver.args=kw
    return FakeDB()
  with patch("sys.stdin.isatty",return_value=True),patch("sys.stdout.isatty",return_value=True),patch("os.geteuid",return_value=1000):
   db=connect_postgres(prompt=lambda x:"postgresql://user:secret@localhost:5432/postgres",driver=Driver)
  self.assertEqual(Driver.args["sslmode"],"verify-full")
  self.assertFalse(db.autocommit)
 def test_private_tty_required(self):
  from live_v7.aws_pg_recovery_cli_v19 import connect_postgres
  with patch("sys.stdin.isatty",return_value=False):
   with self.assertRaisesRegex(ValueError,"PRIVATE_NONROOT"):
    connect_postgres(prompt=lambda _: "fake")
 def test_no_postgres_uri_in_argv_or_env(self):
  from pathlib import Path
  s=Path(__file__).with_name("aws_pg_recovery_cli_v19.py").read_text()
  self.assertNotIn("argparse",s)
  self.assertNotIn("DATABASE_URL",s)
  self.assertNotIn("OPTIONX_DB_PASSWORD",s)

if __name__=="__main__":unittest.main()
