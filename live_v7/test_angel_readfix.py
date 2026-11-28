"""Angel V7 GET-only client header parity, mixed exchange validation and private error codes.

No real credentials, no network calls, no order endpoints. All cases are synthetic.
"""
import io
import os
import unittest
import urllib.error
from unittest.mock import patch

from angel_gateway import angel_client_identity_headers
from live_v7.broker_readonly import angel_orders, angel_positions, BrokerSnapshotError
from live_v7.read_only_bridge import angel_owner_snapshot, ReadOnlyBridgeError
from live_v7.read_only_transport import (
    ReadOnlyTransportError, ServerOnlySession, request_headers, fetch_readonly
)

class _MockResponse:
    status=200
    def __enter__(self): return self
    def __exit__(self,*args): return None
    def read(self, size):
        return b'{"status":true,"message":"SUCCESS","data":[]}'

class AngelGetRepairTests(unittest.TestCase):
    def setUp(self):
        self.session=ServerOnlySession(
            broker="Angel",owner_id="owner-test",
            api_key="not_real_api_key_0001",
            bearer_token="mock-jwt-"+"x"*32,
            broker_account_verified=True,session_current=True)

    def test_identity_headers_share_login_profile_helper_no_network(self):
        with patch.dict(os.environ,{"ANGEL_EGRESS_PUBLIC_IPV4":""}):
            data=angel_client_identity_headers(allow_public_lookup=False)
        self.assertEqual(data["X-ClientLocalIP"],"127.0.0.1")
        self.assertIn("X-MACAddress",data)
        self.assertNotIn("X-ClientPublicIP",data)

    def test_angel_get_matches_official_client_identification(self):
        fake={"X-ClientLocalIP":"127.0.0.1","X-ClientPublicIP":"8.8.8.8",
              "X-MACAddress":"00:00:00:00:00:00"}
        with patch("live_v7.read_only_transport.angel_client_identity_headers",return_value=fake) as h:
            data=request_headers(self.session,
                path="/rest/secure/angelbroking/order/v1/getPosition",
                allow_public_lookup=False)
        h.assert_called_once_with(allow_public_lookup=False)
        for k,v in fake.items(): self.assertEqual(data[k],v)
        self.assertEqual(data["X-PrivateKey"],self.session.api_key)
        self.assertEqual(data["Content-Type"],"application/json")
        self.assertEqual(data["Authorization"],"Bearer "+self.session.bearer_token)

    def test_fetch_is_get_to_fixed_angel_endpoint_and_no_orders(self):
        def fetch(req,timeout):
            self.assertEqual(req.get_method(),"GET")
            self.assertEqual(req.full_url,
                "https://apiconnect.angelone.in/rest/secure/angelbroking/order/v1/getPosition")
            self.assertNotIn("placeOrder",req.full_url)
            return _MockResponse()
        with patch("live_v7.read_only_transport.angel_client_identity_headers",return_value={}):
            data=fetch_readonly(
                session=self.session,resource="positions",
                verified_owner_id="owner-test",
                external_read_authorized_by_server=True,fetch=fetch)
        self.assertIs(data["status"],True)
        self.assertEqual(data["data"],[])

    def test_http_denial_has_safe_code_no_private_response_body(self):
        def forbidden(req,timeout):
            raise urllib.error.HTTPError(req.full_url,403,"secret-do-not-display",{},io.BytesIO(b'private'))
        with patch("live_v7.read_only_transport.angel_client_identity_headers",return_value={}):
            with self.assertRaises(ReadOnlyTransportError) as ctx:
                fetch_readonly(session=self.session,resource="orderbook",
                     verified_owner_id="owner-test",external_read_authorized_by_server=True,
                     fetch=forbidden)
        self.assertEqual(ctx.exception.diagnostic_code,"BROKER_AUTH_REJECTED")
        self.assertNotIn("private",str(ctx.exception))
        self.assertNotIn("secret-do-not-display",str(ctx.exception))

    def test_rate_limit_classification_no_provider_body(self):
        def limited(req,timeout):
            raise urllib.error.HTTPError(req.full_url,429,"Limit",{},None)
        with patch("live_v7.read_only_transport.angel_client_identity_headers",return_value={}):
            with self.assertRaises(ReadOnlyTransportError) as ctx:
                fetch_readonly(session=self.session,resource="positions",
                     verified_owner_id="owner-test",external_read_authorized_by_server=True,
                     fetch=limited)
        self.assertEqual(ctx.exception.diagnostic_code,"BROKER_RATE_LIMIT")

    def test_mixed_orderbook_skips_cash_and_keeps_nfo_only(self):
        data={"status":True,"data":[
            {"exchange":"NSE","orderid":"cash-001","tradingsymbol":"SBIN-EQ"},
            {"exchange":"NFO","orderid":"nfo-001","tradingsymbol":"NIFTY27NOV26CE",
             "transactiontype":"BUY","orderstatus":"open",
             "quantity":"25","filledshares":"0"}]}
        rows=angel_orders(data)
        self.assertEqual(len(rows),1);self.assertEqual(rows[0]["symbol"],"NIFTY27NOV26CE")
        self.assertEqual(rows[0]["status"],"OPEN")

    def test_mixed_positionbook_skips_cash_and_keeps_nfo_only(self):
        data={"status":True,"data":[
            {"exchange":"NSE","tradingsymbol":"SBIN-EQ","netqty":"1","symboltoken":"12"},
            {"exchange":"NFO","tradingsymbol":"NIFTY27NOV26PE","netqty":"-25","symboltoken":"38"}]}
        rows=angel_positions(data)
        self.assertEqual(len(rows),1);self.assertEqual(rows[0]["net_quantity"],-25)

    def test_unknown_exchange_remains_rejected_and_no_fabricated_position(self):
        with self.assertRaises(BrokerSnapshotError):
            angel_positions({"status":True,"data":[{"exchange":"UNKNOWN","tradingsymbol":"FOO","symboltoken":"55","netqty":"1"}]})

    def test_angel_status_false_returned_as_safely_categorized_error(self):
        with patch.dict(os.environ,{"OPTIONX_OWNER_USER_ID":"owner-test"}),\
             patch("live_v7.read_only_bridge.angel_gateway._clean_session",
                 return_value={"apiKey":"not_real_api_key_0001","jwt":"mock-jwt-"+"x"*32}),\
             patch("live_v7.read_only_bridge.fetch_readonly",
                 return_value={"status":False,"message":"private-upstream-payload","data":None}):
            with self.assertRaises(ReadOnlyBridgeError) as ctx:
                angel_owner_snapshot(verified_optionx_user_id="owner-test",
                                     resource="positions",server_feature_flag_enabled=True)
        self.assertEqual(ctx.exception.diagnostic_code,"ANGEL_API_REJECTED")
        self.assertNotIn("private",str(ctx.exception))

    def test_expired_session_still_never_calls_broker(self):
        with patch.dict(os.environ,{"OPTIONX_OWNER_USER_ID":"owner-test"}),\
             patch("live_v7.read_only_bridge.angel_gateway._clean_session",return_value=None),\
             patch("live_v7.read_only_bridge.fetch_readonly") as reader:
            with self.assertRaises(ReadOnlyBridgeError) as ctx:
                angel_owner_snapshot(verified_optionx_user_id="owner-test",
                                     resource="positions",server_feature_flag_enabled=True)
        self.assertEqual(ctx.exception.diagnostic_code,"SESSION_EXPIRED")
        reader.assert_not_called()

if __name__=="__main__":
    unittest.main()
