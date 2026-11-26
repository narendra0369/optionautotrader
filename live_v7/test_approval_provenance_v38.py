"""Offline regression tests for V38; no broker credentials/orders."""
import unittest
from datetime import datetime,timezone,timedelta
from pathlib import Path
from live_v7.approval_provenance_v38 import (
    inspect_authorization, app_reference_digest, EvidenceInvalid)

NOW=datetime(2026,11,26,7,0,tzinfo=timezone.utc)
DIGEST=app_reference_digest("optionx-test-app")
def record(status="APPROVED",**kw):
    return dict({"status":status,"source_category":"BROKER_OFFICIAL",
                 "app_digest":DIGEST,"issued_at":NOW},**kw)
def audit(**kw):
    basic={"technical":record(),"compliance":record(),
           "trading_api":record(),"undertaking":record(),"static_ip":record(),
           "now":NOW,"expected_app_digest":DIGEST}
    basic.update(kw)
    return inspect_authorization(**basic)
class V38ApprovalProvenanceTests(unittest.TestCase):
    def reason(self,substring,**kw):
        result=audit(**kw)
        self.assertTrue(any(substring in x for x in result["blockedReasons"]))
        self.assertFalse(result["canSubmitOrder"])
    def test_all_claimed_approved_never_unlocks(self):
        result=audit()
        self.assertTrue(result["allClaimedApproved"])
        self.assertFalse(result["evidenceAuthenticatedByThisModule"])
        self.assertFalse(result["canSubmitOrder"])
        self.assertFalse(result["canCancelOrder"])
        self.assertFalse(result["canModifyOrder"])
    def test_conditional_email_not_approval(self):
        self.reason("BROKER_TECHNICAL_APPROVAL_CONDITIONAL",
                    technical=record("CONDITIONAL"))
    def test_pending_compliance(self):
        self.reason("BROKER_COMPLIANCE_APPROVAL_PENDING",
                    compliance=record("PENDING"))
    def test_unverified_trading_api(self):
        self.reason("ACCOUNT_TRADING_API_ENTITLEMENT_UNKNOWN",
                    trading_api=record("UNKNOWN"))
    def test_undertaking_missing(self):
        self.reason("RETAIL_ALGO_UNDERTAKING_EVIDENCE_MISSING",undertaking=None)
    def test_static_ip_pending(self):
        self.reason("STATIC_IP_APP_CONFIRMATION_PENDING",static_ip=record("PENDING"))
    def test_revoked_tech(self):
        self.reason("BROKER_TECHNICAL_APPROVAL_REVOKED",technical=record("REVOKED"))
    def test_not_official_source(self):
        self.reason("BROKER_TECHNICAL_APPROVAL_SOURCE_UNVERIFIED",
                    technical=record(source_category="USER_EMAIL"))
    def test_wrong_app(self):
        self.reason("BROKER_COMPLIANCE_APPROVAL_APP_MISMATCH",
                    compliance=record(app_digest="0"*64))
    def test_future_dated(self):
        self.reason("BROKER_TECHNICAL_APPROVAL_DATE_IN_FUTURE",
                    technical=record(issued_at=NOW+timedelta(seconds=1)))
    def test_expired(self):
        self.reason("BROKER_TECHNICAL_APPROVAL_EVIDENCE_EXPIRED",
                    technical=record(issued_at=NOW-timedelta(days=31)))
    def test_naive_timestamp(self):
        self.reason("BROKER_TECHNICAL_APPROVAL_DATE_INVALID",
                    technical=record(issued_at=NOW.replace(tzinfo=None)))
    def test_missing_status(self):
        self.reason("BROKER_TECHNICAL_APPROVAL_STATUS_INVALID",
                    technical=record(status=None))
    def test_conditional_not_permission_for_any_order(self):
        result=audit(technical=record("CONDITIONAL"))
        self.assertFalse(result["canRetryUnknownOrder"])
        self.assertFalse(result["canAutoResubmitLPP17070"])
        self.assertFalse(result["realOrdersEnabled"])
    def test_naive_now_rejected(self):
        with self.assertRaisesRegex(EvidenceInvalid,"AWARE_EVIDENCE_TIME"):
            audit(now=NOW.replace(tzinfo=None))
    def test_digest_invalid(self):
        with self.assertRaisesRegex(EvidenceInvalid,"EXPECTED_APP_DIGEST"):
            audit(expected_app_digest="invalid")
    def test_app_reference_not_printed(self):
        self.assertEqual(len(DIGEST),64)
        self.assertNotIn("optionx-test-app",DIGEST)
    def test_no_order_transport(self):
        src=Path(__file__).with_name("approval_provenance_v38.py").read_text()
        for forbidden in ("placeOrder","cancelOrder","modifyOrder",
                          "angel_gateway","angel_execution_transport","psycopg"):
            self.assertNotIn(forbidden,src)

if __name__=="__main__": unittest.main()
