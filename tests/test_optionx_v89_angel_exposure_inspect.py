import unittest
from scripts.optionx_v89_angel_exposure_inspect import summarize

def sample(*, orders=None, positions=None, trades=0):
    books = {
        "orderbook": {"orders":[] if orders is None else orders},
        "tradebook": {"tradeRows":trades},
        "positions": {"positions":[] if positions is None else positions}
    }
    for b in books.values():
        b.update(canSubmitOrder=False, liveExecutionEnabled=False)
    return {"broker":"Angel", "allReadsSucceeded":True, "books":books}

class V89Tests(unittest.TestCase):
    def test_empty_books(self):
        r = summarize(sample())
        self.assertEqual(r["position_records"],0)
        self.assertEqual(r["nonzero_positions"],0)
        self.assertFalse(r["sl_target_broker_ack_verified"])
    def test_one_record_zero_position(self):
        r=summarize(sample(positions=[{"net_quantity":0}]))
        self.assertEqual((r["position_records"],r["nonzero_positions"]),(1,0))
    def test_one_record_nonzero_position(self):
        r=summarize(sample(positions=[{"net_quantity":65}]))
        self.assertEqual((r["position_records"],r["nonzero_positions"]),(1,1))
        self.assertFalse(r["owner_partition_verified"])
    def test_active_order_preserve(self):
        r=summarize(sample(orders=[{"status":"OPEN"}]))
        self.assertEqual(r["active_orders"],1)
        self.assertFalse(r["can_cancel"])
    def test_unknown_order_preserve(self):
        r=summarize(sample(orders=[{"status":"UNKNOWN"}]))
        self.assertEqual(r["active_orders"],1)
        self.assertFalse(r["can_modify"])
    def test_trade_rows_are_not_linked_fills(self):
        r=summarize(sample(trades=4))
        self.assertEqual(r["trade_records"],4)
        self.assertFalse(r["trade_fill_links_verified"])
    def test_incomplete_fails(self):
        b=sample(); del b["books"]["tradebook"]
        with self.assertRaises(ValueError): summarize(b)
    def test_bad_flag_fails(self):
        b=sample(); b["books"]["positions"]["canSubmitOrder"]=True
        with self.assertRaises(ValueError): summarize(b)
    def test_bad_position_qty_fails(self):
        with self.assertRaises(ValueError): summarize(sample(positions=[{"net_quantity":"65"}]))
    def test_unknown_status_fails(self):
        with self.assertRaises(ValueError): summarize(sample(orders=[{"status":"MYSTERY"}]))
    def test_bad_trade_rows_fails(self):
        with self.assertRaises(ValueError): summarize(sample(trades=True))
    def test_wrong_broker_fails(self):
        b=sample(); b["broker"]="Delta"
        with self.assertRaises(ValueError): summarize(b)
    def test_no_order_methods(self):
        r=summarize(sample(positions=[{"net_quantity":1}]))
        self.assertTrue(all(r[k] is False for k in ("can_place","can_sell","can_cancel","can_modify")))
    def test_negative_position_is_exposure(self):
        self.assertEqual(summarize(sample(positions=[{"net_quantity":-65}]))["nonzero_positions"],1)

if __name__=="__main__": unittest.main()
