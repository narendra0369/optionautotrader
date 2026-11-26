"""V48 HMAC/nonce owner-command integration tests (no network, no live order)."""
import tempfile
import unittest
from datetime import datetime,timezone,timedelta
from pathlib import Path
from live_v7.owner_control_store_v47 import open_control_store,read_state
from live_v7.signed_owner_commands_v48 import (
 sign_from_trusted_gateway,apply_signed_command,CommandRejected)
OWNER="11111111-1111-4111-8111-111111111111"
OTHER="22222222-2222-4222-8222-222222222222"
KEY=b"v48-secret-is-not-real-test-key-0123456789abcdef"
NOW=datetime(2026,11,26,9,0,tzinfo=timezone.utc)
def payload(action="REQUEST_UNLOCK_REVIEW",nonce="nonce-0000000000000001",when=NOW):
 return {"v":1,"owner":OWNER,"action":action,"nonce":nonce,"issued_at":int(when.timestamp())}

class SignedOwnerCommandsTests(unittest.TestCase):
 def setUp(self):
    self.tmp=tempfile.TemporaryDirectory()
    private=Path(self.tmp.name)/"private";private.mkdir(mode=0o700)
    self.path=private/"ctrl.db"
    self.db=open_control_store(self.path)
 def tearDown(self):self.db.close();self.tmp.cleanup()
 def send(self,p=None,key=KEY,sig=None,now=NOW,expected=OWNER):
    p=p or payload()
    if sig is None:sig=sign_from_trusted_gateway(p,key=key,owner_verified=True)
    return apply_signed_command(self.db,data=p,signature=sig,key=key,
                                expected_owner=expected,now=now)
 def test_review_persisted_but_not_live(self):
    r=self.send()
    self.assertTrue(r["commandAccepted"])
    self.assertEqual(r["mode"],"REVIEW_REQUESTED")
    self.assertFalse(r["liveOrdersEnabled"])
 def test_stop_persists(self):
    self.send()
    r=self.send(payload("EMERGENCY_STOP",nonce="nonce-0000000000000002"))
    self.assertEqual(r["mode"],"STOPPED")
    self.assertEqual(read_state(self.db,owner_id=OWNER)["mode"],"STOPPED")
 def test_restart_persists_nonce_and_stop(self):
    p=payload("EMERGENCY_STOP")
    self.send(p)
    self.db.close()
    self.db=open_control_store(self.path)
    with self.assertRaisesRegex(CommandRejected,"REPLAYED"):
       self.send(p)
    self.assertEqual(read_state(self.db,owner_id=OWNER)["mode"],"STOPPED")
 def test_duplicate_nonce_blocked(self):
    p=payload();self.send(p)
    with self.assertRaisesRegex(CommandRejected,"REPLAYED"):self.send(p)
 def test_modified_action_signature_rejected(self):
    p=payload();sig=sign_from_trusted_gateway(p,key=KEY,owner_verified=True)
    with self.assertRaisesRegex(CommandRejected,"SIGNATURE_MISMATCH"):
       self.send(payload("EMERGENCY_STOP"),sig=sig)
 def test_wrong_owner_rejected(self):
    with self.assertRaisesRegex(CommandRejected,"COMMAND_OWNER_MISMATCH"):
       self.send(expected=OTHER)
 def test_wrong_key_rejected(self):
    p=payload();sig=sign_from_trusted_gateway(p,key=KEY,owner_verified=True)
    with self.assertRaisesRegex(CommandRejected,"SIGNATURE_MISMATCH"):
       self.send(p,key=b"another-long-separate-test-key-abcdefghijklmnopqrstuvwxyz",sig=sig)
 def test_old_command_rejected(self):
    p=payload(when=NOW-timedelta(seconds=31))
    with self.assertRaisesRegex(CommandRejected,"COMMAND_STALE_OR_FUTURE"):self.send(p)
 def test_future_command_rejected(self):
    p=payload(when=NOW+timedelta(seconds=31))
    with self.assertRaisesRegex(CommandRejected,"COMMAND_STALE_OR_FUTURE"):self.send(p)
 def test_unsupported_start_blocked(self):
    with self.assertRaisesRegex(CommandRejected,"COMMAND_ACTION_NOT_PERMITTED"):
       self.send(payload("START_REAL_TRADING"))
 def test_unknown_browser_toggle_blocked(self):
    p=dict(payload(),unlock=True)
    with self.assertRaisesRegex(CommandRejected,"COMMAND_FIELDS_INVALID"):self.send(p)
 def test_unsigned_request_blocked(self):
    with self.assertRaisesRegex(CommandRejected,"SIGNATURE_INVALID"):self.send(sig="")
 def test_unverified_gateway_cannot_sign(self):
    with self.assertRaisesRegex(CommandRejected,"TRUSTED_GATEWAY_OWNER_VERIFICATION_REQUIRED"):
       sign_from_trusted_gateway(payload(),key=KEY,owner_verified=False)
 def test_weak_key_blocked(self):
    with self.assertRaisesRegex(CommandRejected,"STRONG_SERVER_KEY_REQUIRED"):
       self.send(key=b"weak")
 def test_nonces_unique_across_actions(self):
    self.send()
    with self.assertRaisesRegex(CommandRejected,"REPLAYED"):
       self.send(payload("EMERGENCY_STOP"))
 def test_no_real_broker_activity(self):
    self.send()
    src=(Path(__file__).with_name("signed_owner_commands_v48.py")).read_text()
    for bad in ("placeOrder","cancelOrder","modifyOrder","angel_gateway","urllib.request","requests.post"):
       self.assertNotIn(bad,src)
 def test_absent_state_defaults_stop(self):
    self.assertEqual(read_state(self.db,owner_id=OWNER)["mode"],"STOPPED")

if __name__=="__main__":unittest.main()
