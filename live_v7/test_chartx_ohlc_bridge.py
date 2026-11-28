import hashlib,hmac,os,time,unittest
from unittest.mock import patch
from live_v7 import chartx_ohlc_bridge as B
class TestBridge(unittest.TestCase):
    def test_disabled(self):
        with patch.dict(os.environ,{},clear=True):
            with self.assertRaises(PermissionError): B.authenticate("NIFTY","15m",str(int(time.time())),"0"*64)
    def test_scope_and_session(self):
        env={"CHARTX_BRIDGE_ENABLED":"1","CHARTX_DATA_ACCESS_KEY":"x"*40,"OPTIONX_OWNER_USER_ID":"owner"}
        t=str(int(time.time()))
        sig=hmac.new(("x"*40).encode(),("chartx-ohlc-v1|NIFTY|15m|"+t).encode(),hashlib.sha256).hexdigest()
        with patch.dict(os.environ,env,clear=True):
            with patch.object(B.angel_gateway,"_clean_session",return_value=None):
                with self.assertRaises(PermissionError):B.authenticate("NIFTY","15m",t,sig)
            with patch.object(B.angel_gateway,"_clean_session",return_value={"jwt":"mock","apiKey":"mock","verifiedAt":"test"}) as lookup:
                self.assertEqual(B.authenticate("NIFTY","15m",t,sig)["verifiedAt"],"test")
                lookup.assert_called_with("owner",unittest.mock.ANY)
                with self.assertRaises(PermissionError):B.authenticate("BANKNIFTY","15m",t,sig)
                with self.assertRaises(ValueError):B.authenticate("ORDER","15m",t,sig)
                with self.assertRaises(PermissionError):B.authenticate("NIFTY","15m",t,sig,now=int(t)+60)
