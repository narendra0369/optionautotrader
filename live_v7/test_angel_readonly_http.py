"""V7 Angel GET-only HTTP safety regression. No real broker, sockets or credentials.

Tests are run in the staging Render build gate. Every account snapshot
must be restricted by OptionX auth, exact trusted staging origin, server flag,
and the owner-bound temporary Angel verification established by the bridge.
"""
from __future__ import annotations
import os
import unittest
from unittest.mock import patch
from live_v7.test_stoxkart_http import hit, STAGING
from live_v7.read_only_bridge import ReadOnlyBridgeError

POSITIONS='/api/v7/angel/positions'
ORDERS='/api/v7/angel/orderbook'
OFF={'OPTIONX_V7_READONLY_ANGEL_ENABLED':'0'}
ON={'OPTIONX_V7_READONLY_ANGEL_ENABLED':'1'}
SNAPSHOT={
    'broker':'Angel','resource':'positions',
    'records':[{'symbol':'NIFTY27NOV26CE','exchange':'NFO','instrumentToken':'safe-token',
                'net_quantity':2}],
    'recordCount':1,'trustedAccount':'OWNER_PROFILE_MATCHED',
    'liveExecutionEnabled':False,'orderExecutionEnabled':False,'canSubmitOrder':False,
    'quoteAndContractMasterVerified':False,
}

class AngelReadonlyHttpTests(unittest.TestCase):
    def test_disabled_flag_must_return_423_without_broker_call(self):
        with patch.dict(os.environ,OFF), patch('market_api.angel_owner_snapshot') as reader:
            code,body,_=hit('GET',POSITIONS)
        self.assertEqual(code,423)
        self.assertFalse(body['liveExecutionEnabled'])
        reader.assert_not_called()

    def test_wrong_origin_always_denied_even_with_feature_flag(self):
        with patch.dict(os.environ,ON), patch('market_api.angel_owner_snapshot') as reader:
            code,body,_=hit('GET',POSITIONS,origin='https://unknown.example')
        self.assertEqual(code,403)
        reader.assert_not_called()

    def test_production_origin_cannot_call_staging_private_snapshot(self):
        with patch.dict(os.environ,ON), patch('market_api.angel_owner_snapshot') as reader:
            code,body,_=hit('GET',ORDERS,origin='https://optionx-200k-strategy-lab.onrender.com')
        self.assertEqual(code,403)
        reader.assert_not_called()

    def test_requires_optionx_jwt_even_if_flag_on(self):
        with patch.dict(os.environ,ON), patch('market_api.angel_owner_snapshot') as reader:
            code,body,_=hit('GET',ORDERS,user=None)
        self.assertEqual(code,401)
        reader.assert_not_called()

    def test_correct_staging_and_owner_return_only_sanitized_readonly_records(self):
        with patch.dict(os.environ,ON), patch('market_api.angel_owner_snapshot',return_value=SNAPSHOT) as reader:
            code,body,headers=hit('GET',POSITIONS,user='verified-owner')
        self.assertEqual(code,200)
        reader.assert_called_once_with(
            verified_optionx_user_id='verified-owner',resource='positions',
            server_feature_flag_enabled=True)
        self.assertFalse(body['canSubmitOrder'])
        self.assertIs(body['liveExecutionEnabled'],False)
        self.assertIs(body['orderExecutionEnabled'],False)
        self.assertEqual(body['records'][0]['net_quantity'],2)
        self.assertEqual(headers.get('Access-Control-Allow-Origin'),STAGING)
        self.assertNotIn('apiKey',str(body))
        self.assertNotIn('jwt',str(body).lower())

    def test_owner_expired_session_is_never_displayed_as_empty_positions(self):
        with patch.dict(os.environ,ON), patch('market_api.angel_owner_snapshot',
                                               side_effect=ReadOnlyBridgeError('expired')):
            code,body,_=hit('GET',POSITIONS,user='verified-owner')
        self.assertEqual(code,503)
        self.assertNotIn('expired',str(body))
        self.assertFalse(body['liveExecutionEnabled'])

    def test_safe_diagnostic_code_reaches_owner_without_private_broker_text(self):
        with patch.dict(os.environ,ON), patch(
            'market_api.angel_owner_snapshot',
            side_effect=ReadOnlyBridgeError('sensitive account details', 'BROKER_AUTH_REJECTED')
        ):
            code, body, _ = hit('GET',POSITIONS)
        self.assertEqual(code,503)
        self.assertEqual(body['diagnosticCode'],'BROKER_AUTH_REJECTED')
        self.assertFalse(body['canSubmitOrder'])
        self.assertFalse(body['liveExecutionEnabled'])
        self.assertNotIn('sensitive',str(body))

    def test_readonly_orderbook_status_including_unknown_is_not_an_order_approval(self):
        book={**SNAPSHOT,'resource':'orderbook','records':[
            {'symbol':'NIFTY27NOV26CE','exchange':'NFO','side':'BUY','quantity':25,
             'filled_quantity':0,'status':'UNKNOWN','statusKnown':False,'order_id':'mock-0001'}]}
        with patch.dict(os.environ,ON), patch('market_api.angel_owner_snapshot',return_value=book):
            code,body,_=hit('GET',ORDERS)
        self.assertEqual(code,200)
        self.assertEqual(body['records'][0]['status'],'UNKNOWN')
        self.assertFalse(body['canSubmitOrder'])

    def test_all_real_order_post_paths_stay_hard_locked(self):
        with patch.dict(os.environ,ON):
            for endpoint in ('/api/live/place-order','/api/brokers/angel/orders',
                             '/api/brokers/angel/modify-order','/api/brokers/angel/cancel-order'):
                with self.subTest(endpoint=endpoint):
                    code,body,_=hit('POST',endpoint,body={'side':'BUY'})
                    self.assertEqual(code,423)
                    self.assertFalse(body['orderSent'])

    def test_staging_login_origin_accepted_only_with_staging_cors_flag(self):
        # Authorized staging verification can reuse the existing owner-bound
        # temporary broker login; backend remains read-only and never returns tokens.
        expected={'connected':True,'orderExecutionEnabled':False,'maskedClientCode':'••••92'}
        with patch('market_api.angel_connect',return_value=expected) as verifier:
            code,body,_=hit('POST','/api/brokers/angel/connect',body={
                'apiKey':'test-public-not-real','clientCode':'MOCK','pin':'mock',
                'totp':'000000'})
        self.assertEqual(code,200)
        self.assertFalse(body['orderExecutionEnabled'])
        self.assertTrue(verifier.called)

    def test_wrong_origin_cannot_send_angel_login_secrets(self):
        with patch('market_api.angel_connect') as verifier:
            code,body,_=hit('POST','/api/brokers/angel/connect',
                            origin='https://malicious.example',body={'pin':'mock'})
        self.assertEqual(code,403)
        verifier.assert_not_called()

if __name__=='__main__':
    unittest.main()
