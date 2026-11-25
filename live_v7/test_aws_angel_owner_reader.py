"""No live broker calls: AWS owner reader safety and dependency contract tests."""
from datetime import datetime, timezone
from io import StringIO
from unittest.mock import patch
import os
import unittest

import angel_gateway
from live_v7.aws_angel_owner_reader import (
    _config, one_cycle, verify_login, OwnerReaderError, run_cli
)

OWNER="11111111-1111-4111-8111-111111111111"
NOW=datetime(2026,11,25,6,0,tzinfo=timezone.utc)

class AwsAngelOwnerReaderTests(unittest.TestCase):
    def test_owner_and_client_required(self):
        with patch.dict(os.environ,{"OPTIONX_OWNER_USER_ID":"","ANGEL_ALLOWED_CLIENT_CODE":""}):
            with self.assertRaisesRegex(OwnerReaderError,"OWNER_USER_ID"):
                _config()
    def test_private_interactive_terminal_required(self):
        with patch.dict(os.environ,{"OPTIONX_OWNER_USER_ID":OWNER,"ANGEL_ALLOWED_CLIENT_CODE":"SAFE123"}), \
             patch("os.geteuid",return_value=1001), patch("sys.stdin.isatty",return_value=False):
            with self.assertRaisesRegex(OwnerReaderError,"INTERACTIVE_PRIVATE"):
                _config()
    def test_never_root(self):
        with patch.dict(os.environ,{"OPTIONX_OWNER_USER_ID":OWNER,"ANGEL_ALLOWED_CLIENT_CODE":"SAFE123"}), \
             patch("os.geteuid",return_value=0):
            with self.assertRaisesRegex(OwnerReaderError,"MUST_NOT_RUN_AS_ROOT"):
                _config()
    def test_owner_auth_verifies_profile_without_reporting_credentials(self):
        prompts=iter(["thisisatestkey","1234","123456"])
        captured=[]
        def login(owner,body):
            captured.append((owner,dict(body)))
            return {"connected":True,"ownerMatch":True,"orderExecutionEnabled":False}
        r=verify_login(OWNER,"SAFE123",prompt=lambda _prompt:next(prompts),login=login)
        self.assertEqual(captured[0][1]["clientCode"],"SAFE123")
        self.assertEqual(r,{"connected":True,"ownerMatched":True,"orderExecutionEnabled":False})
        self.assertNotIn("1234",str(r))
        self.assertNotIn("thisisatestkey",str(r))
    def test_invalid_totp_blocks_before_login(self):
        called=[]
        with self.assertRaisesRegex(OwnerReaderError,"INVALID_PRIVATE_LOGIN"):
            verify_login(OWNER,"SAFE123",prompt=lambda _: "invalid",
                         login=lambda *_:called.append(True))
        self.assertFalse(called)
    def test_mismatched_profile_blocks(self):
        with self.assertRaisesRegex(OwnerReaderError,"BROKER_OWNER_PROFILE"):
            verify_login(OWNER,"SAFE123",prompt=iter(["safekey123","pin1","123456"]).__next__ if False else lambda x: {"Angel API key (hidden): ":"safekey123","Angel PIN (hidden): ":"pin1","Angel TOTP 6 digits (hidden): ":"123456"}[x],
                         login=lambda *_:{"connected":True,"ownerMatch":False})
    def test_one_cycle_uses_in_memory_session_and_three_books(self):
        snapshot={"allReadsSucceeded":True}
        seen=[]
        with patch("angel_gateway._owner_bound",return_value=True), \
             patch("angel_gateway._clean_session",return_value={"jwt":"abc","apiKey":"sample"}):
            r=one_cycle(OWNER,object(),
              fetch_books=lambda owner,now: seen.append((owner,now)) or snapshot,
              observe_snapshot=lambda cn,**kwargs:{
                "ordersObserved":0,"positionsObserved":1,"observationDigest":"f"*64,
                "newEntriesBlocked":True,"canSubmitOrder":False},
              clock=lambda:NOW)
        self.assertEqual(seen,[(OWNER,NOW)])
        self.assertFalse(r["canSubmitOrder"])
    def test_broker_session_missing_stops_before_network(self):
        called=[]
        with patch("angel_gateway._owner_bound",return_value=True), \
             patch("angel_gateway._clean_session",return_value=None):
            with self.assertRaisesRegex(OwnerReaderError,"SESSION_EXPIRED"):
                one_cycle(OWNER,object(),fetch_books=lambda *_a,**_k:called.append(True),clock=lambda:NOW)
        self.assertFalse(called)
    def test_incomplete_books_stop_audit(self):
        audit=[]
        with patch("angel_gateway._owner_bound",return_value=True), \
             patch("angel_gateway._clean_session",return_value={"jwt":"mock"}):
            with self.assertRaisesRegex(OwnerReaderError,"READ_INCOMPLETE"):
                one_cycle(OWNER,object(),fetch_books=lambda *_a,**_k:{"allReadsSucceeded":False},
                          observe_snapshot=lambda *_a,**_k:audit.append(True),clock=lambda:NOW)
        self.assertFalse(audit)
    def test_invariant_forbids_execution(self):
        with patch("angel_gateway._owner_bound",return_value=True), \
             patch("angel_gateway._clean_session",return_value={"jwt":"mock"}):
            with self.assertRaisesRegex(OwnerReaderError,"FAIL_CLOSED"):
                one_cycle(OWNER,object(),fetch_books=lambda *_a,**_k:{"allReadsSucceeded":True},
                          observe_snapshot=lambda *_a,**_k:{"newEntriesBlocked":False,"canSubmitOrder":True},clock=lambda:NOW)
    def test_source_never_imports_order_transport(self):
        from pathlib import Path
        data=Path(__file__).with_name("aws_angel_owner_reader.py").read_text()
        for forbidden in ("angel_execution_transport","placeOrder(","cancelOrder(","method=\"POST\""):
            self.assertNotIn(forbidden,data)
    def test_no_live_credential_arguments(self):
        import argparse
        with self.assertRaises(SystemExit):
            run_cli(["--pin","0000"])
    def test_reject_short_polling(self):
        with self.assertRaises(SystemExit):
            run_cli(["--poll-seconds","1"])

if __name__=="__main__":
    unittest.main()
