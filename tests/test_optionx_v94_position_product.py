import unittest
from live_v7.angel_position_product_v94 import verified_position
from live_v7.angel_sl_guarded_worker_v93 import SLDispatchBlocked

N={"symbol":"NIFTY29DEC2629000CE","exchange":"NFO","instrumentToken":"38158","net_quantity":65}
R={"tradingsymbol":N["symbol"],"exchange":"NFO","symboltoken":"38158","netqty":"65","producttype":"CARRYFORWARD"}
class V94PositionTests(unittest.TestCase):
    def check_blocked(self,**kw):
        data={"normalized":[N],"raw_positions":[R],"expected_symbol":N["symbol"],"expected_quantity":65}
        data.update(kw)
        with self.assertRaises(SLDispatchBlocked):verified_position(**data)
    def test_verified_carryforward(self):
        self.assertEqual(verified_position(normalized=[N],raw_positions=[R],expected_symbol=N["symbol"],expected_quantity=65)["producttype"],"CARRYFORWARD")
    def test_wrong_quantity(self):self.check_blocked(expected_quantity=64)
    def test_duplicate_broker_position(self):self.check_blocked(raw_positions=[R,R])
    def test_duplicate_normalized_position(self):self.check_blocked(normalized=[N,N])
    def test_missing_raw_position(self):self.check_blocked(raw_positions=[])
    def test_broker_product_missing(self):self.check_blocked(raw_positions=[{k:v for k,v in R.items() if k!="producttype"}])
    def test_broker_product_unknown(self):self.check_blocked(raw_positions=[{**R,"producttype":"BOGUS"}])
    def test_broker_token_mismatch(self):self.check_blocked(raw_positions=[{**R,"symboltoken":"999"}])
    def test_broker_quantity_mismatch(self):self.check_blocked(raw_positions=[{**R,"netqty":"64"}])
    def test_negative_qty(self):self.check_blocked(expected_quantity=-65)
    def test_boolean_qty(self):self.check_blocked(expected_quantity=True)
if __name__=="__main__":unittest.main()
