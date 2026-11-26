"""V46 owner live unlock security tests. No order POST, no deploy."""
import unittest
from pathlib import Path
from unittest.mock import patch
from live_v7.owner_live_unlock_v46 import live_unlock_status

ROOT=Path(__file__).resolve().parent.parent

class V46OwnerUnlockTests(unittest.TestCase):
 def test_owner_broker_pass_still_cannot_unlock(self):
    r=live_unlock_status(owner_match=True,verified_session=True)
    self.assertFalse(r["liveOrdersEnabled"])
    self.assertFalse(r["canUnlockFromBrowser"])
    self.assertFalse(r["canSubmitOrder"])
    self.assertIn("BROKER_TRANSPORT_SOURCE_LOCKED",r["blockers"])
 def test_owner_mismatch_is_blocked(self):
    r=live_unlock_status(owner_match=False,verified_session=True)
    self.assertIn("OWNER_BINDING_UNVERIFIED_ON_THIS_SERVER",r["blockers"])
 def test_no_broker_session_still_blocked(self):
    r=live_unlock_status(owner_match=True,verified_session=False)
    self.assertIn("BROKER_SESSION_NOT_ACTIVE_ON_THIS_SERVER",r["blockers"])
 def test_source_lock_removal_does_not_enable(self):
    with patch("live_v7.owner_live_unlock_v46.execution_capabilities",
      return_value={"sourceLockEnabled":False}):
        r=live_unlock_status(owner_match=True,verified_session=True)
        self.assertFalse(r["liveOrdersEnabled"])
        self.assertIn("PRODUCTION_STOP_GUARD_NOT_RELEASED",r["blockers"])
 def test_frontend_page_contains_owner_controls(self):
    html=(ROOT/"index.html").read_text()
    self.assertIn('id="ownerLiveUnlockCheck"',html)
    self.assertIn('id="ownerLiveUnlockStatus"',html)
    self.assertIn('id="ownerLiveUnlockStop" disabled',html)
 def test_frontend_fetches_owner_route(self):
    js=(ROOT/"live_ui.mjs").read_text()
    self.assertIn("/api/v46/owner/live-unlock-status",js)
    self.assertIn("unlockButton.addEventListener('click'",js)
 def test_backend_requires_bound_owner(self):
    py=(ROOT/"market_api.py").read_text()
    start=py.index("if path.path == '/api/v46/owner/live-unlock-status'")
    end=py.index("if path.path == '/api/v7/readiness'",start)
    route=py[start:end]
    self.assertIn("user_from_token",route)
    self.assertIn("get('ownerMatch') is not True",route)
    self.assertIn("return self._json(403",route)
 def test_backend_route_get_only(self):
    py=(ROOT/"market_api.py").read_text()
    start=py.index("def do_POST(")
    self.assertNotIn("'/api/v46/owner/live-unlock-status'",py[start:])
 def test_no_order_writer_in_status_logic(self):
    src=(ROOT/"live_v7/owner_live_unlock_v46.py").read_text()
    for forbidden in ("placeOrder","cancelOrder","modifyOrder","request(", "urllib.request"):
        self.assertNotIn(forbidden,src)
 def test_no_unlock_on_unknown_state(self):
    with patch("live_v7.owner_live_unlock_v46.execution_capabilities",
      return_value={}):
        r=live_unlock_status(owner_match=True,verified_session=True)
        self.assertFalse(r["canSubmitOrder"])
        self.assertIn("BROKER_TRANSPORT_SOURCE_LOCKED",r["blockers"])

if __name__=="__main__":unittest.main()
