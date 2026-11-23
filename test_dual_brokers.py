"""Offline regression tests for public two-broker adapter (never send orders)."""
import json
import unittest
from unittest.mock import patch
from dual_brokers import (
    catalog, _symbol, _fetch_delta, delta_product, delta_products, delta_candles,
)

class Response:
    status = 200
    def __init__(self, data): self.data = json.dumps(data).encode()
    def __enter__(self): return self
    def __exit__(self, *args): return False
    def read(self, cap): return self.data[:cap]

PRODUCT = dict(id=27,symbol='BTCUSD',contract_type='perpetual_futures',state='live',
               trading_status='operational',tick_size='0.5',contract_value='0.001',
               contract_unit_currency='BTC')

class TestDualBrokers(unittest.TestCase):
    def test_exact_broker_market_routes(self):
        cs = catalog()
        self.assertEqual(cs['brokers'][0]['markets'], ['NIFTY','BANKNIFTY'])
        self.assertEqual(cs['brokers'][1]['markets'], ['BTC'])
        self.assertFalse(cs['liveOrdersEnabled'])
        self.assertFalse(cs['brokerCredentialsStored'])
    def test_symbol_allowlist_and_no_ssrf(self):
        for bad in ('BTC/USD','https://evil.com','../../etc/passwd','BTCUSD?x=1','ETHUSD','',None):
            with self.subTest(bad=bad),self.assertRaises(ValueError): _symbol(bad)
        self.assertEqual(_symbol('btcUsd'),'BTCUSD')
    def test_only_get_fixed_delta_host(self):
        def capture(req, timeout):
            self.assertTrue(req.full_url.startswith('https://api.india.delta.exchange/v2/'))
            self.assertEqual(req.get_method(),'GET')
            self.assertLessEqual(timeout, 9)
            return Response({'success': True, 'result': []})
        self.assertEqual(_fetch_delta('/v2/products', fetch=capture)['result'], [])
        with self.assertRaises(ValueError): _fetch_delta('/foo', fetch=capture)
    def test_delta_contract_sanitized_and_active(self):
        def fake(path, fetch=None):
            self.assertEqual(path, '/v2/products/BTCUSD')
            return {'success':True, 'result':PRODUCT}
        with patch('dual_brokers._fetch_delta',side_effect=fake):
            p=delta_product('BTCUSD')
        self.assertTrue(p['currentlyTradable']); self.assertEqual(p['contractValue'],'0.001')
        self.assertNotIn('api_key', str(p).lower())
    def test_contract_list_only_btc_and_first_page_notice(self):
        with patch('dual_brokers._fetch_delta',return_value={'success':True,'result':[
            PRODUCT, {**PRODUCT,'id':1,'symbol':'ETHUSD'}, {**PRODUCT,'id':2,'symbol':'C-BTC-60000-281126','contract_type':'call_options'}
        ]}):
            p=delta_products('option')
        self.assertEqual(p['returned'],1)
        self.assertTrue(p['firstPageOnly'])
        with self.assertRaises(ValueError): delta_products('spot')
    def test_candles_completed_and_deduped(self):
        now=1_730_000_000; step=900; end=now-now%step
        candles=[]
        for i in range(60):
            timestamp=end-(60-i)*step
            candles.append(dict(time=timestamp,open=100,high=105,low=99,close=102,volume=5))
        candles.append({**candles[-1], 'close':103})  # same timestamp replacement
        candles.append(dict(time=end,open=100,high=105,low=99,close=101,volume=2))  # incomplete
        with patch('dual_brokers._fetch_delta',return_value={'success':True,'result':candles}):
            r=delta_candles('BTCUSD','15m',now=now)
        self.assertEqual(r['feedType'],'delta-derivatives')
        self.assertEqual(len(r['bars']),60)
        self.assertEqual(r['bars'][-1]['close'],103)
        self.assertLess(r['bars'][-1]['time'],end*1000)
    def test_reject_tiny_or_bad_data(self):
        with patch('dual_brokers._fetch_delta',return_value={'success':True,'result':[]}):
            with self.assertRaisesRegex(ValueError,'insufficient'):delta_candles('BTCUSD','5m',now=1_730_000_000)
        with self.assertRaises(ValueError):delta_candles('ETHUSD','5m')
        with self.assertRaises(ValueError):delta_candles('BTCUSD','2m')

if __name__=='__main__': unittest.main()
