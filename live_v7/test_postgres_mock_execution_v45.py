"""V45 staging PostgreSQL transaction protocol tests; no real DB/network."""
import unittest
from datetime import datetime,timezone
from pathlib import Path
from live_v7.postgres_mock_execution_v45 import (
    mock_reserve,mock_seal_unknown,StageReservationBlocked,validate_intent
)
OWNER="11111111-1111-4111-8111-111111111111"
NOW=datetime(2026,11,26,9,tzinfo=timezone.utc)
ORDER={"symbol":"NIFTY29DEC2629000CE","token":"38158","side":"SELL",
       "order_type":"LIMIT","quantity":65,"price":"10.50"}

class FakeCursor:
    def __init__(self,db): self.db=db; self.last=None
    def __enter__(self):return self
    def __exit__(self,*args):return False
    def execute(self,sql,args=()):
        self.db.sql.append((sql,args))
        if "FROM optionx_exec_stage.guard" in sql:
            self.last=self.db.guard
        elif "SELECT payload_hash,state FROM optionx_exec_stage.order_intents" in sql:
            self.last=self.db.rows.get((args[0],args[1]))
        elif "SELECT state FROM optionx_exec_stage.order_intents" in sql:
            rec=self.db.rows.get((args[0],args[1]))
            self.last=None if rec is None else (rec[1],)
        elif "INSERT INTO optionx_exec_stage.order_intents" in sql:
            self.db.pending["insert"]=((args[0],args[1]),(args[2],"RESERVED_UNSENT"))
        elif "SET state='MAY_HAVE_SENT_RECONCILE'" in sql:
            key=(args[0],args[1])
            existing=self.db.rows.get(key)
            if existing: self.db.pending["update"]=(key,(existing[0],"MAY_HAVE_SENT_RECONCILE"))
        elif "INSERT INTO optionx_exec_stage.order_events" in sql:
            self.db.pending.setdefault("events",0)
            self.db.pending["events"]+=1
    def fetchone(self): return self.last

class FakePg:
    autocommit=False
    def __init__(self,guard=("MOCK_ONLY",True)):
        self.guard=guard; self.rows={}; self.pending={}; self.sql=[]
        self.commits=0; self.rollbacks=0; self.events=0
    def cursor(self):return FakeCursor(self)
    def commit(self):
        if "insert" in self.pending:
            key,row=self.pending["insert"];self.rows[key]=row
        if "update" in self.pending:
            key,row=self.pending["update"];self.rows[key]=row
        self.events+=self.pending.get("events",0)
        self.pending={};self.commits+=1
    def rollback(self):
        self.pending={};self.rollbacks+=1

class StagePgIntegrationTests(unittest.TestCase):
    def setUp(self): self.db=FakePg()
    def reserve(self,**kw):
        return mock_reserve(self.db,owner_id=kw.get("owner",OWNER),
            intent_key=kw.get("key","V45KEY_1234"),intent=kw.get("order",ORDER),now=NOW)
    def test_mock_only_reserve_commits_once(self):
        r=self.reserve()
        self.assertEqual(r["result"],"STAGING_RESERVED_NO_SEND")
        self.assertEqual(self.db.commits,1)
        self.assertEqual(self.db.events,1)
        self.assertFalse(r["canSubmitOrder"])
    def test_replay_does_not_duplicate(self):
        self.reserve()
        r=self.reserve()
        self.assertEqual(r["result"],"EXISTING_NO_RESEND")
        self.assertEqual(self.db.events,1)
    def test_closed_guard_default_denies(self):
        self.db.guard=("STOPPED",True)
        with self.assertRaisesRegex(StageReservationBlocked,"STAGING_MOCK_GUARD_NOT_ENABLED"):self.reserve()
        self.assertEqual(self.db.rollbacks,1)
    def test_missing_guard_denies(self):
        self.db.guard=None
        with self.assertRaises(StageReservationBlocked):self.reserve()
    def test_running_guard_denies(self):
        self.db.guard=("RUNNING",False)
        with self.assertRaises(StageReservationBlocked):self.reserve()
    def test_unknown_seal_is_permanent(self):
        self.reserve()
        r=mock_seal_unknown(self.db,owner_id=OWNER,intent_key="V45KEY_1234")
        self.assertEqual(r["state"],"MAY_HAVE_SENT_RECONCILE")
        self.assertEqual(self.db.events,2)
        self.assertFalse(r["canRetry"])
    def test_duplicate_seal_no_new_event(self):
        self.reserve()
        for _ in range(2): mock_seal_unknown(self.db,owner_id=OWNER,intent_key="V45KEY_1234")
        self.assertEqual(self.db.events,2)
    def test_seal_without_reservation_denied(self):
        with self.assertRaisesRegex(StageReservationBlocked,"RESERVATION_NOT_FOUND"):
            mock_seal_unknown(self.db,owner_id=OWNER,intent_key="V45KEY_1234")
    def test_seal_guard_stopped_denied(self):
        self.reserve()
        self.db.guard=("STOPPED",True)
        with self.assertRaises(StageReservationBlocked):
            mock_seal_unknown(self.db,owner_id=OWNER,intent_key="V45KEY_1234")
    def test_key_collision_conflicting_order(self):
        self.reserve()
        alt=dict(ORDER,price="11.00")
        with self.assertRaisesRegex(StageReservationBlocked,"KEY_CONFLICT_DIFFERENT_ORDER"):
            self.reserve(order=alt)
    def test_no_autocommit_allowed(self):
        self.db.autocommit=True
        with self.assertRaisesRegex(StageReservationBlocked,"TRANSACTIONAL_CONNECTION_REQUIRED"):
            self.reserve()
    def test_owner_invalid(self):
        with self.assertRaisesRegex(StageReservationBlocked,"OWNER_INVALID"):
            self.reserve(owner="invalid")
    def test_bad_quantity(self):
        with self.assertRaisesRegex(StageReservationBlocked,"QUANTITY_INVALID"):
            self.reserve(order=dict(ORDER,quantity=True))
    def test_private_fields_rejected(self):
        with self.assertRaisesRegex(StageReservationBlocked,"INTENT_SHAPE_INVALID"):
            self.reserve(order=dict(ORDER,jwt="SECRET"))
    def test_sql_guard_lock_before_insert(self):
        self.reserve()
        sql=" ".join(q for q,_ in self.db.sql)
        self.assertLess(sql.index("FROM optionx_exec_stage.guard"),sql.index("INSERT INTO optionx_exec_stage.order_intents"))
        self.assertIn("FOR UPDATE",sql)
    def test_no_order_transport_called(self):
        source=Path(__file__).with_name("postgres_mock_execution_v45.py").read_text()
        for banned in ("placeOrder","cancelOrder","angel_gateway","urllib.request","requests.post"):
            self.assertNotIn(banned,source)
    def test_db_migration_stopped_default_and_never_running(self):
        root=Path(__file__).resolve().parent.parent
        migration=(root/"migrations/staging/optionx_v45_execution_stage.sql").read_text()
        self.assertIn("DEFAULT 'STOPPED'",migration)
        self.assertIn("CHECK (state IN ('STOPPED','MOCK_ONLY'))",migration)
        self.assertNotIn("CREATE SCHEMA IF NOT EXISTS optionx_private",migration)
if __name__=="__main__":unittest.main()
