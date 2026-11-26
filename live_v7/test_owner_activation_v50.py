"""V50 durable owner activation tests (isolated offline-only)."""
import tempfile
import unittest
from datetime import datetime,timezone,timedelta
from pathlib import Path
from live_v7.owner_activation_v50 import (
 CHECKS,ActivationDenied,create_store,eligibility,arm,stop,state
)
OWNER="11111111-1111-4111-8111-111111111111"
OTHER="22222222-2222-4222-8222-222222222222"
NOW=datetime(2026,11,26,9,0,tzinfo=timezone.utc)
ALL={k:True for k in CHECKS}

class ActivationTests(unittest.TestCase):
 def setUp(self):
    self.tmp=tempfile.TemporaryDirectory()
    p=Path(self.tmp.name)/"private";p.mkdir(mode=0o700)
    self.path=p/"activation.sqlite"
    self.db=create_store(self.path)
 def tearDown(self):
    self.db.close();self.tmp.cleanup()
 def activate(self,**kw):
    return arm(self.db,owner_id=kw.get("owner_id",OWNER),
      owner_verified=kw.get("owner_verified",True),
      server_evidence=kw.get("server_evidence",ALL),
      now=kw.get("now",NOW),
      transport_is_source_locked=kw.get("locked",True))
 def test_default_stopped(self):
    self.assertEqual(state(self.db,owner_id=OWNER,now=NOW)["state"],"STOPPED")
 def test_source_lock_prevents_arm_even_with_all_checks(self):
    with self.assertRaisesRegex(ActivationDenied,"ANGEL_SOURCE_LOCK_STILL_ACTIVE"):
      self.activate()
    self.assertEqual(state(self.db,owner_id=OWNER,now=NOW)["state"],"STOPPED")
 def test_missing_one_check_denied(self):
    partial=dict(ALL,broker_write_transport_certified=False)
    with self.assertRaisesRegex(ActivationDenied,"broker_write_transport_certified"):
      self.activate(server_evidence=partial,locked=False)
 def test_all_missing_fail_closed(self):
    self.assertEqual(len(eligibility(evidence={},owner_verified=True,now=NOW)["blockers"]),len(CHECKS))
 def test_unverified_owner_cannot_arm(self):
    with self.assertRaisesRegex(ActivationDenied,"OWNER_VERIFICATION_REQUIRED"):
      self.activate(owner_verified=False,locked=False)
 def test_short_lease_with_all_internal_proofs(self):
    result=self.activate(locked=False)
    self.assertEqual(result["state"],"ARMED")
    self.assertFalse(result["canSubmitOrder"])
    self.assertEqual(state(self.db,owner_id=OWNER,now=NOW)["state"],"ARMED")
 def test_expiry_fails_closed(self):
    self.activate(locked=False)
    self.assertEqual(state(self.db,owner_id=OWNER,now=NOW+timedelta(minutes=16))["state"],"STOPPED")
 def test_expiry_boundary(self):
    self.activate(locked=False)
    self.assertEqual(state(self.db,owner_id=OWNER,now=NOW+timedelta(minutes=15))["state"],"STOPPED")
 def test_stop_preempts_lease(self):
    self.activate(locked=False)
    stop(self.db,owner_id=OWNER,owner_verified=True,now=NOW)
    self.assertEqual(state(self.db,owner_id=OWNER,now=NOW)["state"],"STOPPED")
 def test_stop_persists_restart(self):
    self.activate(locked=False)
    stop(self.db,owner_id=OWNER,owner_verified=True,now=NOW)
    self.db.close();self.db=create_store(self.path)
    self.assertEqual(state(self.db,owner_id=OWNER,now=NOW)["state"],"STOPPED")
 def test_lease_persists_restart_until_expiry(self):
    self.activate(locked=False)
    self.db.close();self.db=create_store(self.path)
    self.assertEqual(state(self.db,owner_id=OWNER,now=NOW)["state"],"ARMED")
 def test_wrong_owner_is_stopped(self):
    self.activate(locked=False)
    self.assertEqual(state(self.db,owner_id=OTHER,now=NOW)["state"],"STOPPED")
 def test_unauthorized_stop_denied(self):
    with self.assertRaises(ActivationDenied):
      stop(self.db,owner_id=OWNER,owner_verified=False,now=NOW)
 def test_private_database(self):
    self.assertEqual(self.path.stat().st_mode&0o777,0o600)
 def test_public_directory_rejected(self):
    p=Path(self.tmp.name)/"bad";p.mkdir(mode=0o700);p.chmod(0o755)
    try:
      with self.assertRaisesRegex(ActivationDenied,"PRIVATE_DIRECTORY_PERMISSIONS"):
        create_store(p/"store.db")
    finally:p.chmod(0o700)
 def test_audit_transitions(self):
    self.activate(locked=False)
    stop(self.db,owner_id=OWNER,owner_verified=True,now=NOW)
    self.assertEqual(self.db.execute("SELECT COUNT(*) FROM activation_audit").fetchone()[0],2)
 def test_no_broker_order_transport(self):
    s=Path(__file__).with_name("owner_activation_v50.py").read_text()
    for bad in ("placeOrder","cancelOrder","urllib.request","angel_gateway","requests.post"):
      self.assertNotIn(bad,s)
 def test_unknown_evidence_key_denied(self):
    checks=dict(ALL);checks["browserSaysUnlock"]=True
    with self.assertRaisesRegex(ActivationDenied,"PREREQUISITES_NOT_CERTIFIED"):
      self.activate(server_evidence=checks,locked=False)
 def test_cannot_submit_after_armed(self):
    self.activate(locked=False)
    self.assertFalse(state(self.db,owner_id=OWNER,now=NOW)["canSubmitOrder"])
 def test_non_uuid_denied(self):
    with self.assertRaises(ActivationDenied):
      state(self.db,owner_id="invalid",now=NOW)

if __name__=="__main__":unittest.main()
