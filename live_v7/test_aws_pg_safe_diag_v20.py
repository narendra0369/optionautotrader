"""V20 mock-only checks: no network or secret disclosure."""
import unittest
from unittest.mock import patch
from live_v7.aws_pg_safe_diag_v20 import (
    DiagnosticError, PG_HOST, PG_USER, connect_readonly, stage_name
)

class FakeDB:
    autocommit=False
    closed=False
    def close(self): self.closed=True

class FakeDriver:
    kwargs=None
    @staticmethod
    def connect(**kw):
        FakeDriver.kwargs=kw
        return FakeDB()

class V20SafeDiagnosticsTests(unittest.TestCase):
    def test_password_separate_and_tls_mandatory(self):
        with patch("os.geteuid",return_value=1000), \
             patch("sys.stdin.isatty",return_value=True), \
             patch("sys.stdout.isatty",return_value=True), \
             patch("pathlib.Path.is_file",return_value=True), \
             patch("os.access",return_value=True):
            db=connect_readonly(prompt=lambda _: "P@ss:#%",driver=FakeDriver)
        self.assertFalse(db.autocommit)
        self.assertEqual(FakeDriver.kwargs["password"],"P@ss:#%")
        self.assertEqual(FakeDriver.kwargs["sslmode"],"verify-full")
        self.assertEqual(FakeDriver.kwargs["host"],PG_HOST)
        self.assertEqual(FakeDriver.kwargs["user"],PG_USER)
        self.assertEqual(FakeDriver.kwargs["options"],"-c default_transaction_read_only=on")
        self.assertNotIn("uri",FakeDriver.kwargs)
    def test_requires_private_nonroot_tty(self):
        with patch("os.geteuid",return_value=0):
            with self.assertRaisesRegex(DiagnosticError,"PRIVATE_OPTIONX_TTY"):
                connect_readonly(driver=FakeDriver)
    def test_ca_must_be_accessible(self):
        with patch("os.geteuid",return_value=1000), \
             patch("sys.stdin.isatty",return_value=True), \
             patch("sys.stdout.isatty",return_value=True), \
             patch("pathlib.Path.is_file",return_value=False):
            with self.assertRaisesRegex(DiagnosticError,"CA_NOT_READABLE"):
                connect_readonly(driver=FakeDriver)
    def test_missing_password_blocks(self):
        with patch("os.geteuid",return_value=1000), \
             patch("sys.stdin.isatty",return_value=True), \
             patch("sys.stdout.isatty",return_value=True), \
             patch("pathlib.Path.is_file",return_value=True), \
             patch("os.access",return_value=True):
            with self.assertRaisesRegex(DiagnosticError,"PASSWORD_MISSING"):
                connect_readonly(prompt=lambda _: "",driver=FakeDriver)
    def test_no_exception_message_disclosed(self):
        for stage in ("PG_CONNECT","ANGEL_LOGIN","BROKER_BOOKS","RECONCILE","OWNER_CONFIG"):
            result=stage_name(RuntimeError("private-user:secret@host"),stage)
            self.assertNotIn("private",result)
            self.assertNotIn("secret",result)
    def test_auth_sqlstate_classified(self):
        class Error(Exception):
            sqlstate="28P01"
        self.assertEqual(stage_name(Error("secret"),"PG_CONNECT"),"SUPABASE_AUTH_REJECTED")
    def test_no_execution_transport(self):
        from pathlib import Path
        src=Path(__file__).with_name("aws_pg_safe_diag_v20.py").read_text()
        self.assertNotIn("angel_execution_transport",src)
        self.assertNotIn("placeOrder",src)
        self.assertNotIn("insert into optionx_private",src.lower())
        self.assertNotIn("update optionx_private",src.lower())

if __name__ == "__main__":
    unittest.main()
