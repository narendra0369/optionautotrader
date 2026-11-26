"""V30 offline-only manual SELL LIMIT preview: never broker writes."""
import unittest
from datetime import datetime,timezone,timedelta
from pathlib import Path
from live_v7.manual_limit_exit_worker_v30 import preview_manual_exit,PreviewBlocked
P=[{"symbol":"NIFTY29DEC2629000CE","instrumentToken":"38158","net_quantity":65}]
def scenario(**kw):
 return preview_manual_exit(
  positions=kw.get("positions",P),orders=kw.get("orders",[]),
  ltp=kw.get("ltp","11.25"),
  as_of=kw.get("as_of",datetime.now(timezone.utc)),
  verified_owner=kw.get("verified_owner",True))
class V30ManualLimitExitTests(unittest.TestCase):
 def test_genuine_draft_never_order(self):
  x=scenario()
  self.assertEqual(x["limit"],"10.50")
  self.assertEqual(x["premiumLossAtLimitExCharges"],"157.30")
  self.assertFalse(x["canSubmitOrder"])
  self.assertFalse(x["submittedOrder"])
 def test_manual_not_auto_adopted(self):
  self.assertFalse(scenario()["manualPositionAutoAdopted"])
 def test_wrong_quantity(self):
  with self.assertRaisesRegex(PreviewBlocked,"POSITION_QUANTITY_CHANGED"):
   scenario(positions=[dict(P[0],net_quantity=130)])
 def test_wrong_contract(self):
  with self.assertRaisesRegex(PreviewBlocked,"MATCHED"):
   scenario(positions=[dict(P[0],symbol="NIFTY28DEC2629000CE")])
 def test_wrong_token(self):
  with self.assertRaises(PreviewBlocked):
   scenario(positions=[dict(P[0],instrumentToken="999")])
 def test_short_position(self):
  with self.assertRaises(PreviewBlocked):
   scenario(positions=[dict(P[0],net_quantity=-65)])
 def test_existing_sell_blocks(self):
  with self.assertRaisesRegex(PreviewBlocked,"ACTIVE_SELL"):
   scenario(orders=[dict(symbol=P[0]["symbol"],side="SELL",status="OPEN",
      statusKnown=True,quantity=65,filled_quantity=0)])
 def test_pending_sell_blocks(self):
  with self.assertRaises(PreviewBlocked):
   scenario(orders=[dict(symbol=P[0]["symbol"],side="SELL",status="PENDING",
      statusKnown=True,quantity=65,filled_quantity=0)])
 def test_unknown_order_state_blocks(self):
  with self.assertRaisesRegex(PreviewBlocked,"UNRECOGNIZED"):
   scenario(orders=[dict(symbol=P[0]["symbol"],side="BUY",status="UNKNOWN",
      statusKnown=False,quantity=65,filled_quantity=0)])
 def test_ltp_below_limit_blocks(self):
  with self.assertRaisesRegex(PreviewBlocked,"LTP_BELOW"):
   scenario(ltp="10.00")
 def test_invalid_ltp_blocks(self):
  with self.assertRaises(PreviewBlocked):
   scenario(ltp="NaN")
 def test_stale_snapshot_blocks(self):
  with self.assertRaisesRegex(PreviewBlocked,"NOT_FRESHLY"):
   scenario(as_of=datetime.now(timezone.utc)-timedelta(seconds=30))
 def test_future_snapshot_blocks(self):
  with self.assertRaisesRegex(PreviewBlocked,"NOT_FRESHLY"):
   scenario(as_of=datetime.now(timezone.utc)+timedelta(seconds=60))
 def test_owner_rejected(self):
  with self.assertRaisesRegex(PreviewBlocked,"OWNER"):
   scenario(verified_owner=False)
 def test_no_side_effect_transport(self):
  s=Path(__file__).with_name("manual_limit_exit_worker_v30.py").read_text()
  for bad in ("placeOrder","cancelOrder","modifyOrder","angel_execution_transport",
              "/rest/secure/angelbroking/order/v1/placeOrder"):
   self.assertNotIn(bad,s)
if __name__=="__main__":unittest.main()
