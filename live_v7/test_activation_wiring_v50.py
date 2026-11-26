"""V50 UI/backend and execution source-lock integration checks."""
import unittest
from pathlib import Path
from datetime import datetime,timezone
from live_v7.owner_activation_coordinator_v50 import inspect_owner_activation
from live_v7.angel_execution_transport import capabilities

ROOT=Path(__file__).resolve().parent.parent
NOW=datetime(2026,11,26,9,tzinfo=timezone.utc)

class ActivationWiringTests(unittest.TestCase):
 def test_current_capabilities_source_locked(self):
    self.assertTrue(capabilities()["sourceLockEnabled"])
 def test_owner_still_has_blockers(self):
    r=inspect_owner_activation(owner_authenticated=True,now=NOW)
    self.assertFalse(r["eligible"])
    self.assertFalse(r["canArmNow"])
    self.assertIn("ANGEL_SOURCE_LOCK_STILL_ACTIVE",r["blockers"])
 def test_unverified_owner_denied(self):
    r=inspect_owner_activation(owner_authenticated=False,now=NOW)
    self.assertIn("OWNER_VERIFICATION_REQUIRED",r["blockers"])
 def test_ui_button_exists(self):
    self.assertIn('id="ownerLiveActivationAttempt"',(ROOT/"index.html").read_text())
 def test_backend_requires_authenticated_owner(self):
    s=(ROOT/"market_api.py").read_text()
    begin=s.index("if path.path == '/api/v50/owner/activation-eligibility'")
    end=s.index("if path.path == '/api/v46/owner/live-unlock-status'",begin)
    region=s[begin:end]
    self.assertIn("user_from_token",region)
    self.assertIn("get('ownerMatch') is not True",region)
    self.assertIn("return self._json(403",region)
 def test_browser_not_allowed_to_submit_checks(self):
    s=(ROOT/"market_api.py").read_text()
    start=s.index("def do_POST(self):")
    self.assertNotIn("'/api/v50/owner/activation-eligibility'",s[start:])
 def test_no_source_lock_change(self):
    s=(ROOT/"live_v7/angel_execution_transport.py").read_text()
    self.assertIn('raise AngelTransportBlocked("LIVE_ORDERS_SOURCE_LOCKED_PENDING_BROKER_CERTIFICATION")',s)
 def test_no_order_call_in_activation_code(self):
    for name in ("owner_activation_v50.py","owner_activation_coordinator_v50.py"):
       s=(ROOT/"live_v7"/name).read_text()
       for bad in ("placeOrder","cancelOrder","urllib.request","requests.post"):
          self.assertNotIn(bad,s)
 def test_client_text_not_false_live(self):
    s=(ROOT/"live_ui.mjs").read_text()
    self.assertTrue("/api/v50/owner/activation-eligibility" in s or "/api/v51/owner/activate" in s)
    self.assertIn("badge.textContent='REAL ORDERS OFF'",s)

if __name__=="__main__": unittest.main()
