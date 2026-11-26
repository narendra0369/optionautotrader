"""V49 end-to-end mock broker worker tests. No live broker network."""
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

from live_v7.durable_intent_v43 import open_ledger, recover
from live_v7.owner_control_store_v47 import (
    open_control_store,request_unlock_review,emergency_stop,read_state
)
from live_v7.lifecycle_worker_v49 import (
    run_mock_cycle,DeterministicMockGateway,LifecycleBlocked
)

OWNER="11111111-1111-4111-8111-111111111111"
NOW=datetime(2026,11,26,9,0,tzinfo=timezone.utc)
DRAFT={"contract":"NIFTY29DEC2629000CE","token":"38158",
       "quantity":65,"side":"SELL","orderType":"LIMIT",
       "limit":"10.50","canSubmitOrder":False,
       "submittedOrder":False,"realOrdersEnabled":False}
class V49WorkerTests(unittest.TestCase):
 def setUp(self):
    self.tmp=tempfile.TemporaryDirectory()
    p=Path(self.tmp.name)/"owner-private"
    p.mkdir(mode=0o700)
    self.intent_path=p/"intents.db"
    self.ctrl_path=p/"controls.db"
    self.intent=open_ledger(self.intent_path)
    self.ctrl=open_control_store(self.ctrl_path)
    self.broker=DeterministicMockGateway()
 def tearDown(self):
    self.intent.close();self.ctrl.close();self.tmp.cleanup()
 def cycle(self,scenario="COMPLETE",key="v49-key-000001",gateway=None):
    return run_mock_cycle(intent_db=self.intent,control_db=self.ctrl,
      owner_id=OWNER,intent_key=key,draft=DRAFT,now=NOW,
      mock_gateway=gateway or self.broker,scenario=scenario)
 def test_complete_books_consistent_never_live(self):
    r=self.cycle()
    self.assertEqual(r["phase"],"MOCK_BOOKS_CONSISTENT")
    self.assertEqual(r["reconciliation"]["filledQuantityObserved"],65)
    self.assertFalse(r["canSubmitOrder"])
    self.assertEqual(r["brokerOrdersSent"],0)
 def test_exact_replay_prevented(self):
    self.cycle()
    r=self.cycle()
    self.assertEqual(r["phase"],"DUPLICATE_NO_DISPATCH")
    self.assertEqual(self.broker.calls,1)
 def test_unknown_response_stays_blocked(self):
    r=self.cycle(scenario="UNKNOWN")
    self.assertEqual(r["phase"],"UNKNOWN_OUTCOME_REQUIRES_RECONCILIATION")
    self.assertFalse(r["canRetryUnknownOrder"])
 def test_unknown_cannot_retry_after_restart(self):
    self.cycle(scenario="UNKNOWN")
    self.intent.close()
    self.intent=open_ledger(self.intent_path)
    r=self.cycle()
    self.assertEqual(r["phase"],"DUPLICATE_NO_DISPATCH")
    self.assertEqual(self.broker.calls,1)
 def test_partial_fill_requires_review(self):
    r=self.cycle(scenario="PARTIAL")
    self.assertEqual(r["phase"],"REVIEW_REQUIRED")
    self.assertIn("ORDER_STILL_ACTIVE_OR_UNCERTAIN",r["reconciliation"]["blockers"])
 def test_rejected_no_fill_consistent_no_retry(self):
    r=self.cycle(scenario="REJECTED")
    self.assertEqual(r["phase"],"MOCK_BOOKS_CONSISTENT")
    self.assertEqual(r["reconciliation"]["state"],"TERMINAL_NO_FILL_CONFIRMED_IN_BOOKS")
    self.assertFalse(r["canRetryUnknownOrder"])
 def test_cancelled_no_fill(self):
    r=self.cycle(scenario="CANCELLED")
    self.assertEqual(r["reconciliation"]["orderStatusObserved"],"cancelled")
    self.assertFalse(r["canCancelOrder"])
 def test_stopped_default_rejects_real_but_runs_mock(self):
    self.assertEqual(read_state(self.ctrl,owner_id=OWNER)["mode"],"STOPPED")
    self.assertFalse(self.cycle()["liveOrdersEnabled"])
 def test_review_state_does_not_arm(self):
    request_unlock_review(self.ctrl,owner_id=OWNER,owner_verified=True,when=NOW)
    r=self.cycle()
    self.assertFalse(r["liveOrdersEnabled"])
    self.assertFalse(r["canSubmitOrder"])
 def test_emergency_stop_preserved(self):
    emergency_stop(self.ctrl,owner_id=OWNER,owner_verified=True,when=NOW)
    self.assertFalse(self.cycle()["liveOrdersEnabled"])
    self.assertEqual(read_state(self.ctrl,owner_id=OWNER)["mode"],"STOPPED")
 def test_stopped_unchanged_after_full_fill(self):
    self.cycle()
    self.assertEqual(read_state(self.ctrl,owner_id=OWNER)["mode"],"STOPPED")
 def test_gateway_exception_fenced(self):
    class Bad:
      mock_only=True
      def simulate(self,**kwargs):raise TimeoutError("mock timeout")
    r=self.cycle(gateway=Bad())
    self.assertEqual(r["phase"],"UNKNOWN_OUTCOME_REQUIRES_RECONCILIATION")
    self.assertEqual(recover(self.intent,owner_id=OWNER,idempotency_key="v49-key-000001",now=NOW)["state"],"MAY_HAVE_SENT_RECONCILE")
 def test_real_gateway_denied(self):
    class Real:
      mock_only=False
      def simulate(self,**kwargs):raise AssertionError("must not run")
    with self.assertRaisesRegex(LifecycleBlocked,"MOCK_GATEWAY_ONLY"):
        self.cycle(gateway=Real())
 def test_missing_mock_identity_denied(self):
    with self.assertRaisesRegex(LifecycleBlocked,"MOCK_GATEWAY_ONLY"):
        self.cycle(gateway=object())
 def test_scenario_allowlist(self):
    with self.assertRaisesRegex(LifecycleBlocked,"SCENARIO_NOT_ALLOWLISTED"):
        self.cycle(scenario="REAL_SEND")
 def test_control_db_persists(self):
    emergency_stop(self.ctrl,owner_id=OWNER,owner_verified=True,when=NOW)
    self.ctrl.close();self.ctrl=open_control_store(self.ctrl_path)
    self.assertEqual(read_state(self.ctrl,owner_id=OWNER)["mode"],"STOPPED")
 def test_durable_intent_sealed_after_complete(self):
    self.cycle()
    r=recover(self.intent,owner_id=OWNER,idempotency_key="v49-key-000001",now=NOW)
    self.assertEqual(r["state"],"MAY_HAVE_SENT_RECONCILE")
 def test_old_position_not_adopted(self):
    r=self.cycle()
    self.assertFalse(r["reconciliation"]["canSubmitOrder"])
    self.assertEqual(r["reason"],"SYNTHETIC_EVIDENCE_ONLY")
 def test_malformed_preview_cannot_reach_ledger(self):
    malformed=dict(DRAFT,unexpected="unknown")
    with self.assertRaisesRegex(LifecycleBlocked,"SYNTHETIC_DRAFT_FIELDS_INVALID"):
        run_mock_cycle(intent_db=self.intent,control_db=self.ctrl,
          owner_id=OWNER,intent_key="v49-bad-preview",draft=malformed,
          now=NOW,mock_gateway=self.broker,scenario="COMPLETE")
    self.assertEqual(self.broker.calls,0)
 def test_preview_live_flag_cannot_override_stop(self):
    malicious=dict(DRAFT,canSubmitOrder=True)
    with self.assertRaisesRegex(LifecycleBlocked,"SYNTHETIC_DRAFT_MUST_REMAIN_LOCKED"):
        run_mock_cycle(intent_db=self.intent,control_db=self.ctrl,
          owner_id=OWNER,intent_key="v49-bad-flag",draft=malicious,
          now=NOW,mock_gateway=self.broker,scenario="COMPLETE")
    self.assertEqual(self.broker.calls,0)
 def test_source_lock_unchanged(self):
    from live_v7.angel_execution_transport import capabilities
    self.assertFalse(capabilities()["sourceLockEnabled"])
    self.assertTrue(capabilities()["permitRequired"])
    self.assertFalse(capabilities()["realOrdersEnabled"])
 def test_no_live_transport_import(self):
    s=(Path(__file__).with_name("lifecycle_worker_v49.py")).read_text()
    for term in ("angel_gateway","placeOrder","cancelOrder","urllib.request"):
       self.assertNotIn(term,s)
if __name__=="__main__":unittest.main()
