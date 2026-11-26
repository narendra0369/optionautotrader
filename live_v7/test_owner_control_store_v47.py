"""V47 durable owner control tests: private persistence and fail-closed state."""
import sqlite3
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from live_v7.owner_control_store_v47 import (
    ControlBlocked,open_control_store,request_unlock_review,emergency_stop,read_state
)
OWNER="11111111-1111-4111-8111-111111111111"
OTHER="22222222-2222-4222-8222-222222222222"
NOW=datetime(2026,11,26,9,0,tzinfo=timezone.utc)

class V47OwnerControlTests(unittest.TestCase):
 def setUp(self):
    self.temp=tempfile.TemporaryDirectory()
    self.private=Path(self.temp.name)/"private"
    self.private.mkdir(mode=0o700)
    self.dbpath=self.private/"control.sqlite3"
    self.db=open_control_store(self.dbpath)
 def tearDown(self):
    self.db.close();self.temp.cleanup()
 def request(self,owner=OWNER,verified=True):
    return request_unlock_review(self.db,owner_id=owner,owner_verified=verified,when=NOW)
 def stop(self,owner=OWNER,verified=True):
    return emergency_stop(self.db,owner_id=owner,owner_verified=verified,when=NOW)
 def test_default_stopped(self):
    self.assertEqual(read_state(self.db,owner_id=OWNER)["mode"],"STOPPED")
 def test_owner_request_is_not_armed(self):
    r=self.request()
    self.assertTrue(r["stopPersisted"])
    self.assertFalse(r["liveOrdersEnabled"])
    self.assertEqual(r["mode"],"REVIEW_REQUESTED")
 def test_review_survives_restart(self):
    self.request()
    self.db.close();self.db=open_control_store(self.dbpath)
    r=read_state(self.db,owner_id=OWNER)
    self.assertEqual(r["mode"],"REVIEW_REQUESTED")
    self.assertFalse(r["canSubmitOrder"])
 def test_stop_survives_restart(self):
    self.request()
    self.stop()
    self.db.close();self.db=open_control_store(self.dbpath)
    self.assertEqual(read_state(self.db,owner_id=OWNER)["mode"],"STOPPED")
 def test_unverified_cannot_request(self):
    with self.assertRaisesRegex(ControlBlocked,"VERIFIED_OWNER_REQUIRED"):
        self.request(verified=False)
 def test_unverified_cannot_stop_other_owner(self):
    with self.assertRaisesRegex(ControlBlocked,"VERIFIED_OWNER_REQUIRED"):
        self.stop(owner=OTHER,verified=False)
 def test_other_owner_isolated(self):
    self.request()
    self.assertEqual(read_state(self.db,owner_id=OTHER)["mode"],"STOPPED")
 def test_audit_events_recorded(self):
    self.request();self.stop()
    self.assertEqual(self.db.execute("SELECT COUNT(*) FROM control_audit").fetchone()[0],3)
 def test_duplicate_review_never_enables(self):
    for _ in range(3): self.request()
    self.assertEqual(read_state(self.db,owner_id=OWNER)["mode"],"REVIEW_REQUESTED")
    self.assertEqual(self.db.execute("SELECT COUNT(*) FROM owner_control").fetchone()[0],1)
 def test_file_private(self):
    self.assertEqual(self.dbpath.stat().st_mode & 0o777,0o600)
 def test_public_dir_rejected(self):
    public=Path(self.temp.name)/"public"
    public.mkdir(mode=0o700);public.chmod(0o755)
    try:
        with self.assertRaisesRegex(ControlBlocked,"PRIVATE_DIRECTORY_PERMISSIONS"):
            open_control_store(public/"state.db")
    finally: public.chmod(0o700)
 def test_relative_file_rejected(self):
    with self.assertRaisesRegex(ControlBlocked,"ABSOLUTE_PRIVATE_DB_REQUIRED"):
        open_control_store("control.sqlite3")
 def test_symlink_rejected(self):
    link=self.private/"alias.db"
    link.symlink_to(self.dbpath)
    with self.assertRaisesRegex(ControlBlocked,"ABSOLUTE_PRIVATE_DB_REQUIRED"):
        open_control_store(link)
 def test_invalid_owner_rejected(self):
    with self.assertRaisesRegex(ControlBlocked,"OWNER_ID_INVALID"):
        read_state(self.db,owner_id="not-a-uuid")
 def test_no_order_transport(self):
    src=Path(__file__).with_name("owner_control_store_v47.py").read_text()
    for unsafe in ("placeOrder","cancelOrder","modifyOrder","angel_gateway","urllib.request","psycopg"):
        self.assertNotIn(unsafe,src)
 def test_control_state_not_live_flag(self):
    for r in (self.request(),self.stop()):
        self.assertFalse(r["canSubmitOrder"])
        self.assertFalse(r["realOrderSent"])

if __name__=="__main__":unittest.main()
