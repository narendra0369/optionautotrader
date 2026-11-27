"""V92 website owner manual stop gate regression checks (no broker network)."""
from pathlib import Path
import unittest
ROOT=Path(__file__).resolve().parents[1]
class V92WebsiteTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.html=(ROOT/"index.html").read_text(encoding="utf-8")
        cls.js=(ROOT/"live_ui.mjs").read_text(encoding="utf-8")
    def test_panel_is_in_actual_live_page(self):
        self.assertIn('id="v92ManualSlGate"',self.html)
        self.assertIn('id="v92SlGateCheck"',self.html)
    def test_user_visible_gate_cannot_submit(self):
        self.assertIn("No order submitted.",self.js)
        self.assertIn("ORDER TRANSPORT NOT WIRED",self.js)
        self.assertIn("NO ORDER ROUTE",self.html)
    def test_checks_server_not_browser_boolean(self):
        self.assertIn("request('/api/v46/owner/live-unlock-status')",self.js)
        self.assertIn("status.liveOrdersEnabled===true",self.js)
    def test_no_order_submission_in_added_handler(self):
        start=self.js.index("// V92: owner-visible order draft")
        end=self.js.index(" const unlockRequest=",start)
        segment=self.js[start:end]
        for forbidden in ("placeOrder(", "cancelOrder(", "/placeOrder", "/cancelOrder", "fetch('https://apiconnect"):
            self.assertNotIn(forbidden,segment)
    def test_price_relation_and_tick(self):
        self.assertIn("limit<=trigger",self.js)
        self.assertIn("Math.abs(n*20-Math.round(n*20))",self.js)
    def test_owner_session_required(self):
        self.assertIn("if(!user){",self.js)
        self.assertIn("Sign in as the bound OPTIONX owner",self.js)
    def test_contract_and_qty_display(self):
        self.assertIn("NIFTY29DEC2629000CE",self.html)
        self.assertIn('id="v92SlQty"',self.html)
    def test_never_claims_fresh_quote(self):
        self.assertIn("not a fresh broker snapshot",self.js)
if __name__=="__main__":unittest.main()
