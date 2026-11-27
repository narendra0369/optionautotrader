import unittest
from scripts.optionx_v91_manual_sl_preflight import check_draft
P={"exchange":"NFO","symbol":"NIFTY29DEC2629000CE","instrumentToken":"38158","net_quantity":65}
class V91Tests(unittest.TestCase):
    def test_readonly(self):
        r=check_draft(position=P,orders=[],ltp="11.25")
        self.assertFalse(r["can_place"]);self.assertEqual(r["net_quantity"],65)
    def test_trigger_not_selected(self):
        self.assertEqual(check_draft(position=P,orders=[],ltp="11.25")["draft_price_check"],"TRIGGER_NOT_SELECTED")
    def test_valid_draft_does_not_permit_order(self):
        r=check_draft(position=P,orders=[],ltp="11.25",trigger="10.50",limit="10.45",tick="0.05")
        self.assertEqual(r["draft_price_check"],"RELATION_VALID_NOT_BROKER_CERTIFIED")
        self.assertFalse(r["can_place"])
    def test_above_ltp_blocked(self):
        with self.assertRaises(ValueError):check_draft(position=P,orders=[],ltp="11.25",trigger="12",limit="11")
    def test_sell_limit_above_trigger_blocked(self):
        with self.assertRaises(ValueError):check_draft(position=P,orders=[],ltp="11.25",trigger="10.5",limit="10.6")
    def test_non_tick_blocked(self):
        with self.assertRaises(ValueError):check_draft(position=P,orders=[],ltp="11.25",trigger="10.53",limit="10.45",tick="0.05")
    def test_short_position_needs_buy_stop(self):
        with self.assertRaises(ValueError):check_draft(position={**P,"net_quantity":-65},orders=[],ltp="11.25")
    def test_zero_exposure_blocked(self):
        with self.assertRaises(ValueError):check_draft(position={**P,"net_quantity":0},orders=[],ltp="11.25")
    def test_active_sell_order_blocked(self):
        with self.assertRaises(ValueError):check_draft(position=P,orders=[{"symbol":P["symbol"],"status":"OPEN"}],ltp="11.25")
    def test_unknown_same_contract_blocked(self):
        with self.assertRaises(ValueError):check_draft(position=P,orders=[{"symbol":P["symbol"],"status":"UNKNOWN"}],ltp="11.25")
    def test_other_contract_does_not_block_draft(self):
        r=check_draft(position=P,orders=[{"symbol":"OTHER","status":"OPEN"}],ltp="11.25")
        self.assertFalse(r["can_place"])
    def test_bad_ltp(self):
        with self.assertRaises(ValueError):check_draft(position=P,orders=[],ltp="0")
    def test_invalid_exchange(self):
        with self.assertRaises(ValueError):check_draft(position={**P,"exchange":"NSE"},orders=[],ltp="11.25")
    def test_invalid_token(self):
        with self.assertRaises(ValueError):check_draft(position={**P,"instrumentToken":""},orders=[],ltp="11.25")
if __name__=="__main__":unittest.main()
