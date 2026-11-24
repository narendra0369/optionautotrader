"""Offline-only tests for owner-bound temporary Angel One profile verification."""
import json
import unittest
from io import BytesIO
from unittest.mock import patch
import angel_gateway as ag

USER = '123e4567-e89b-12d3-a456-426614174000'
OTHER = '00000000-0000-0000-0000-000000000000'
CREDS = {'apiKey': 'TEST_API_KEY_1234', 'clientCode': 'AB1234', 'pin': '1234', 'totp': '123456'}
LOGIN_TOKEN = 'fake-jwt-not-real-' + 'x' * 55

class Response:
    status = 200
    def __init__(self, data): self.data = data
    def __enter__(self): return self
    def __exit__(self, *a): return False
    def read(self, n): return json.dumps(self.data).encode()

class BrokerFake:
    def __init__(self, match=True, rejects=False):
        self.calls = []
        self.match = match
        self.rejects = rejects
    def __call__(self, req, timeout=10):
        assert req.full_url.startswith('https://apiconnect.angelone.in/')
        assert '/placeOrder' not in req.full_url
        assert '/getOrder' not in req.full_url
        assert '/cancelOrder' not in req.full_url
        self.calls.append((req.get_method(), req.full_url))
        if self.rejects: return Response({'status': False, 'message': 'DO_NOT_EXPOSE_TOKEN_HERE'})
        if req.get_method() == 'POST':
            b = json.loads(req.data)
            assert b == {'clientcode': 'AB1234','password': '1234','totp': '123456'}
            return Response({'status': True, 'data': {'jwtToken': LOGIN_TOKEN, 'refreshToken': 'PRIVATE_REFRESH', 'feedToken': 'PRIVATE_FEED'}})
        assert req.get_method() == 'GET'
        assert req.get_header('Authorization') == 'Bearer ' + LOGIN_TOKEN
        return Response({'status': True, 'data': {'clientcode': 'AB1234' if self.match else 'AB9999', 'name': 'Never display'}})

class TestAngelGateway(unittest.TestCase):
    def setUp(self):
        ag._SESSIONS.clear(); ag._ATTEMPTS.clear()
        self.env = patch.dict('os.environ', {'OPTIONX_OWNER_USER_ID': USER, 'ANGEL_EGRESS_PUBLIC_IPV4': ''})
        self.env.start()
    def tearDown(self):
        self.env.stop(); ag._SESSIONS.clear(); ag._ATTEMPTS.clear()
    def test_success_is_read_only_and_secrets_never_returned(self):
        f = BrokerFake()
        result = ag.connect(USER, dict(CREDS), fetch=f, now=1000)
        self.assertEqual(len(f.calls), 2)
        self.assertTrue(result['connected'])
        self.assertFalse(result['orderExecutionEnabled'])
        self.assertIn('••', result['maskedClientCode'])
        self.assertTrue(result['maskedClientCode'].endswith('34'))
        self.assertEqual(ag.status(USER, now=1000)['connected'], True)
        combined = json.dumps(result)
        for secret in ('123456', 'PRIVATE_REFRESH', 'PRIVATE_FEED', LOGIN_TOKEN, '1234', CREDS['apiKey']):
            self.assertNotIn(secret, combined)
        self.assertTrue(ag.status(USER, now=1900)['connected'])  # no arbitrary 15-minute expiry
        midnight=ag.trading_day_expiry(1000)
        self.assertTrue(ag.status(USER, now=midnight-1)['connected'])
        self.assertFalse(ag.status(USER, now=midnight)['connected'])
        self.assertEqual(result['readOnlySessionScope'], 'TRADING_DAY_READONLY')
        self.assertEqual(result['sessionStorage'], 'SERVER_RAM_ONLY')
    def test_midnight_ist_boundary_and_no_next_day_reuse(self):
        from datetime import datetime
        from zoneinfo import ZoneInfo
        tz=ZoneInfo('Asia/Kolkata')
        before=datetime(2026, 11, 25, 23, 59, 45, tzinfo=tz).timestamp()
        expiry=datetime(2026, 11, 26, 0, 0, tzinfo=tz).timestamp()
        self.assertEqual(ag.trading_day_expiry(before), expiry)
        r=ag.connect(USER, dict(CREDS), fetch=BrokerFake(), now=before)
        self.assertEqual(r['expiresAt'], datetime.fromtimestamp(expiry, __import__('datetime').timezone.utc).isoformat())
        self.assertTrue(ag.status(USER, now=expiry-1)['connected'])
        self.assertFalse(ag.status(USER, now=expiry)['connected'])
        self.assertFalse(r['orderExecutionEnabled'])

    def test_process_restart_loses_only_ram_session(self):
        ag.connect(USER, dict(CREDS), fetch=BrokerFake(), now=1000)
        ag._SESSIONS.clear()
        self.assertFalse(ag.status(USER, now=1100)['connected'])

    def test_owner_required_even_with_valid_credentials(self):
        with self.assertRaises(PermissionError): ag.connect(OTHER, dict(CREDS), fetch=BrokerFake())
        self.assertFalse(ag.status(OTHER)['connected'])
    def test_no_owner_configured_fail_closed(self):
        with patch.dict('os.environ', {'OPTIONX_OWNER_USER_ID': ''}):
            with self.assertRaises(PermissionError): ag.connect(USER, dict(CREDS), fetch=BrokerFake())
            self.assertFalse(ag.status(USER)['ownerConfigured'])
    def test_mismatch_and_provider_failure_do_not_store_session(self):
        with self.assertRaisesRegex(ag.AuthError, 'does not match'):
            ag.connect(USER, dict(CREDS), fetch=BrokerFake(match=False), now=1000)
        self.assertFalse(ag.status(USER,now=1000)['connected'])
        try:
            ag.connect(USER, dict(CREDS), fetch=BrokerFake(rejects=True), now=1001)
        except ag.AuthError as e:
            self.assertNotIn('DO_NOT_EXPOSE', str(e))
        else: self.fail('Broker rejection must fail')
    def test_invalid_secret_formats_rejected_before_network(self):
        for bad in ({**CREDS, 'totp':'11111'}, {**CREDS, 'pin': ''}, {**CREDS, 'apiKey': 'a'}, {**CREDS, 'clientCode':'<bad>'}):
            f=BrokerFake()
            with self.assertRaises(ag.AuthError): ag.connect(USER, bad, fetch=f, now=1000)
            self.assertEqual(f.calls, [])
    def test_attempt_limit_and_disconnect(self):
        for t in (1000,1001,1002):
            with self.assertRaises(ag.AuthError): ag.connect(USER, dict(CREDS), fetch=BrokerFake(rejects=True), now=t)
        with self.assertRaisesRegex(ag.AuthError, 'Too many'):
            ag.connect(USER, dict(CREDS), fetch=BrokerFake(), now=1003)
        # Once window expires, fresh login is possible.
        self.assertTrue(ag.connect(USER, dict(CREDS), fetch=BrokerFake(), now=2000)['connected'])
        self.assertFalse(ag.disconnect(USER)['connected'])
        self.assertFalse(ag.status(USER,now=2000)['connected'])
    def test_read_only_endpoint_allowlist(self):
        with self.assertRaisesRegex(ag.AuthError, 'Unsupported'):
            ag._post_or_get('POST', '/rest/secure/angelbroking/order/v1/placeOrder', CREDS['apiKey'], payload={}, fetch=BrokerFake())
    def test_client_code_binding(self):
        with patch.dict('os.environ', {'ANGEL_ALLOWED_CLIENT_CODE': 'XY1234'}):
            with self.assertRaises(PermissionError): ag.connect(USER, dict(CREDS), fetch=BrokerFake())

if __name__ == '__main__': unittest.main()
