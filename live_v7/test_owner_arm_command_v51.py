"""V51 signed website activation request and server-side gate tests.
Offline only: all mock requests must remain blocked until broker certified.
"""
import tempfile
import unittest
from datetime import datetime, timezone, timedelta
from pathlib import Path

from live_v7.owner_activation_v50 import create_store, state
from live_v7.signed_owner_commands_v48 import sign_from_trusted_gateway, CommandRejected
from live_v7.owner_arm_command_v51 import attempt_activation

OWNER="11111111-1111-4111-8111-111111111111"
OTHER="22222222-2222-4222-8222-222222222222"
KEY=b"local-unit-test-only-secret-000000000000000000"
NOW=datetime(2026,11,26,9,0,tzinfo=timezone.utc)
ROOT=Path(__file__).resolve().parent.parent

def packet(nonce="v51nonce_0123456789abcdef",when=NOW):
    return {"v":1,"owner":OWNER,"action":"REQUEST_ACTIVATE_LIVE",
            "nonce":nonce,"issued_at":int(when.timestamp())}

class V51ActivationTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        folder=Path(self.tmp.name)/"private";folder.mkdir(mode=0o700)
        self.path=folder/"activation.db"
        self.db=create_store(self.path)
    def tearDown(self):
        self.db.close();self.tmp.cleanup()
    def send(self,data=None,signature=None,expected_owner=OWNER,now=NOW,key=KEY):
        data=packet() if data is None else data
        if signature is None:
            signature=sign_from_trusted_gateway(data,key=KEY,owner_verified=True)
        return attempt_activation(self.db,data=data,signature=signature,
                 key=key,expected_owner=expected_owner,now=now)
    def test_signed_owner_click_fail_closed(self):
        r=self.send()
        self.assertEqual(r["state"],"BLOCKED")
        self.assertTrue(r["commandReceived"])
        self.assertFalse(r["liveOrdersEnabled"])
    def test_activation_db_stopped(self):
        self.send()
        self.assertEqual(state(self.db,owner_id=OWNER,now=NOW)["state"],"STOPPED")
    def test_replayed_click_rejected(self):
        self.send()
        with self.assertRaisesRegex(CommandRejected,"ALREADY_USED"):
            self.send()
    def test_replay_survives_restart(self):
        self.send()
        self.db.close();self.db=create_store(self.path)
        with self.assertRaisesRegex(CommandRejected,"ALREADY_USED"):
            self.send()
    def test_invalid_signature(self):
        with self.assertRaisesRegex(CommandRejected,"SIGNATURE_MISMATCH"):
            self.send(signature="0"*64)
    def test_wrong_owner(self):
        with self.assertRaisesRegex(CommandRejected,"COMMAND_OWNER_MISMATCH"):
            self.send(expected_owner=OTHER)
    def test_stale_message(self):
        with self.assertRaisesRegex(CommandRejected,"STALE_OR_FUTURE"):
            self.send(data=packet(when=NOW-timedelta(minutes=2)))
    def test_future_message(self):
        with self.assertRaisesRegex(CommandRejected,"STALE_OR_FUTURE"):
            self.send(data=packet(when=NOW+timedelta(minutes=2)))
    def test_browser_cannot_add_approval_flag(self):
        data=packet();data["broker_approved"]=True
        with self.assertRaisesRegex(CommandRejected,"COMMAND_FIELDS_INVALID"):
            self.send(data=data)
    def test_wrong_action(self):
        data=packet();data["action"]="REQUEST_UNLOCK_REVIEW"
        with self.assertRaisesRegex(CommandRejected,"ACTIVATION_ACTION_REQUIRED"):
            self.send(data=data)
    def test_web_button_posts_owner_endpoint(self):
        js=(ROOT/"live_ui.mjs").read_text()
        self.assertIn("/api/v51/owner/activate",js)
        self.assertIn("method:'POST'",js)
    def test_api_requires_owner_and_origin(self):
        py=(ROOT/"market_api.py").read_text()
        a=py.index("if path == '/api/v51/owner/activate'")
        b=py.index("if path == '/api/v48/owner/request-unlock-review'",a)
        block=py[a:b]
        self.assertIn("user_from_token",block)
        self.assertIn("get('ownerMatch') is not True",block)
        self.assertIn("V7_STAGING_ORIGIN",block)
        self.assertIn("REQUEST_ACTIVATE_LIVE",block)
        self.assertIn("OPTIONX_V48_CONTROL_RELAY_ENABLED",block)
    def test_aws_receiver_handles_arm_separately(self):
        s=(ROOT/"live_v7/aws_control_receiver_v48.py").read_text()
        self.assertIn('body.get("action")=="REQUEST_ACTIVATE_LIVE"',s)
        self.assertIn("create_store(self.server.activation_db_path)",s)
    def test_broker_source_still_locked(self):
        from live_v7.angel_execution_transport import capabilities
        self.assertFalse(capabilities()["sourceLockEnabled"])
    self.assertTrue(capabilities()["permitRequired"])
    def test_worker_evidence_not_browser_data(self):
        from live_v7.owner_arm_command_v51 import _trusted_aws_evidence
        self.assertFalse(any(_trusted_aws_evidence().values()))
    def test_no_real_broker_request(self):
        s=(ROOT/"live_v7/owner_arm_command_v51.py").read_text()
        for x in ("placeOrder","cancelOrder","requests.post","urllib.request"):
            self.assertNotIn(x,s)

if __name__=="__main__":
    unittest.main()
