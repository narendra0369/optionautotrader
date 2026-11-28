"""Offline-only Angel index EMA/ORB signal -> nearest ATM premium & Greeks tests."""
from datetime import datetime,timedelta,timezone,time
from zoneinfo import ZoneInfo
from unittest.mock import patch
import json
import unittest

from live_v7 import angel_auto_atm as auto
from live_v7 import angel_marketdata as md
from live_v7 import angel_greeks as ag
from live_v7.test_angel_marketdata import master,MockQuote
from live_v7.test_stoxkart_http import hit
from live_v7.angel_marketdata import MarketDataError

IST=ZoneInfo("Asia/Kolkata")
NOW=datetime(2026,11,25,12,46,tzinfo=IST)
BARS=[]


def candle(at,close,high=None,low=None):
    v=float(close)
    return [at.isoformat(),v,float(high if high is not None else v+1),
            float(low if low is not None else v-1),v,100]


for i in range(25):
    BARS.append(candle(datetime(2026,11,24,9,15,tzinfo=IST)+timedelta(minutes=15*i),100))
for i in range(15):
    at=datetime(2026,11,25,9,15,tzinfo=IST)+timedelta(minutes=15*i)
    # last 12:45? i=14 is 12:45, not complete by 12:46; i=13=12:30
    value=103 if i==13 else 100
    BARS.append(candle(at,value,high=104 if i==13 else 101,low=99))


def network(req,timeout):
    payload=json.loads(req.data)
    if req.full_url==auto.CANDLE_URL:
        assert payload["symboltoken"]=="99926000"
        assert payload["interval"]=="FIFTEEN_MINUTE"
        return MockQuote(json.dumps({"status":True,"data":BARS}).encode())
    if req.full_url==auto.LTP_URL:
        assert payload["exchange"]=="NSE"
        assert payload["symboltoken"]=="99926000"
        return MockQuote(json.dumps({"status":True,"data":{
           "exchange":"NSE","tradingsymbol":"Nifty 50","symboltoken":"99926000",
           "ltp":25051}}).encode())
    raise AssertionError("Unknown broker request")


def option_quote(req,timeout):
    assert req.full_url==md.LTP_URL
    assert json.loads(req.data)["symboltoken"]=="111111"
    return MockQuote(json.dumps({"status":True,"data":{
      "exchange":"NFO","tradingsymbol":"NIFTY26NOV2625000CE",
      "symboltoken":"111111","ltp":100}}).encode())


def greeks(req,timeout):
    assert req.full_url==ag._GREEKS_URL
    assert json.loads(req.data)=={"name":"NIFTY","expirydate":"26NOV2026"}
    return MockQuote(json.dumps({"status":True,"data":[{
      "name":"NIFTY","expiry":"26NOV2026","strikePrice":"25000","optionType":"CE",
      "delta":"0.5","gamma":"0.001","theta":"-4","vega":"2","impliedVolatility":"20"
    }]}).encode())


class AngelAutoATMTests(unittest.TestCase):
    def setUp(self):
        with md._LOCK:
            md._CACHE.update(loaded=0,contracts={},asof="")
            md._LAST_QUOTE.clear()
        with ag._LOCK: ag._LAST.clear()
        with auto._LOCK: auto._LAST.clear()
        self.owner=patch("angel_gateway._owner_bound",return_value=True)
        self.session=patch("angel_gateway._clean_session",
            return_value={"apiKey":"fake_api_key","jwt":"x"*60})
        self.headers=patch("angel_gateway.angel_client_identity_headers",return_value={})
        for p in (self.owner,self.session,self.headers):
            p.start();self.addCleanup(p.stop)

    def test_orb_next_15m_signal_creates_nearest_atm_paper_preview(self):
        # first 6×15m bars = 18×5m opening range; cross after 12:30 close
        out=auto.angel_auto_atm_readonly(
           "owner_001","NIFTY","ORB18",now=NOW,
           index_quote_fetch=network,index_candle_fetch=network,
           master_fetch=master,option_quote_fetch=option_quote,
           greek_fetch=greeks)
        self.assertEqual(out["status"],"READONLY_ATM_PREVIEW_READY_NOT_ORDER_ELIGIBLE")
        self.assertEqual(out["signal"]["side"],"CE")
        self.assertEqual(out["selectedContract"]["token"],"111111")
        self.assertEqual(out["selectedContract"]["premium"],100)
        self.assertEqual(out["exitPlan"]["orderTypes"]["entry"],"LIMIT")
        self.assertEqual(out["exitPlan"]["orderTypes"]["stop"],"STOPLOSS_LIMIT")
        self.assertEqual(out["dailyEntryHardCap"],2)
        self.assertIsNone(out["dailyEntryCount"])
        self.assertFalse(out["dailyEntryCountVerified"])
        self.assertIsNone(out["fillETASeconds"])
        self.assertFalse(out["liveOrdersEnabled"])
        self.assertFalse(out["canSubmitOrder"])

    def test_no_signal_never_calls_index_quote_or_option_price(self):
        # Stable flat candles -> no breakout signal, no fabricated premiums
        bars=[candle(datetime(2026,11,24,9,15,tzinfo=IST)+timedelta(minutes=15*i),100) for i in range(25)]
        bars +=[candle(datetime(2026,11,25,9,15,tzinfo=IST)+timedelta(minutes=15*i),100) for i in range(15)]
        def stable(req,timeout):
            return MockQuote(json.dumps({"status":True,"data":bars}).encode())
        with patch("live_v7.angel_auto_atm._quote_spot") as q:
            out=auto.angel_auto_atm_readonly("owner_001","NIFTY","ORB18",now=NOW,
                    index_candle_fetch=stable)
            self.assertEqual(out["status"],"WAITING_FOR_NEW_15M_STRATEGY_SIGNAL")
            self.assertIsNone(out["selectedContract"])
            q.assert_not_called()

    def test_wrong_index_identity_rejected(self):
        def wrong(req,timeout):
            if req.full_url==auto.LTP_URL:
                return MockQuote(json.dumps({"status":True,"data":{
                  "exchange":"NSE","tradingsymbol":"Nifty Bank",
                  "symboltoken":"99926009","ltp":25051}}).encode())
            return network(req,timeout)
        with self.assertRaises(MarketDataError) as c:
            auto.angel_auto_atm_readonly("owner_001","NIFTY","ORB18",now=NOW,
                 index_quote_fetch=wrong,index_candle_fetch=network,
                 master_fetch=master)
        self.assertEqual(c.exception.code,"BROKER_INDEX_TOKEN_OR_SYMBOL_MISMATCH")

    def test_stale_signal_does_not_get_atm_quote(self):
        old=NOW+timedelta(hours=1)
        with patch("live_v7.angel_auto_atm._quote_spot") as q:
            result=auto.angel_auto_atm_readonly("owner_001","NIFTY","ORB18",now=old,
                         index_candle_fetch=network)
            self.assertEqual(result["status"],"WAITING_FOR_NEW_15M_STRATEGY_SIGNAL")
            q.assert_not_called()

    def test_bad_request_fail_before_broker(self):
        with patch("live_v7.angel_auto_atm._get_json") as fetch:
            with self.assertRaises(MarketDataError):
                auto.angel_auto_atm_readonly("owner_001","BTC","ORB18",now=NOW)
            with self.assertRaises(MarketDataError):
                auto.angel_auto_atm_readonly("owner_001","NIFTY","fake",now=NOW)
            fetch.assert_not_called()

    def test_no_trading_from_endpoint_before_explicit_readonly_flags(self):
        import os
        with patch.dict(os.environ,{
             "OPTIONX_V7_AUTO_ATM_READONLY_ENABLED":"0",
             "OPTIONX_V7_MARKETDATA_ANGEL_ENABLED":"1",
             "OPTIONX_V7_GREEKS_ANGEL_ENABLED":"1"}),\
             patch("market_api.angel_auto_atm_readonly") as engine:
            status,data,_=hit("GET","/api/v7/angel/auto-atm?market=NIFTY&strategy=ORB18")
            self.assertEqual(status,423)
            self.assertFalse(data["canSubmitOrder"])
            engine.assert_not_called()

    def test_unauthorized_and_wrong_origin_blocked(self):
        import os
        with patch.dict(os.environ,{
             "OPTIONX_V7_AUTO_ATM_READONLY_ENABLED":"1",
             "OPTIONX_V7_MARKETDATA_ANGEL_ENABLED":"1",
             "OPTIONX_V7_GREEKS_ANGEL_ENABLED":"1"}),\
             patch("market_api.angel_auto_atm_readonly") as engine:
            s,_,_=hit("GET","/api/v7/angel/auto-atm?market=NIFTY&strategy=ORB18",
                  origin="https://evil.example")
            self.assertEqual(s,403)
            s,_,_=hit("GET","/api/v7/angel/auto-atm?market=NIFTY&strategy=ORB18",user=None)
            self.assertEqual(s,401)
            engine.assert_not_called()

    def test_no_place_order_even_when_preview_flags_enabled(self):
        import os
        with patch.dict(os.environ,{
             "OPTIONX_V7_AUTO_ATM_READONLY_ENABLED":"1",
             "OPTIONX_V7_MARKETDATA_ANGEL_ENABLED":"1",
             "OPTIONX_V7_GREEKS_ANGEL_ENABLED":"1"}):
            status,result,_=hit("POST","/api/live/orders",body={"orderType":"LIMIT"})
            self.assertEqual(status,423)
            self.assertFalse(result["orderSent"])


if __name__=="__main__":
    unittest.main()
