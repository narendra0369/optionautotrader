"""Offline no-broker tests for V87 fail-closed reconciliation."""
import unittest
from datetime import datetime, timedelta, timezone
from scripts.optionx_v87_angel_reconcile import reconcile

NOW = datetime(2026, 11, 27, 5, tzinfo=timezone.utc)
def snapshot(orders=None, positions=None, trade_rows=0):
    books = {
        "orderbook": {"orders": [] if orders is None else orders},
        "positions": {"positions": [] if positions is None else positions},
        "tradebook": {"tradeRows": trade_rows},
    }
    for resource, body in books.items():
        body.update(broker="Angel", resource=resource, mode="OWNER_BOUND_READ_ONLY",
                    canSubmitOrder=False, liveExecutionEnabled=False)
    return {"broker": "Angel", "allReadsSucceeded": True, "books": books}
def evaluate(b=None, **kwargs):
    opts = {"received_at": NOW, "now": NOW, "owner_session_verified": True,
            "server_authenticated_transport": True}
    opts.update(kwargs)
    return reconcile(snapshot() if b is None else b, **opts)
class V87Tests(unittest.TestCase):
    def test_empty_still_not_certified(self):
        r=evaluate(); self.assertFalse(r["recoveryCertified"]); self.assertFalse(r["canPlace"])
    def test_unverified_owner(self):
        self.assertIn("BROKER_OWNER_OR_TRANSPORT_NOT_VERIFIED", evaluate(owner_session_verified=False)["reasons"])
    def test_unverified_transport(self):
        self.assertIn("BROKER_OWNER_OR_TRANSPORT_NOT_VERIFIED", evaluate(server_authenticated_transport=False)["reasons"])
    def test_stale(self):
        self.assertIn("BROKER_SNAPSHOT_STALE", evaluate(received_at=NOW-timedelta(seconds=30))["reasons"])
    def test_future(self):
        self.assertIn("BROKER_SNAPSHOT_STALE", evaluate(received_at=NOW+timedelta(seconds=1))["reasons"])
    def test_incomplete(self):
        b=snapshot(); del b["books"]["tradebook"]
        self.assertIn("THREE_BOOKS_INCOMPLETE", evaluate(b)["reasons"])
    def test_unknown_order(self):
        b=snapshot(orders=[{"order_id":"ABCD","status":"UNKNOWN"}])
        self.assertIn("UNKNOWN_ORDER_STATE", evaluate(b)["reasons"])
    def test_manual_order(self):
        b=snapshot(orders=[{"order_id":"MANUAL","status":"OPEN"}])
        self.assertIn("NON_OPTIONX_ACTIVE_ORDER_PRESERVE",evaluate(b)["reasons"])
    def test_manual_position(self):
        self.assertIn("BROKER_EXPOSURE_OWNER_RECONCILIATION_REQUIRED",
            evaluate(snapshot(positions=[{"net_quantity":65}]))["reasons"])
    def test_known_order_still_no_cancel(self):
        b=snapshot(orders=[{"order_id":"X123","status":"OPEN"}])
        r=evaluate(b,optionx_order_ids=frozenset({"X123"}))
        self.assertFalse(r["canCancel"]); self.assertFalse(r["recoveryCertified"])
    def test_bad_resource_mode(self):
        b=snapshot(); b["books"]["positions"]["mode"]="PUBLIC"
        self.assertIn("INVALID_POSITIONS_SNAPSHOT",evaluate(b)["reasons"])
    def test_bad_quantity(self):
        self.assertIn("POSITION_QUANTITY_INVALID",evaluate(snapshot(positions=[{"net_quantity":"65"}]))["reasons"])
    def test_naive_timestamp(self):
        self.assertIn("TIMESTAMPS_MISSING",evaluate(now=NOW.replace(tzinfo=None))["reasons"])
    def test_no_dispatch(self):
        r=evaluate()
        self.assertTrue(all(r[k] is False for k in ("canPlace","canSell","canCancel","canModify","manualPositionsTouched")))

if __name__ == "__main__": unittest.main()
