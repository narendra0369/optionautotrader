"""V48 Render->AWS relay and route hardening tests. No live network."""
import io
import json
import unittest
from pathlib import Path
from datetime import datetime,timezone
from live_v7.render_aws_relay_v48 import forward_owner_control,RelayBlocked

ROOT=Path(__file__).resolve().parent.parent
OWNER="11111111-1111-4111-8111-111111111111"
OTHER="22222222-2222-4222-8222-222222222222"
KEY=b"mock-only-test-key-abcdefghijklmnopqrstuvwxyz12345"
URL="https://owner-control.example.invalid/v48/owner/control"
NOW=datetime(2026,11,26,9,0,tzinfo=timezone.utc)
class FakeResponse:
 status=200
 def __enter__(self):return self
 def __exit__(self,*args):return False
 def read(self,n):return json.dumps({"commandAccepted":True,
       "mode":"REVIEW_REQUESTED","liveOrdersEnabled":False}).encode()
class Capture:
 def __init__(self):self.calls=[]
 def __call__(self,request,timeout=7):
    self.calls.append((request,timeout))
    return FakeResponse()
class RelayV48Tests(unittest.TestCase):
 def call(self,**kw):
    args=dict(verified_owner_id=OWNER,expected_owner_id=OWNER,
      action="REQUEST_UNLOCK_REVIEW",signing_key=KEY,
      aws_endpoint=URL,now=NOW,opener=Capture())
    args.update(kw)
    return forward_owner_control(**args)
 def test_gateway_signed_ack_stays_off(self):
    c=Capture();r=self.call(opener=c)
    self.assertTrue(r["awsControlAcknowledged"])
    self.assertFalse(r["liveOrdersEnabled"])
    self.assertEqual(c.calls[0][0].get_method(),"POST")
 def test_bearer_not_forwarded(self):
    c=Capture();self.call(opener=c)
    req=c.calls[0][0]
    self.assertNotIn("Authorization",dict(req.headers))
    self.assertIn("X-optionx-signature",req.headers)
 def test_wrong_owner(self):
    with self.assertRaisesRegex(RelayBlocked,"VERIFIED_OWNER_REQUIRED"):
        self.call(verified_owner_id=OTHER)
 def test_empty_owner(self):
    with self.assertRaises(RelayBlocked):self.call(verified_owner_id=None)
 def test_disallow_real_start(self):
    with self.assertRaisesRegex(RelayBlocked,"ACTION_NOT_ALLOWED"):
        self.call(action="START_TRADING")
 def test_disallow_http(self):
    with self.assertRaises(RelayBlocked):
        self.call(aws_endpoint="http://localhost:8766/v48/owner/control")
 def test_disallow_password_in_url(self):
    with self.assertRaises(RelayBlocked):
        self.call(aws_endpoint="https://user:password@abc.invalid/v48/owner/control")
 def test_disallow_wrong_path(self):
    with self.assertRaises(RelayBlocked):
        self.call(aws_endpoint="https://abc.invalid/order/place")
 def test_weak_signing_key(self):
    from live_v7.signed_owner_commands_v48 import CommandRejected
    with self.assertRaises(CommandRejected):self.call(signing_key=b"weak")
 def test_render_endpoint_owner_session_check(self):
    s=(ROOT/"market_api.py").read_text()
    x=s.index("if path == '/api/v48/owner/request-unlock-review'")
    y=s.index("if path in ('/api/brokers/stoxkart/start'",x)
    block=s[x:y]
    self.assertIn("user_from_token",block)
    self.assertIn("get('ownerMatch') is not True",block)
    self.assertIn("OPTIONX_V48_CONTROL_RELAY_ENABLED",block)
    self.assertIn("forward_owner_control",block)
 def test_render_no_browser_custom_action(self):
    s=(ROOT/"market_api.py").read_text()
    x=s.index("if path == '/api/v48/owner/request-unlock-review'")
    y=s.index("if path in ('/api/brokers/stoxkart/start'",x)
    self.assertIn("action='REQUEST_UNLOCK_REVIEW'",s[x:y])
 def test_website_button_exists(self):
    self.assertIn('id="ownerLiveUnlockRequest"',(ROOT/"index.html").read_text())
 def test_website_no_post_order(self):
    s=(ROOT/"live_ui.mjs").read_text()
    self.assertIn("/api/v48/owner/request-unlock-review",s)
    self.assertIn("Execution remains OFF",s)
 def test_aws_receiver_loopback_only(self):
    s=(ROOT/"live_v7/aws_control_receiver_v48.py").read_text()
    self.assertIn('("127.0.0.1",port)',s)
    self.assertIn("LOOPBACK_BIND_ONLY",s)
    self.assertIn("apply_signed_command",s)
 def test_aws_no_broker_calls(self):
    for name in ("signed_owner_commands_v48.py","render_aws_relay_v48.py",
                 "aws_control_receiver_v48.py"):
        s=(ROOT/"live_v7"/name).read_text()
        for bad in ("placeOrder","cancelOrder","modifyOrder","angel_execution_transport.request"):
            self.assertNotIn(bad,s)
 def test_relay_status_not_live(self):
    c=Capture();r=self.call(opener=c)
    self.assertFalse(r["canSubmitOrder"])

if __name__=="__main__":unittest.main()
