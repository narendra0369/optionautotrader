"""V21 mock-only broker TradeBook and protective STOPLOSS_LIMIT proofs."""
import unittest
from datetime import datetime, timezone, timedelta

from live_v7.broker_evidence_v21 import (
    EvidenceError, confirm_tradebook_fills, confirm_native_stop
)

NOW=datetime(2026,11,25,10,0,tzinfo=timezone.utc)
SYMBOL="NIFTY29DEC2629000CE"
FILL={"exchange":"NFO","orderid":"owned123","fillid":"fill001",
      "fillsize":"25","fillprice":"100.25","tradingsymbol":SYMBOL,
      "transactiontype":"BUY"}
STOP={"orderid":"stop123","exchange":"NFO","tradingsymbol":SYMBOL,
      "symboltoken":"12345","transactiontype":"SELL","variety":"STOPLOSS",
      "ordertype":"STOPLOSS_LIMIT","orderstatus":"trigger pending",
      "quantity":"65","filledshares":"0","unfilledshares":"65",
      "price":"90.00","triggerprice":"91.00"}

def fills(rows,qty=25,**kwargs):
    return confirm_tradebook_fills(
        owned_order_id="owned123",symbol=SYMBOL,expected_quantity=65,
        orderbook_filled_quantity=qty,raw_trade_rows=rows,
        source_authenticated=kwargs.get("source_authenticated",True),
        owner_authenticated=True,snapshot_at=kwargs.get("snapshot_at",NOW),now=NOW
    )
def stop(row=None,**kwargs):
    return confirm_native_stop(
        owned_stop_order_id="stop123",symbol=SYMBOL,
        instrument_token="12345",open_quantity=65,
        orderbook_row=STOP if row is None else row,
        source_authenticated=kwargs.get("source_authenticated",True),
        owner_authenticated=True,snapshot_at=kwargs.get("snapshot_at",NOW),now=NOW
    )
class V21BrokerEvidenceTests(unittest.TestCase):
    def test_valid_partial_fill(self):
        r=fills([FILL])
        self.assertEqual(r["verifiedQuantity"],25)
        self.assertEqual(r["weightedAverageFillPrice"],"100.25")
        self.assertTrue(r["requiresProtection"])
        self.assertFalse(r["canSubmitOrder"])
    def test_two_fill_weighted_average(self):
        other=dict(FILL,fillid="fill002",fillsize="40",fillprice="101.50")
        r=fills([FILL,other],qty=65)
        self.assertEqual(r["verifiedQuantity"],65)
        self.assertEqual(r["weightedAverageFillPrice"],str((25*100.25+40*101.5)/65) if False else "101.0192307692307692307692308")
    def test_duplicate_fillid_rejected(self):
        with self.assertRaisesRegex(EvidenceError,"DUPLICATE"):
            fills([FILL,FILL],qty=50)
    def test_orderbook_fill_quantity_disagreement(self):
        with self.assertRaisesRegex(EvidenceError,"MISMATCH"):
            fills([FILL],qty=50)
    def test_manual_trade_not_claimed(self):
        manual=dict(FILL,orderid="manual999",fillid="manualFill")
        r=fills([manual,FILL])
        self.assertEqual(r["verifiedQuantity"],25)
    def test_unknown_trade_exchange_rejected(self):
        with self.assertRaisesRegex(EvidenceError,"EXCHANGE"):
            fills([dict(FILL,exchange="WTF")])
    def test_owned_wrong_side_rejected(self):
        with self.assertRaisesRegex(EvidenceError,"SIDE"):
            fills([dict(FILL,transactiontype="SELL")])
    def test_unauthenticated_tradebook_rejected(self):
        with self.assertRaisesRegex(EvidenceError,"AUTH"):
            fills([FILL],source_authenticated=False)
    def test_stale_tradebook_rejected(self):
        with self.assertRaisesRegex(EvidenceError,"STALE"):
            fills([FILL],snapshot_at=NOW-timedelta(seconds=11))
    def test_zero_fill_requires_no_stop_but_no_order_enable(self):
        r=fills([],qty=0)
        self.assertFalse(r["requiresProtection"])
        self.assertFalse(r["liveOrdersEnabled"])
    def test_positive_native_stop(self):
        r=stop()
        self.assertTrue(r["stopObservedInBrokerBook"])
        self.assertEqual(r["verifiedRemainingQuantity"],65)
        self.assertFalse(r["stopFillGuaranteed"])
        self.assertFalse(r["targetOCOCertified"])
    def test_wrong_native_stop_id(self):
        with self.assertRaisesRegex(EvidenceError,"NOT_OWNED"):
            stop(dict(STOP,orderid="manual999"))
    def test_wrong_native_stop_contract(self):
        with self.assertRaisesRegex(EvidenceError,"CONTRACT"):
            stop(dict(STOP,tradingsymbol="BANKNIFTY01DEC26CE"))
    def test_stop_cancelled_denied(self):
        with self.assertRaisesRegex(EvidenceError,"NOT_ACTIVE"):
            stop(dict(STOP,orderstatus="cancelled"))
    def test_stop_rejected_denied(self):
        with self.assertRaisesRegex(EvidenceError,"NOT_ACTIVE"):
            stop(dict(STOP,orderstatus="rejected"))
    def test_partial_stop_fill_does_not_cover_open_quantity(self):
        with self.assertRaisesRegex(EvidenceError,"UNPROTECTED"):
            stop(dict(STOP,filledshares="25",unfilledshares="40"))
    def test_stop_limit_trigger_order_invalid(self):
        with self.assertRaisesRegex(EvidenceError,"TRIGGER_RELATION"):
            stop(dict(STOP,price="95",triggerprice="91"))
    def test_stop_variety_verified(self):
        with self.assertRaisesRegex(EvidenceError,"NOT_BROKER_NATIVE"):
            stop(dict(STOP,variety="NORMAL"))
    def test_stop_tampered_source_rejected(self):
        with self.assertRaisesRegex(EvidenceError,"AUTH"):
            stop(source_authenticated=False)
    def test_stop_stale_rejected(self):
        with self.assertRaisesRegex(EvidenceError,"STALE"):
            stop(snapshot_at=NOW-timedelta(seconds=11))
    def test_no_broker_write_transport(self):
        from pathlib import Path
        s=Path(__file__).with_name("broker_evidence_v21.py").read_text()
        self.assertNotIn("placeOrder",s)
        self.assertNotIn("angel_gateway",s)
        self.assertNotIn("requests.",s)

if __name__=="__main__":unittest.main()
