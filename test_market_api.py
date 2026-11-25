import unittest
from unittest.mock import patch
from datetime import datetime
from zoneinfo import ZoneInfo
from market_api import _valid, _aggregate_4h, get_candles

class FeedTests(unittest.TestCase):
    def test_mobile_public_cors_least_privilege(self):
        from market_api import _permitted_origin, V8_MOBILE_PUBLIC_ORIGIN
        self.assertTrue(_permitted_origin(V8_MOBILE_PUBLIC_ORIGIN, '/health'))
        self.assertTrue(_permitted_origin(V8_MOBILE_PUBLIC_ORIGIN, '/api/candles'))
        for path in ('/api/live/status','/api/v7/angel/positions',
                     '/api/brokers/angel/connect','/api/live/orders',
                     '/api/v7/readiness','/api/brokers/angel/status'):
            self.assertFalse(_permitted_origin(V8_MOBILE_PUBLIC_ORIGIN,path))
        self.assertFalse(_permitted_origin('https://evil.example','/api/candles'))

    def test_v7_staging_paper_public_endpoints_only(self):
        from market_api import _permitted_origin, V7_STAGING_ORIGIN
        with patch.dict('os.environ', {'OPTIONX_V7_STAGING_CORS': '0'}):
            self.assertTrue(_permitted_origin(V7_STAGING_ORIGIN, '/health'))
            self.assertTrue(_permitted_origin(V7_STAGING_ORIGIN, '/api/candles'))
            for private in ('/api/v7/angel/positions',
                            '/api/v7/angel/orderbook',
                            '/api/v7/angel/auto-atm',
                            '/api/live/status'):
                self.assertFalse(_permitted_origin(V7_STAGING_ORIGIN, private))
        with patch.dict('os.environ', {'OPTIONX_V7_STAGING_CORS': '1'}):
            self.assertTrue(_permitted_origin(V7_STAGING_ORIGIN, '/api/v7/angel/positions'))
        self.assertFalse(_permitted_origin('https://untrusted.example', '/api/candles'))

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

# Also run the dual-broker public adapter regression tests in Render builds.
from test_dual_brokers import TestDualBrokers

# Render Python build imports these additional offline verification tests.
from test_angel_gateway import TestAngelGateway

# Owner-authenticated Angel Option Greeks read-only adapter mock tests.
from live_v7.test_angel_greeks import AngelGreeksReadOnlyTests

# Owner-gated ATM automation remains paper preview only.
from live_v7.test_angel_auto_atm import AngelAutoATMTests

# Build-gate: validate offline Angel order request contracts; NEVER transmit them.
from live_v7.test_angel_order_contracts import AngelOrderContractsTests

# No-network owner-only egress audit regression; never broker/order calls.
from live_v7.test_egress_diagnostic import EgressDiagnosticTests

from live_v7.test_angel_greeks_order_bridge import GreeksOrderBridgeTests

from live_v7.test_angel_execution_transport import AngelExecutionTransportTests

from live_v7.test_angel_aws_release_gate import AwsReleaseGateTests

from live_v7.test_angel_books_readonly import AngelBooksReadOnlyTests

from live_v7.test_aws_shadow_observer import AwsShadowObserverTests

from live_v7.test_aws_angel_owner_reader import AwsAngelOwnerReaderTests

from live_v7.test_lifecycle_rehearsal_v18 import V18LifecycleTests

from live_v7.test_aws_pg_recovery_v19 import V19PostgresRecoveryTests

from live_v7.test_aws_pg_safe_diag_v20 import V20SafeDiagnosticsTests

from live_v7.test_broker_evidence_v21 import V21BrokerEvidenceTests

from live_v7.test_aws_runtime_evidence_v22 import V22RuntimeEvidenceTests

from live_v7.test_execution_coordinator_v23 import V23ExecutionCoordinatorTests

from live_v7.test_prelive_gate_v24 import V24PreliveGateTests

from live_v7.test_pg_atomic_reservation_v25 import V25PostgresStoppedReservationTests
