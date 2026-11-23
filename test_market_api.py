import unittest
from unittest.mock import patch
from datetime import datetime
from zoneinfo import ZoneInfo
from market_api import _valid, _aggregate_4h, get_candles

class FeedTests(unittest.TestCase):
    def test_invalid_ohlc(self):
        self.assertIsNone(_valid(100, 90, 92, 98, 101))
        self.assertIsNone(_valid(100, None, 110, 80, 101))
        self.assertEqual(_valid(100, 100, 105, 99, 102)['close'], 102)
    def test_market_timeframe_allowlist(self):
        with self.assertRaises(ValueError): get_candles('EVIL','1m')
        with self.assertRaises(ValueError): get_candles('BTC','bad')
    def test_kraken_converts_and_sorts(self):
        data={'error':[],'result':{'XXBTZUSD':[[i*60, str(100+i),str(101+i),str(99+i),str(100.5+i),'0','2', 4] for i in range(40)],'last':60}}
        with patch('market_api._fetch_json',return_value=data):
            r=get_candles('BTC','1m')
        self.assertEqual(len(r['bars']),40)
        self.assertEqual(r['bars'][0]['time'],0)
        self.assertEqual(r['feedType'],'spot')
    def test_yahoo_converts(self):
        p={'chart':{'error':None,'result':[{'timestamp':[i*900 for i in range(40)],'indicators':{'quote':[{'open':[100]*40,'high':[102]*40,'low':[99]*40,'close':[101]*40,'volume':[0]*40}]}}]}}
        with patch('market_api._fetch_json',return_value=p): r=get_candles('NIFTY','15m')
        self.assertEqual(len(r['bars']),40)
        self.assertEqual(r['feedType'],'indicative-index')
    def test_4h_aggregation(self):
        t=int(datetime(2026,1,5,9,0,tzinfo=ZoneInfo('Asia/Kolkata')).timestamp())*1000
        bars=[{'time':t+i*3600000,'open':100+i,'high':103+i,'low':99+i,'close':101+i,'volume':2} for i in range(4)]
        group=_aggregate_4h(bars)
        self.assertEqual(len(group),2)
        self.assertEqual(group[0]['volume'],6)

if __name__ == '__main__': unittest.main()

# Safe live gateway regression cases also run in Render
from test_live_gateway import TestLockedGateway
