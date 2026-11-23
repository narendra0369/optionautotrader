import unittest
import json
from io import BytesIO
from live_gateway import capabilities, preflight, status, hard_block_order, user_from_token

USER = '123e4567-e89b-12d3-a456-426614174000'
BASE = dict(broker='Angel', market='NIFTY', strategyId=1, side='BUY', orderType='LIMIT',
            contractSymbol='NIFTY26NOV26000CE', quantity=65, limitPrice=102.5,
            riskBudget=300, dailyStop=600, maxTrades=2)

class GoodResponse:
    status = 200
    def __enter__(self): return self
    def __exit__(self, *args): return False
    def read(self, n): return json.dumps({'id': USER}).encode()

class TestLockedGateway(unittest.TestCase):
    def test_tokens_are_verified_not_decoded(self):
        self.assertIsNone(user_from_token(None))
        self.assertIsNone(user_from_token('Bearer junk'))
        self.assertEqual(user_from_token('Bearer ' + 'a'*30, fetch=lambda req, timeout: GoodResponse()), USER)
        self.assertIsNone(user_from_token('Bearer ' + 'a'*30, fetch=lambda req, timeout: (_ for _ in ()).throw(OSError('offline'))))
    def test_never_enables_order(self):
        self.assertFalse(capabilities()['orderExecutionEnabled'])
        self.assertFalse(status(USER)['liveExecutionEnabled'])
        self.assertFalse(hard_block_order()['orderSent'])
        v = preflight(BASE, USER)
        self.assertFalse(v['canSubmitOrder'])
        self.assertGreaterEqual(v['blockedCount'], 8)
        self.assertEqual(v['preview']['estimatedNotional'], 6662.5)
    def test_rejects_wrong_market_broker(self):
        with self.assertRaisesRegex(ValueError, 'not mapped'): preflight({**BASE,'broker':'Delta'},USER)
    def test_rejects_market_orders(self):
        with self.assertRaisesRegex(ValueError,'LIMIT'): preflight({**BASE,'orderType':'MARKET'},USER)
    def test_rejects_invalid_numbers(self):
        for qty in (0,-1,True,1.5,float('nan'),float('inf')):
            with self.assertRaises(ValueError): preflight({**BASE, 'quantity':qty},USER)
    def test_rejects_bad_limits(self):
        with self.assertRaises(ValueError): preflight({**BASE,'riskBudget':700,'dailyStop':600},USER)
    def test_rejects_proxy(self):
        v=preflight({**BASE,'contractSymbol':'NIFTY'},USER)
        self.assertEqual(v['checks'][-1]['code'],'MISSING_CONTRACT')
    def test_every_market_valid_preview(self):
        for broker, market in [('Zerodha','BANKNIFTY'),('Dhan','NIFTY'),('Delta','BTC')]:
            v=preflight({**BASE,'broker':broker,'market':market},USER)
            self.assertFalse(v['canSubmitOrder'])
    def test_no_owner_by_default(self):
        import os
        v=status(USER)
        self.assertFalse(v['brokerConnected'])
        self.assertEqual(v['realOrderCount'],0)

if __name__ == '__main__': unittest.main()
