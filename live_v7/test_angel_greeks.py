"""Angel authenticated option Greeks read-only proxy: entirely fake broker I/O."""
import json
import os
import unittest
from unittest.mock import patch

from live_v7 import angel_marketdata as md
from live_v7 import angel_greeks as g
from live_v7.test_angel_marketdata import CLOCK, master, MockQuote
from live_v7.test_stoxkart_http import hit, STAGING


def chain():
    return {
      "status":True,"data":[
       {"name":"NIFTY","expiry":"26NOV2026","strikePrice":"25000.000000",
        "optionType":"CE","delta":"0.492400","gamma":"0.0028","theta":"-4.0918",
        "vega":"2.2967","impliedVolatility":"16.3300"},
       {"name":"NIFTY","expiry":"26NOV2026","strikePrice":"25000.000000",
        "optionType":"PE","delta":"-0.507600","gamma":"0.0028","theta":"-4.0918",
        "vega":"2.2967","impliedVolatility":"16.3300"}
      ]}


class AngelGreeksReadOnlyTests(unittest.TestCase):
    def setUp(self):
        with md._LOCK:
            md._CACHE.update(loaded=0,contracts={},asof="")
        with g._LOCK:
            g._LAST.clear()
        self.owner=patch("angel_gateway._owner_bound",return_value=True)
        self.session=patch("angel_gateway._clean_session",
                            return_value={"apiKey":"mockkey_notreal","jwt":"a"*60})
        self.identity=patch("angel_gateway.angel_client_identity_headers",return_value={})
        for p in (self.owner,self.session,self.identity):
            p.start();self.addCleanup(p.stop)

    def _fetch(self, req, timeout):
        self.assertEqual(req.get_method(),"POST")
        self.assertEqual(req.full_url,g._GREEKS_URL)
        self.assertEqual(json.loads(req.data),{"name":"NIFTY","expirydate":"26NOV2026"})
        self.assertNotIn("placeOrder",req.full_url)
        return MockQuote(json.dumps(chain()).encode())

    def test_server_read_only_posts_exact_name_expiry_and_returns_only_one_option(self):
        out=g.angel_selected_contract_greeks(
            "verified-user","111111",master_fetch=master,greeks_fetch=self._fetch,clock=CLOCK)
        self.assertEqual(out["resource"],"selectedOptionGreeks")
        self.assertEqual(out["contract"]["side"],"CE")
        self.assertEqual(out["contract"]["lotSize"],65)
        self.assertEqual(out["contract"]["tickSize"],0.05)
        self.assertEqual(out["greeks"]["iv"],16.33)
        self.assertAlmostEqual(out["greeks"]["delta"],0.4924)
        self.assertFalse(out["exchangeTimestampVerified"])
        self.assertFalse(out["executionPriceVerified"])
        self.assertFalse(out["canSubmitOrder"])
        self.assertFalse(out["orderExecutionEnabled"])

    def test_put_option_selects_negative_delta_and_no_other_row(self):
        out=g.angel_selected_contract_greeks(
            "verified-user","222222",master_fetch=master,greeks_fetch=self._fetch,clock=CLOCK)
        self.assertEqual(out["contract"]["side"],"PE")
        self.assertLess(out["greeks"]["delta"],0)

    def test_repeated_poll_is_blocked(self):
        g.angel_selected_contract_greeks(
            "verified-user","111111",master_fetch=master,greeks_fetch=self._fetch,clock=CLOCK)
        with self.assertRaises(md.MarketDataError) as ctx:
            g.angel_selected_contract_greeks(
               "verified-user","111111",master_fetch=master,greeks_fetch=self._fetch,clock=CLOCK)
        self.assertEqual(ctx.exception.code,"GREEKS_POLL_RATE_LIMIT")

    def test_unverified_token_and_future_cannot_call_broker_greeks(self):
        with patch("live_v7.angel_greeks.urllib.request.build_opener") as outbound:
            for token in ("000000","ABCDEF","444444"):
                with self.subTest(token=token),self.assertRaises(md.MarketDataError):
                    g.angel_selected_contract_greeks("verified-user",token,
                                           master_fetch=master,clock=CLOCK)
            outbound.assert_not_called()

    def test_missing_owner_and_session_blocks_before_broker_network(self):
        with patch("angel_gateway._owner_bound",return_value=False):
            with self.assertRaises(md.MarketDataError):
                g.angel_selected_contract_greeks("other","111111",
                                                  master_fetch=master,clock=CLOCK)
        with patch("angel_gateway._clean_session",return_value=None):
            with self.assertRaises(md.MarketDataError):
                g.angel_selected_contract_greeks("other","111111",
                                                  master_fetch=master,clock=CLOCK)

    def test_missing_broker_chain_or_duplicate_match_fails_closed(self):
        def bad(rows):
            return lambda req,timeout: MockQuote(json.dumps({"status":True,"data":rows}).encode())
        row=chain()["data"][0]
        for rows in ([],[row,row],[{**row,"strikePrice":"24900"}],
                     [{**row,"delta":"1.2"}],[{**row,"impliedVolatility":"NaN"}]):
            with self.subTest(rows=rows),self.assertRaises(md.MarketDataError):
                g.angel_selected_contract_greeks(
                    "verified-user","111111",master_fetch=master,greeks_fetch=bad(rows),
                    clock=CLOCK+len(str(rows))%4+20)  # separate time windows

    def test_http_greeks_separately_locked_by_default_and_wrong_origin(self):
        with patch.dict(os.environ,{"OPTIONX_V7_MARKETDATA_ANGEL_ENABLED":"1",
                                     "OPTIONX_V7_GREEKS_ANGEL_ENABLED":"0"}),\
            patch("market_api.angel_selected_contract_greeks") as reader:
            status,body,_=hit("GET","/api/v7/angel/greeks?token=111111")
            self.assertEqual(status,423)
            self.assertFalse(body["canSubmitOrder"])
            reader.assert_not_called()
        with patch.dict(os.environ,{"OPTIONX_V7_MARKETDATA_ANGEL_ENABLED":"1",
                                     "OPTIONX_V7_GREEKS_ANGEL_ENABLED":"1"}),\
            patch("market_api.angel_selected_contract_greeks") as reader:
            status,_,_=hit("GET","/api/v7/angel/greeks?token=111111",
                           origin="https://evil.example")
            self.assertEqual(status,403)
            status,_,_=hit("GET","/api/v7/angel/greeks?token=111111",user=None)
            self.assertEqual(status,401)
            reader.assert_not_called()

    def test_http_greeks_read_cannot_enable_order_even_with_both_flags_on(self):
        with patch.dict(os.environ,{"OPTIONX_V7_MARKETDATA_ANGEL_ENABLED":"1",
                                     "OPTIONX_V7_GREEKS_ANGEL_ENABLED":"1"}):
            status,body,_=hit("POST","/api/brokers/angel/orders",body={"ordertype":"LIMIT"})
            self.assertEqual(status,423)
            self.assertFalse(body["orderSent"])


if __name__=="__main__":
    unittest.main()
