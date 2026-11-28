"""Angel NFO metadata and LTP pilot: entirely offline/controlled tests."""
import io
import json
import os
import time
import unittest
from datetime import datetime,timezone
from unittest.mock import patch
from live_v7 import angel_marketdata as md
from live_v7.test_stoxkart_http import hit, STAGING

CLOCK=datetime(2026,11,24,7,0,tzinfo=timezone.utc).timestamp()
VALID=[
 {"token":"111111","symbol":"NIFTY26NOV2625000CE","name":"NIFTY","expiry":"26NOV2026",
  "strike":"2500000.000000","lotsize":"65","instrumenttype":"OPTIDX","exch_seg":"NFO","tick_size":"5.000000"},
 {"token":"222222","symbol":"NIFTY26NOV2625000PE","name":"NIFTY","expiry":"26NOV2026",
  "strike":"2500000.000000","lotsize":"65","instrumenttype":"OPTIDX","exch_seg":"NFO","tick_size":"5.000000"},
 {"token":"333333","symbol":"BANKNIFTY26NOV2655000CE","name":"BANKNIFTY","expiry":"26NOV2026",
  "strike":"5500000.000000","lotsize":"30","instrumenttype":"OPTIDX","exch_seg":"NFO","tick_size":"5.000000"},
 {"token":"444444","symbol":"NIFTY26NOV26FUT","name":"NIFTY","expiry":"26NOV2026",
  "strike":"-1.000000","lotsize":"65","instrumenttype":"FUTIDX","exch_seg":"NFO","tick_size":"5.000000"},
 {"token":"555555","symbol":"NIFTY26NOV2625000CE","name":"NIFTY","expiry":"26NOV2026",
  "strike":"2500000.000000","lotsize":"65","instrumenttype":"OPTIDX","exch_seg":"NSE","tick_size":"5.000000"},
]
class MockMaster(io.BytesIO):
    def __enter__(self): return self
    def __exit__(self,*_): self.close()
def master(*_args,**_kwargs):
    return MockMaster(json.dumps(VALID).encode())
class MockQuote(io.BytesIO):
    status=200
    def __enter__(self): return self
    def __exit__(self,*_): self.close()

class AngelMarketDataTests(unittest.TestCase):
    def setUp(self):
        with md._LOCK:
            md._CACHE.update(loaded=0,contracts={},asof="")
            md._LAST_QUOTE.clear()
            md._LAST_CANDLES.clear()
        self.clean=patch("live_v7.angel_marketdata.angel_gateway._clean_session",
                         return_value={"apiKey":"fake-public-api-key","jwt":"x"*50})
        self.owner=patch("live_v7.angel_marketdata.angel_gateway._owner_bound",return_value=True)
        self.clean.start();self.owner.start()
        self.addCleanup(self.clean.stop);self.addCleanup(self.owner.stop)

    def test_stream_master_chunks_and_reject_truncated(self):
        source=json.dumps(VALID).encode()
        self.assertEqual(len(list(md._stream_json_array(io.BytesIO(source)))),5)
        with self.assertRaises(md.MarketDataError):
            list(md._stream_json_array(io.BytesIO(source[:-1])))

    def test_filter_nfo_master_normalizes_strike_lot_tick_expiry(self):
        out=md.list_contracts("owner","NIFTY","CE",strike="25000",fetch=master,clock=CLOCK)
        self.assertEqual(out["expiry"],"2026-11-26")
        self.assertEqual(out["contracts"][0]["token"],"111111")
        self.assertEqual(out["contracts"][0]["strike"],25000)
        self.assertEqual(out["contracts"][0]["lotSize"],65)
        self.assertEqual(out["contracts"][0]["tickSize"],0.05)
        self.assertFalse(out["liveExecutionEnabled"])
        self.assertFalse(out["canSubmitOrder"])

    def test_other_market_and_future_are_separated(self):
        future=md.list_contracts("owner","NIFTY","FUT",fetch=master,clock=CLOCK)
        self.assertEqual(future["contracts"][0]["instrumentType"],"FUTIDX")
        self.assertIsNone(future["contracts"][0]["strike"])
        b=md.list_contracts("owner","BANKNIFTY","CE",fetch=master,clock=CLOCK)
        self.assertEqual(b["contracts"][0]["token"],"333333")

    def test_owner_must_be_valid_before_even_loading_public_master(self):
        with patch("live_v7.angel_marketdata.angel_gateway._owner_bound",return_value=False):
            with patch("live_v7.angel_marketdata._get_master") as fetch:
                with self.assertRaises(md.MarketDataError) as c:
                    md.list_contracts("not-owner","NIFTY","CE")
                self.assertEqual(c.exception.code,"OWNER_NOT_VERIFIED")
                fetch.assert_not_called()

    def test_missing_session_rejected_before_master_fetch(self):
        with patch("live_v7.angel_marketdata.angel_gateway._clean_session",return_value=None):
            with patch("live_v7.angel_marketdata._get_master") as fetch:
                with self.assertRaises(md.MarketDataError) as c:
                    md.list_contracts("owner","NIFTY","CE")
                self.assertEqual(c.exception.code,"ANGEL_SESSION_EXPIRED")
                fetch.assert_not_called()

    def test_fake_unverified_quote_token_can_never_contact_broker(self):
        with patch("live_v7.angel_marketdata.angel_client_identity_headers",create=True),\
             patch("live_v7.angel_marketdata.urllib.request.build_opener") as transport:
            with self.assertRaises(md.MarketDataError) as c:
                md.quote_ltp("owner","999999",master_fetch=master,clock=CLOCK)
            self.assertEqual(c.exception.code,"UNVERIFIED_INSTRUMENT_TOKEN")
            transport.assert_not_called()

    def test_real_contract_ltp_requires_matching_token_and_never_enters_order_gateway(self):
        def getter(req,timeout):
            self.assertEqual(req.get_method(),"POST")
            self.assertEqual(req.full_url,md.LTP_URL)
            payload=json.loads(req.data)
            self.assertEqual(payload,{"exchange":"NFO","tradingsymbol":"NIFTY26NOV2625000CE",
                                      "symboltoken":"111111"})
            return MockQuote(json.dumps({"status":True,"data":{
                    "exchange":"NFO","tradingsymbol":"NIFTY26NOV2625000CE",
                    "symboltoken":"111111","ltp":155.75}}).encode())
        with patch("angel_gateway.angel_client_identity_headers",return_value={}):
            r=md.quote_ltp("owner","111111",master_fetch=master,quote_fetch=getter,clock=CLOCK)
        self.assertEqual(r["ltp"],155.75)
        self.assertFalse(r["exchangeTimestampVerified"])
        self.assertFalse(r["quoteFreshnessVerified"])
        self.assertFalse(r["executionPriceVerified"])
        self.assertFalse(r["liveExecutionEnabled"])
        self.assertFalse(r["orderExecutionEnabled"])
        self.assertFalse(r["canSubmitOrder"])

    def test_mismatched_quote_token_fails_closed(self):
        def getter(req,timeout):
            return MockQuote(json.dumps({"status":True,"data":{
                    "exchange":"NFO","tradingsymbol":"NIFTY26NOV2625000CE",
                    "symboltoken":"888888","ltp":123}}).encode())
        with patch("angel_gateway.angel_client_identity_headers",return_value={}):
            with self.assertRaises(md.MarketDataError) as c:
                md.quote_ltp("owner","111111",master_fetch=master,quote_fetch=getter,clock=CLOCK)
        self.assertEqual(c.exception.code,"BROKER_QUOTE_CONTRACT_MISMATCH")

    def test_repeated_quote_poll_rate_limit(self):
        with patch("angel_gateway.angel_client_identity_headers",return_value={}):
            def getter(req,timeout):
                return MockQuote(json.dumps({"status":True,"data":{
                        "exchange":"NFO","tradingsymbol":"NIFTY26NOV2625000CE",
                        "symboltoken":"111111","ltp":99}}).encode())
            md.quote_ltp("owner","111111",master_fetch=master,quote_fetch=getter,clock=CLOCK)
            with self.assertRaises(md.MarketDataError) as c:
                md.quote_ltp("owner","111111",master_fetch=master,quote_fetch=getter,clock=CLOCK)
        self.assertEqual(c.exception.code,"QUOTE_POLL_RATE_LIMIT")

    def test_15m_contract_candles_validate_token_interval_ohlc_and_no_fill(self):
        sample=[["2026-11-24T09:15:00+05:30",101,106,100,104,12345],
                ["2026-11-24T09:30:00+05:30",104,107,102,106,4321]]
        def candles(req,timeout):
            self.assertEqual(req.get_method(),"POST")
            self.assertEqual(req.full_url,md.CANDLES_URL)
            self.assertEqual(json.loads(req.data)["interval"],"FIFTEEN_MINUTE")
            self.assertEqual(json.loads(req.data)["symboltoken"],"111111")
            return MockQuote(json.dumps({"status":True,"data":sample}).encode())
        with patch("angel_gateway.angel_client_identity_headers",return_value={}):
            out=md.historical_15m("owner","111111",days=3,master_fetch=master,
                                  candle_fetch=candles,clock=CLOCK)
        self.assertEqual(out["barCount"],2)
        self.assertEqual(out["timeframe"],"15m")
        self.assertEqual(out["bars"][0]["open"],101)
        self.assertEqual(out["bars"][1]["close"],106)
        self.assertFalse(out["fillPricesVerified"])
        self.assertFalse(out["liveExecutionEnabled"])
        self.assertFalse(out["canSubmitOrder"])

    def test_15m_rejects_unverified_contract_without_broker_network(self):
        with patch("live_v7.angel_marketdata.urllib.request.build_opener") as network:
            with self.assertRaises(md.MarketDataError) as ctx:
                md.historical_15m("owner","999999",master_fetch=master,clock=CLOCK)
            self.assertEqual(ctx.exception.code,"UNVERIFIED_INSTRUMENT_TOKEN")
            network.assert_not_called()

    def test_15m_incomplete_latest_bar_excluded(self):
        sample=[["2026-11-24T12:30:00+05:30",101,110,100,102,88]]
        def candles(req,timeout):
            return MockQuote(json.dumps({"status":True,"data":sample}).encode())
        with patch("angel_gateway.angel_client_identity_headers",return_value={}):
            out=md.historical_15m("owner","111111",days=3,master_fetch=master,
                                  candle_fetch=candles,clock=CLOCK)
        self.assertEqual(out["barCount"],0)

    def test_15m_invalid_ohlc_rejected_before_csv(self):
        sample=[["2026-11-24T09:15:00+05:30",101,98,100,104,0]]
        def candles(req,timeout):
            return MockQuote(json.dumps({"status":True,"data":sample}).encode())
        with patch("angel_gateway.angel_client_identity_headers",return_value={}):
            with self.assertRaises(md.MarketDataError) as ctx:
                md.historical_15m("owner","111111",days=3,master_fetch=master,
                                  candle_fetch=candles,clock=CLOCK)
        self.assertEqual(ctx.exception.code,"BROKER_CANDLES_INVALID_OHLC")

    def test_15m_bad_window_never_contacts_master_or_broker(self):
        with patch("live_v7.angel_marketdata._get_master") as lookup:
            with self.assertRaises(md.MarketDataError) as ctx:
                md.historical_15m("owner","111111",days=30,clock=CLOCK)
        self.assertEqual(ctx.exception.code,"INVALID_CANDLE_WINDOW")
        lookup.assert_not_called()

    def test_http_routes_disabled_wrong_origin_and_unauthenticated(self):
        with patch.dict(os.environ,{"OPTIONX_V7_MARKETDATA_ANGEL_ENABLED":"0"}),\
             patch("market_api.angel_list_contracts") as fetch:
            status,resp,_=hit("GET","/api/v7/angel/contracts?market=NIFTY&side=CE")
            self.assertEqual(status,423)
            fetch.assert_not_called()
        with patch.dict(os.environ,{"OPTIONX_V7_MARKETDATA_ANGEL_ENABLED":"1"}),\
             patch("market_api.angel_list_contracts") as fetch:
            status,_,_=hit("GET","/api/v7/angel/contracts?market=NIFTY&side=CE",
                           origin="https://evil.example")
            self.assertEqual(status,403)
            status,_,_=hit("GET","/api/v7/angel/contracts?market=NIFTY&side=CE",user=None)
            self.assertEqual(status,401)
            fetch.assert_not_called()

    def test_http_no_orders_even_with_marketdata_flag_on(self):
        with patch.dict(os.environ,{"OPTIONX_V7_MARKETDATA_ANGEL_ENABLED":"1"}):
            status,body,_=hit("POST","/api/brokers/angel/orders",body={"side":"BUY"})
            self.assertEqual(status,423)
            self.assertFalse(body["orderSent"])

if __name__=="__main__":
    unittest.main()
