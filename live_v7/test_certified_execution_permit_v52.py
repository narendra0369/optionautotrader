"""V52 Angel execution permit regression. No real broker request is allowed.

A positive permit test uses a *local fake HTTP sender*, not Angel network.
"""
import hashlib
import hmac
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from datetime import datetime,timezone

from live_v7.certified_execution_permit_v52 import (
    _canonical_order,verify_dispatch_permit,PermitDenied
)
from live_v7.angel_execution_transport import (
    request,TrustedServerSession,AngelTransportBlocked,capabilities
)

NOW=datetime(2026,11,26,9,0,tzinfo=timezone.utc)
OWNER="11111111-1111-4111-8111-111111111111"
KEY=b"MOCK-ONLY-UNIT-TEST-KEY-USE-NO-REAL-BROKER-123456"
ORDER={"variety":"NORMAL","tradingsymbol":"NIFTY29DEC2629000CE",
       "symboltoken":"38158","transactiontype":"BUY","exchange":"NFO",
       "ordertype":"LIMIT","producttype":"INTRADAY","duration":"DAY",
       "price":"10.50","quantity":"65"}
GATES={k:True for k in (
    "broker_approval_proven","durable_journal_healthy",
    "worker_owner_bound","protective_stop_recovery_tested",
    "kill_switch_persisted_and_clear","broker_snapshot_reconciled",
    "risk_budget_approved")}
SESSION=TrustedServerSession(
    api_key="mock-not-real",jwt="mock-not-real",owner_id=OWNER,
    egress_ip="43.204.246.235",broker_api_approved=True)

class FakeHTTP:
 status=200
 def __enter__(self):return self
 def __exit__(self,*args):return False
 def read(self,count):
    return json.dumps({"status":True,"data":{"orderid":"MOCK-ACK-52"}}).encode()

class V52Tests(unittest.TestCase):
 def setUp(self):
    self.tmp=tempfile.TemporaryDirectory()
    root=Path(self.tmp.name)/"private";root.mkdir(mode=0o700)
    self.ledger=root/"nonce.sqlite"
    self.keyfile=root/"permit.key"
    self.keyfile.write_bytes(KEY)
    self.keyfile.chmod(0o600)
    self.env=patch.dict(os.environ,{
        "OPTIONX_V52_PERMIT_KEY_FILE":str(self.keyfile),
        "OPTIONX_V52_PERMIT_LEDGER_FILE":str(self.ledger)
    })
    self.env.start()
 def tearDown(self):
    self.env.stop()
    self.tmp.cleanup()
 def permit(self,order=None,nonce="a"*32,operation="place"):
    payload=ORDER if order is None else order
    d=_canonical_order(operation,OWNER,payload)
    expiry=int(NOW.timestamp())+5
    message=":".join((d,nonce,str(expiry))).encode()
    signature=hmac.new(KEY,message,hashlib.sha256).hexdigest()
    return {"order_sha256":d,"nonce":nonce,"expires_unix":expiry,
            "mac":signature}
 def verify(self,permit=None,order=None):
    return verify_dispatch_permit(operation="place",owner=OWNER,
        payload=ORDER if order is None else order,
        permit=self.permit() if permit is None else permit,now=NOW)
 def test_missing_permit_rejected(self):
    with self.assertRaisesRegex(PermitDenied,"PERMIT_MISSING"):
        self.verify(permit={})
 def test_valid_permit_consumes_once(self):
    r=self.verify()
    self.assertTrue(r["singleUseConsumed"])
    with self.assertRaisesRegex(PermitDenied,"ALREADY_CONSUMED"):
        self.verify()
 def test_replay_still_denied_after_reopen(self):
    self.verify()
    with self.assertRaises(PermitDenied):self.verify()
 def test_changed_price_rejected(self):
    p=self.permit()
    with self.assertRaisesRegex(PermitDenied,"NOT_BOUND"):
        self.verify(p,dict(ORDER,price="10.55"))
 def test_changed_owner_rejected(self):
    p=self.permit()
    with self.assertRaisesRegex(PermitDenied,"NOT_BOUND"):
        verify_dispatch_permit(operation="place",owner="different-owner",
            payload=ORDER,permit=p,now=NOW)
 def test_invalid_mac_rejected(self):
    p=self.permit();p["mac"]="0"*64
    with self.assertRaisesRegex(PermitDenied,"SIGNATURE_INVALID"):self.verify(p)
 def test_absent_key_rejected(self):
    self.keyfile.unlink()
    with self.assertRaises(PermitDenied):self.verify()
 def test_nonprivate_key_rejected(self):
    self.keyfile.chmod(0o644)
    with self.assertRaisesRegex(PermitDenied,"PERMISSIONS"):self.verify()
 def test_missing_ledger_rejected(self):
    with patch.dict(os.environ,{"OPTIONX_V52_PERMIT_LEDGER_FILE":""}):
        with self.assertRaises(PermitDenied):self.verify()
 def test_expired_permit_rejected(self):
    with self.assertRaisesRegex(PermitDenied,"STALE_OR_TOO_LONG"):
        verify_dispatch_permit(operation="place",owner=OWNER,payload=ORDER,
            permit=self.permit(),now=NOW.replace(hour=10))
 def test_broker_request_missing_permit_never_http(self):
    calls=[]
    def fake(req,timeout=8):
        calls.append(req);return FakeHTTP()
    with self.assertRaises(AngelTransportBlocked):
        request(operation="place",session=SESSION,expected_owner_id=OWNER,
                execution_gate=GATES,payload=ORDER,fetch=fake)
    self.assertEqual(calls,[])
 def test_mock_broker_ack_with_valid_permit(self):
    # Issue within fake trusted worker fixture; external provider never called.
    # Rebind system clock used in verifier to frozen value.
    with patch("live_v7.certified_execution_permit_v52.datetime") as dt:
        dt.now.return_value=NOW
        dt.side_effect=lambda *x,**kw:datetime(*x,**kw)
        r=request(operation="place",session=SESSION,expected_owner_id=OWNER,
            execution_gate=dict(GATES,dispatch_permit=self.permit()),payload=ORDER,
            fetch=lambda req,timeout=8:FakeHTTP())
    self.assertEqual(r["state"],"ACK_RECEIVED_REQUIRES_ORDERBOOK_RECONCILIATION")
    self.assertTrue(r["newEntriesBlocked"])
 def test_gate_missing_prevents_http(self):
    with self.assertRaisesRegex(AngelTransportBlocked,"PRODUCTION_SAFETY_GATES_MISSING"):
        request(operation="place",session=SESSION,expected_owner_id=OWNER,
                execution_gate={"dispatch_permit":self.permit()},payload=ORDER,
                fetch=lambda req,timeout=8:FakeHTTP())
 def test_capabilities_explain_permit_not_live(self):
    cap=capabilities()
    self.assertFalse(cap["sourceLockEnabled"])
    self.assertTrue(cap["permitRequired"])
    self.assertFalse(cap["realOrdersEnabled"])
 def test_unsupported_market_rejected(self):
    invalid=dict(ORDER,exchange="NSE")
    with self.assertRaises(AngelTransportBlocked):
        request(operation="place",session=SESSION,expected_owner_id=OWNER,
                execution_gate=dict(GATES,dispatch_permit=self.permit()),
                payload=invalid,fetch=lambda req,timeout=8:FakeHTTP())
 def test_no_permit_issuer_in_public_routes(self):
    s=(Path(__file__).resolve().parent.parent/"market_api.py").read_text()
    self.assertNotIn("OPTIONX_V52_PERMIT_KEY_FILE",s)
    self.assertNotIn("verify_dispatch_permit",s)

if __name__=="__main__":unittest.main()
