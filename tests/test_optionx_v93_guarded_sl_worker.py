import unittest
from datetime import datetime,timezone,timedelta
from unittest.mock import patch
from live_v7.angel_sl_guarded_worker_v93 import plan, guarded_submit,SLDispatchBlocked
from live_v7.certified_execution_permit_v52 import PermitDenied

NOW=datetime(2026,11,27,7,0,tzinfo=timezone.utc)
P={"exchange":"NFO","symbol":"NIFTY29DEC2629000CE","instrumentToken":"38158",
    "net_quantity":65,"producttype":"CARRYFORWARD"}
G={"productionPermitted":True,"workerIdentityVerified":True,
   "riskReservationCommitted":True,"ownerApprovedExactOrder":True,
   "durableUnknownOutcomeFenceCommitted":True,"brokerLppChecked":True,
   "brokerProductConfirmed":True}
D={"variety":"STOPLOSS","tradingsymbol":P["symbol"],"symboltoken":"38158",
   "transactiontype":"SELL","exchange":"NFO","ordertype":"STOPLOSS_LIMIT",
   "producttype":"CARRYFORWARD","duration":"DAY","price":"6.45",
   "triggerprice":"6.50","quantity":"65"}

def make(**kw):
    d=dict(owner="owner-uuid-verified",position=P,orders=[],ltp="7.10",
           tick="0.05",trigger="6.50",limit="6.45",snapshot_at=NOW,
           now=NOW,gate=G)
    d.update(kw)
    return plan(**d)

class V93Tests(unittest.TestCase):
    def test_valid_structure_does_not_send(self):
        self.assertEqual(make(),D)
    def test_gate_off(self):
        with self.assertRaises(SLDispatchBlocked):make(gate={**G,"productionPermitted":False})
    def test_no_durable_fence(self):
        with self.assertRaises(SLDispatchBlocked):make(gate={**G,"durableUnknownOutcomeFenceCommitted":False})
    def test_no_worker_identity(self):
        with self.assertRaises(SLDispatchBlocked):make(gate={**G,"workerIdentityVerified":False})
    def test_no_owner_approval(self):
        with self.assertRaises(SLDispatchBlocked):make(gate={**G,"ownerApprovedExactOrder":False})
    def test_no_risk_reservation(self):
        with self.assertRaises(SLDispatchBlocked):make(gate={**G,"riskReservationCommitted":False})
    def test_stale_snapshot(self):
        with self.assertRaises(SLDispatchBlocked):make(snapshot_at=NOW-timedelta(seconds=11))
    def test_wrong_quantity_sign(self):
        with self.assertRaises(SLDispatchBlocked):make(position={**P,"net_quantity":-65})
    def test_unconfirmed_product(self):
        with self.assertRaises(SLDispatchBlocked):make(position={**P,"producttype":"MYSTERY"})
    def test_active_order_blocks(self):
        with self.assertRaises(SLDispatchBlocked):make(orders=[{"symbol":P["symbol"],"status":"OPEN"}])
    def test_unknown_order_blocks(self):
        with self.assertRaises(SLDispatchBlocked):make(orders=[{"symbol":P["symbol"],"status":"UNKNOWN"}])
    def test_tick_mismatch(self):
        with self.assertRaises(SLDispatchBlocked):make(trigger="6.51")
    def test_sl_above_quote(self):
        with self.assertRaises(SLDispatchBlocked):make(ltp="6.4")
    def test_lpp_not_verified(self):
        with self.assertRaises(SLDispatchBlocked):make(gate={**G,"brokerLppChecked":False})
    def test_missing_permit_never_calls_broker(self):
        calls=[]
        with self.assertRaises(PermitDenied):
            guarded_submit(owner="owner-uuid-verified",draft=D,permit=None,
                           submit=lambda d:calls.append(d),read_orderbook=lambda:[],now=NOW)
        self.assertEqual(calls,[])
    @patch("live_v7.angel_sl_guarded_worker_v93.verify_dispatch_permit",
           return_value={"verified":True})
    def test_one_submit_and_book_match(self,_):
        called=[]
        def send(d):called.append(1);return {"orderid":"B12345"}
        result=guarded_submit(owner="owner-uuid-verified",draft=D,permit={},
            submit=send,read_orderbook=lambda:[{"order_id":"B12345","symbol":P["symbol"],
                   "side":"SELL","quantity":65,"status":"OPEN"}],now=NOW)
        self.assertEqual(called,[1])
        self.assertTrue(result["brokerOrderPlacedConfirmed"])
        self.assertFalse(result["stopTriggerAcceptedIndependently"])
    @patch("live_v7.angel_sl_guarded_worker_v93.verify_dispatch_permit",return_value={"verified":True})
    def test_network_unknown_never_retry(self,_):
        called=[]
        def fail(d):called.append(1);raise OSError("timeout")
        result=guarded_submit(owner="owner-uuid-verified",draft=D,permit={},
                 submit=fail,read_orderbook=lambda:[],now=NOW)
        self.assertEqual(called,[1])
        self.assertEqual(result["state"],"UNKNOWN_BROKER_OUTCOME")
        self.assertFalse(result["canRetry"])
    @patch("live_v7.angel_sl_guarded_worker_v93.verify_dispatch_permit",return_value={"verified":True})
    def test_broker_book_mismatch_never_retry(self,_):
        result=guarded_submit(owner="owner-uuid-verified",draft=D,permit={},
              submit=lambda d:{"orderid":"B12345"},
              read_orderbook=lambda:[{"order_id":"B12345","symbol":"WRONG",
                                    "side":"SELL","quantity":65,"status":"OPEN"}],now=NOW)
        self.assertFalse(result["brokerOrderPlacedConfirmed"])
        self.assertFalse(result["canRetry"])
if __name__=="__main__":unittest.main()
