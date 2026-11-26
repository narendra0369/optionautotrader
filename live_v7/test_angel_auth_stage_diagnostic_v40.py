"""V40 diagnostic privacy, single-attempt, stage and no-order tests."""
import io
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import patch
import angel_gateway
from live_v7 import angel_auth_stage_diagnostic_v40 as d

OWNER="11111111-1111-4111-8111-111111111111"
CLIENT="TEST1234"

class AuthStageDiagnosticTests(unittest.TestCase):
    def run_mock(self,*,failure=None,at=None):
        output=io.StringIO()
        calls=[]
        def fake_config(): return OWNER,CLIENT
        def fake_transport(method,endpoint,*args,**kwargs):
            calls.append(method)
            if failure and at==method: raise angel_gateway.AuthError("PRIVATE SECRET")
            return {"status":True}
        def fake_verify(owner,client):
            angel_gateway._post_or_get("POST",angel_gateway.LOGIN,"dummy")
            angel_gateway._post_or_get("GET",angel_gateway.PROFILE,"dummy")
            if failure=="OWNER": raise ValueError("PRIVATE SECRET")
        with patch.object(d,"_config",side_effect=fake_config),\
             patch.object(d,"verify_login",side_effect=fake_verify),\
             patch.object(d.angel_gateway,"_post_or_get",side_effect=fake_transport),\
             patch.object(d.angel_gateway,"disconnect",return_value=None),\
             redirect_stdout(output):
            rc=d.run()
        return rc,output.getvalue(),calls

    def test_success_one_login_one_profile(self):
        rc,out,calls=self.run_mock()
        self.assertEqual(rc,0)
        self.assertEqual(calls,["POST","GET"])
        self.assertIn("V40_AUTHENTICATION: PASS",out)
    def test_login_failure_stage(self):
        rc,out,calls=self.run_mock(failure=True,at="POST")
        self.assertEqual(rc,2)
        self.assertIn("V40_BLOCK_STAGE: LOGIN_API",out)
        self.assertNotIn("PRIVATE SECRET",out)
    def test_profile_failure_stage(self):
        rc,out,calls=self.run_mock(failure=True,at="GET")
        self.assertEqual(rc,2)
        self.assertIn("V40_BLOCK_STAGE: PROFILE_API",out)
        self.assertNotIn("PRIVATE SECRET",out)
    def test_owner_failure_does_not_dump(self):
        rc,out,_=self.run_mock(failure="OWNER")
        self.assertEqual(rc,2)
        self.assertNotIn("PRIVATE SECRET",out)
    def test_config_failure_classified(self):
        buf=io.StringIO()
        with patch.object(d,"_config",side_effect=ValueError("PRIVATE SECRET")),\
             redirect_stdout(buf):
            rc=d.run()
        self.assertEqual(rc,2)
        self.assertIn("V40_BLOCK_STAGE: CONFIG",buf.getvalue())
        self.assertNotIn("PRIVATE SECRET",buf.getvalue())
    def test_unknown_stage_fallback(self):
        self.assertEqual(d.blocked("JWT_TOKEN")["stage"],"PRIVATE_INPUT")
    def test_unknown_category_fallback(self):
        self.assertEqual(d.blocked("LOGIN_API","SECRET")["category"],"UNVERIFIED")
    def test_all_stages_locked(self):
        for stage in d.STAGES:
            row=d.blocked(stage)
            self.assertFalse(row["canSubmitOrder"])
            self.assertFalse(row["realOrdersEnabled"])
            self.assertFalse(row["canRetry"])
    def test_no_order_transport_imports(self):
        src=Path(d.__file__).read_text()
        for unsafe in ("placeOrder","cancelOrder","modifyOrder",
                       "angel_execution_transport","requests.post"):
            self.assertNotIn(unsafe,src)
    def test_no_sensitive_prints(self):
        src=Path(d.__file__).read_text()
        for unsafe in ("print(exc)","print(owner)","print(client)","print(kwargs)",
                       "print(args)","traceback.print_exc"):
            self.assertNotIn(unsafe,src)

if __name__=="__main__": unittest.main()
