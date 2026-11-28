"""No-network AWS shadow observer and durable diagnostic journal checks."""
import json
import os
from pathlib import Path
import sqlite3
import tempfile
import unittest
from datetime import datetime,timezone

from live_v7.aws_shadow_observer import open_observer, observe, audit_chain, ObserverError

NOW=datetime(2026,11,25,6,0,tzinfo=timezone.utc)

def snapshot(*, orders=None, positions=None, trade_verified=False, all_reads=True):
    return {"allReadsSucceeded":all_reads,
      "books":{
        "orderbook":{"orders":orders if orders is not None else []},
        "tradebook":{"tradeRows":0,"fillsBrokerVerified":trade_verified,
                     "reconciliationPending":not trade_verified},
        "positions":{"positions":positions if positions is not None else []}}}

class AwsShadowObserverTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.db=Path(self.tmp.name)/"observer.sqlite3"
        self.conn=open_observer(self.db)
    def tearDown(self):
        self.conn.close()
        self.tmp.cleanup()
    def test_empty_books_never_enable_trading(self):
        r=observe(self.conn,snapshot=snapshot(),trusted_source=True,observed_at=NOW)
        self.assertFalse(r["canSubmitOrder"])
        self.assertFalse(r["liveOrdersEnabled"])
        self.assertTrue(r["newEntriesBlocked"])
        self.assertIn("AUTHORITATIVE_POSTGRES_LEDGER_NOT_CONNECTED",r["blocks"])
        self.assertIn("TRADEBOOK_FILL_NOT_VERIFIED",r["blocks"])
        self.assertTrue(audit_chain(self.conn))
    def test_existing_position_blocks_even_when_tradebook_claimed_verified(self):
        s=snapshot(positions=[{"symbol":"NIFTY29DEC2629000CE","net_quantity":65}],trade_verified=True)
        r=observe(self.conn,snapshot=s,trusted_source=True,observed_at=NOW)
        self.assertTrue(r["newEntriesBlocked"])
        self.assertIn("LIVE_EXECUTION_WORKER_NOT_CERTIFIED",r["blocks"])
        self.assertEqual(r["positionsObserved"],1)
    def test_untracked_order_blocks(self):
        o={"order_id":"order_111","symbol":"NIFTY29DEC2629000CE","side":"BUY",
           "quantity":65,"filled_quantity":65,"status":"COMPLETE"}
        r=observe(self.conn,snapshot=snapshot(orders=[o]),trusted_source=True,observed_at=NOW)
        self.assertTrue(r["newEntriesBlocked"])
        self.assertIn("UNTRACKED_BROKER_ORDERS_REQUIRE_REVIEW",r["blocks"])
    def test_unknown_broker_order_fails_closed(self):
        o={"order_id":"order_111","symbol":"NIFTY29DEC2629000CE","side":"SELL",
           "quantity":65,"filled_quantity":0,"status":"UNKNOWN"}
        r=observe(self.conn,snapshot=snapshot(orders=[o]),trusted_source=True,observed_at=NOW)
        self.assertIn("UNKNOWN_BROKER_ORDER_STATUS",r["blocks"])
    def test_unauthenticated_source_fails_closed(self):
        r=observe(self.conn,snapshot=snapshot(),trusted_source=False,observed_at=NOW)
        self.assertIn("BROKER_SOURCE_NOT_AUTHENTICATED",r["blocks"])
    def test_incomplete_broker_book_blocks(self):
        r=observe(self.conn,snapshot=snapshot(all_reads=False),trusted_source=True,observed_at=NOW)
        self.assertIn("BROKER_BOOK_READ_INCOMPLETE",r["blocks"])
    def test_no_broker_secrets_or_position_symbols_persisted(self):
        s=snapshot(positions=[{"symbol":"NIFTY29DEC2629000CE","net_quantity":65}])
        observe(self.conn,snapshot=s,trusted_source=True,observed_at=NOW)
        stored=str(self.conn.execute("SELECT * FROM observations").fetchall())
        self.assertNotIn("NIFTY29DEC2629000CE",stored)
        self.assertNotIn("jwt",stored)
        self.assertEqual(self.conn.execute("SELECT new_entries_blocked FROM observations").fetchone()[0],1)
    def test_db_append_only(self):
        observe(self.conn,snapshot=snapshot(),trusted_source=True,observed_at=NOW)
        with self.assertRaises(sqlite3.IntegrityError):
            self.conn.execute("UPDATE observations SET new_entries_blocked=0")
        with self.assertRaises(sqlite3.IntegrityError):
            self.conn.execute("DELETE FROM observations")
    def test_chain_two_observations(self):
        observe(self.conn,snapshot=snapshot(),trusted_source=True,observed_at=NOW)
        later=NOW.replace(minute=1)
        observe(self.conn,snapshot=snapshot(),trusted_source=True,observed_at=later)
        self.assertTrue(audit_chain(self.conn))
    def test_missing_books_error(self):
        with self.assertRaisesRegex(ObserverError,"ALL_THREE_BOOKS"):
            observe(self.conn,snapshot={"books":{"orderbook":{}}},trusted_source=True,observed_at=NOW)
    def test_relative_path_rejected(self):
        with self.assertRaisesRegex(ObserverError,"ABSOLUTE_PRIVATE_PATH"):
            open_observer("data.db")
    def test_existing_permissive_file_rejected(self):
        self.conn.close()
        os.chmod(self.db,0o644)
        with self.assertRaisesRegex(ObserverError,"PERMISSIONS_UNSAFE"):
            open_observer(self.db)
        os.chmod(self.db,0o600)
        self.conn=open_observer(self.db)

if __name__=="__main__":
    unittest.main()
