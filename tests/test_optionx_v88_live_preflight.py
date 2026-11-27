"""No broker or database; prove the V88 gate never enables order methods."""
import unittest
from datetime import datetime, timedelta, timezone
from scripts.optionx_v88_live_preflight import ReadinessEvidence, assess

NOW = datetime(2026, 11, 27, 7, tzinfo=timezone.utc)
ALL_TRUE = ReadinessEvidence(**{name: True for name in ReadinessEvidence.__dataclass_fields__})
REC = {"scope":"READ_ONLY_DIAGNOSTIC","broker":"Angel","recoveryCertified":True,"reasons":[],"manualPositionsTouched":False}
def check(**kwargs):
    p=dict(evidence=ALL_TRUE,reconciliation=REC,active_entries_today=0,max_entries_per_day=2,
           remaining_daily_loss_budget=300,broker_snapshot_at=NOW,now=NOW)
    p.update(kwargs)
    return assess(**p)
class PreflightTests(unittest.TestCase):
    def test_all_green_still_never_places(self):
        r=check()
        self.assertTrue(r["eligibleForFurtherReview"])
        self.assertFalse(r["newOrdersEnabled"])
        self.assertTrue(all(r[k] is False for k in ("canBuy","canSell","canModify","canCancel","stopBypassed")))
    def test_missing_mfa(self):
        e=ReadinessEvidence(**{k:k!="owner_aal2_authenticated" for k in ReadinessEvidence.__dataclass_fields__})
        self.assertIn("MISSING_OWNER_AAL2_AUTHENTICATED",check(evidence=e)["unresolved"])
    def test_missing_worker(self):
        e=ReadinessEvidence(**{k:k!="worker_registered_verified" for k in ReadinessEvidence.__dataclass_fields__})
        self.assertIn("MISSING_WORKER_REGISTERED_VERIFIED",check(evidence=e)["unresolved"])
    def test_daily_limit_two(self):
        self.assertIn("GLOBAL_TWO_ENTRY_LIMIT_REACHED",check(active_entries_today=2)["unresolved"])
    def test_daily_limit_not_configured(self):
        self.assertIn("GLOBAL_ENTRY_LIMIT_POLICY_MISMATCH",check(max_entries_per_day=3)["unresolved"])
    def test_negative_trades(self):
        self.assertIn("TRADE_COUNT_UNVERIFIED",check(active_entries_today=-1)["unresolved"])
    def test_bool_trade_count(self):
        self.assertIn("TRADE_COUNT_UNVERIFIED",check(active_entries_today=True)["unresolved"])
    def test_no_risk(self):
        self.assertIn("DAILY_RISK_BUDGET_UNVERIFIED_OR_EXHAUSTED",check(remaining_daily_loss_budget=None)["unresolved"])
    def test_stale_broker(self):
        self.assertIn("BROKER_SNAPSHOT_STALE_OR_MISSING",check(broker_snapshot_at=NOW-timedelta(minutes=1))["unresolved"])
    def test_future_broker(self):
        self.assertIn("BROKER_SNAPSHOT_STALE_OR_MISSING",check(broker_snapshot_at=NOW+timedelta(seconds=2))["unresolved"])
    def test_no_snapshot(self):
        self.assertIn("RECONCILIATION_NOT_VERIFIED",check(reconciliation=None)["unresolved"])
    def test_recovery_false(self):
        self.assertIn("BROKER_RECOVERY_NOT_CERTIFIED",check(reconciliation={**REC,"recoveryCertified":False})["unresolved"])
    def test_manual_position_unknown(self):
        self.assertIn("MANUAL_POSITION_ISOLATION_UNVERIFIED",check(reconciliation={**REC,"manualPositionsTouched":None})["unresolved"])
    def test_open_reconciliation_flags(self):
        self.assertIn("UNRESOLVED_RECONCILIATION_FLAGS",check(reconciliation={**REC,"reasons":["UNKNOWN_ORDER"]})["unresolved"])

if __name__=="__main__":
    unittest.main()
