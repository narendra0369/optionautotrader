"""Offline tests for Stoxkart Superr owner-bound login. Zero network requests.

Mock responses reflect documented authentication and portfolio response shapes.
Passing these tests is not real-account, static-IP or algo-exchange approval.
"""
import hashlib
import hmac
import json
import os
import unittest
from unittest.mock import patch
from urllib.parse import urlsplit

from live_v7 import stoxkart_gateway as stk
from live_gateway import preflight

USER = "local-stoxkart-user"
API_KEY = "stox-api-key-0123456"
API_SECRET = "super-secret-value-0123456789"
CLIENT = "TEST1234"
REQUEST_TOKEN = "req_" + ("x" * 34)
ACCESS_TOKEN = "access_" + ("z" * 36)


class FakeResponse:
    status = 200

    def __init__(self, obj):
        self.data = json.dumps(obj).encode("utf-8")

    def read(self, maxbytes):
        return self.data[:maxbytes]

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


class StoxkartOfflineTests(unittest.TestCase):
    def setUp(self):
        self.env = patch.dict(os.environ, {"OPTIONX_OWNER_USER_ID": USER})
        self.env.start()
        self.addCleanup(self.env.stop)
        with stk.LOCK:
            stk._PENDING.clear()
            stk._SESSIONS.clear()
            stk._ATTEMPTS.clear()
        self.request_paths = []

    def start(self, now=1000):
        return stk.start(USER, {
            "apiKey": API_KEY, "apiSecret": API_SECRET, "clientCode": CLIENT
        }, now=now)

    def fake_fetch(self, req, timeout):
        self.assertLessEqual(timeout, 9)
        url = urlsplit(req.full_url)
        self.assertEqual(url.scheme, "https")
        self.assertEqual(url.netloc, "openapi.stoxkart.com")
        self.request_paths.append((req.get_method(), url.path))
        if url.path == "/auth/token":
            self.assertEqual(req.get_method(), "POST")
            body = json.loads(req.data.decode())
            correct = hmac.new((API_KEY + REQUEST_TOKEN).encode(),
                               API_SECRET.encode(), hashlib.sha256).hexdigest()
            self.assertEqual(body, {
                "api_key": API_KEY, "signature": correct,
                "req_token": REQUEST_TOKEN
            })
            return FakeResponse({"status": "success", "data": {"access_token": ACCESS_TOKEN}})
        if url.path == "/auth/profile":
            self.assertEqual(req.get_method(), "GET")
            headers = {k.lower(): v for k, v in req.header_items()}
            self.assertEqual(headers["x-access-token"], ACCESS_TOKEN)
            self.assertEqual(headers["x-api-key"], API_KEY)
            return FakeResponse({"status": "success", "data": {"client_id": CLIENT, "name": "PRIVATE"}})
        if url.path == "/portfolio/positions":
            return FakeResponse({"status": "success", "data": [
                {"exchange": "NFO", "token": "12345", "net_quantity": "75", "option_type": "CE"},
                {"exchange": "NSE", "token": "101", "net_quantity": "10"},
                {"exchange": "NFO", "token": "12346", "net_quantity": "0", "option_type": "PE"}
            ]})
        raise AssertionError("Unexpected broker URL " + url.path)

    def test_stoxkart_official_url_and_secret_hidden(self):
        reply = self.start()
        self.assertEqual(urlsplit(reply["loginUrl"]).hostname, "superrtrade.stoxkart.com")
        self.assertTrue(reply["registeredRedirectMustBe"].endswith("/stoxkart_callback.html"))
        self.assertNotIn(API_SECRET, repr(reply))
        self.assertFalse(reply["canSubmitOrder"])
        self.assertFalse(stk.status(USER, now=1001)["connected"])
        self.assertTrue(stk.status(USER, now=1001)["pendingLogin"])
        self.assertEqual(self.request_paths, [])

    def test_stoxkart_successful_profile_flow_read_only(self):
        flow = self.start()
        st = stk.complete(USER, {
            "flowId": flow["flowId"], "requestToken": REQUEST_TOKEN
        }, now=1001, fetch=self.fake_fetch)
        self.assertTrue(st["connected"])
        self.assertFalse(st["orderExecutionEnabled"])
        self.assertFalse(st["canSubmitOrder"])
        self.assertNotIn(API_SECRET, repr(st))
        self.assertNotIn(ACCESS_TOKEN, repr(st))
        self.assertEqual(self.request_paths,
                         [("POST", "/auth/token"), ("GET", "/auth/profile")])
        self.assertFalse(stk.status(USER, now=1001 + stk.SESSION_TTL)["connected"])

    def test_stoxkart_get_nfo_positions_only(self):
        flow = self.start()
        stk.complete(USER, {"flowId": flow["flowId"], "requestToken": REQUEST_TOKEN},
                     now=1001, fetch=self.fake_fetch)
        positions = stk.positions(USER, now=1002, fetch=self.fake_fetch)
        self.assertEqual(positions["records"], 1)
        self.assertEqual(positions["positions"][0]["netQuantity"], 75)
        self.assertFalse(positions["canSubmitOrder"])
        self.assertEqual(self.request_paths[-1], ("GET", "/portfolio/positions"))

    def test_stoxkart_wrong_flow_never_contacts_broker(self):
        self.start()
        with self.assertRaises(stk.StoxkartAuthError):
            stk.complete(USER, {"flowId": "bogus_" + "a" * 40,
                                "requestToken": REQUEST_TOKEN},
                         now=1001, fetch=self.fake_fetch)
        self.assertEqual(self.request_paths, [])

    def test_stoxkart_expired_request_never_contacts_broker(self):
        flow = self.start(now=1000)
        with self.assertRaises(stk.StoxkartAuthError):
            stk.complete(USER, {"flowId": flow["flowId"],
                                "requestToken": REQUEST_TOKEN},
                         now=1000 + stk.PENDING_TTL, fetch=self.fake_fetch)
        self.assertEqual(self.request_paths, [])

    def test_stoxkart_fails_wrong_broker_client_profile(self):
        flow = self.start()
        def wrong_profile(req, timeout):
            if urlsplit(req.full_url).path == "/auth/profile":
                return FakeResponse({"status": "success", "data": {"client_id": "OTHER123"}})
            return self.fake_fetch(req, timeout)
        with self.assertRaises(stk.StoxkartAuthError):
            stk.complete(USER, {"flowId": flow["flowId"],
                                "requestToken": REQUEST_TOKEN},
                         now=1001, fetch=wrong_profile)
        self.assertFalse(stk.status(USER, now=1001)["connected"])

    def test_stoxkart_session_one_time_and_expiring(self):
        flow = self.start()
        stk.complete(USER, {"flowId": flow["flowId"], "requestToken": REQUEST_TOKEN},
                     now=1001, fetch=self.fake_fetch)
        with self.assertRaises(stk.StoxkartAuthError):
            stk.complete(USER, {"flowId": flow["flowId"],
                                "requestToken": REQUEST_TOKEN}, now=1001,
                         fetch=self.fake_fetch)
        with self.assertRaises(stk.StoxkartAuthError):
            stk.positions(USER, now=1001 + stk.SESSION_TTL, fetch=self.fake_fetch)

    def test_stoxkart_only_bound_owner(self):
        with self.assertRaises(PermissionError):
            stk.start("other-user", {"apiKey":API_KEY, "apiSecret":API_SECRET,
                                      "clientCode":CLIENT}, now=1000)
        self.assertFalse(stk.status("other-user", now=1000)["ownerMatch"])

    def test_stoxkart_rate_limits(self):
        for i in range(3):
            self.start(now=1000 + i)
        with self.assertRaises(stk.StoxkartAuthError):
            self.start(now=1004)

    def test_stoxkart_unsafe_route_rejected(self):
        with self.assertRaises(stk.StoxkartAuthError):
            stk._post_or_get("POST", "/orders/place", payload={}, fetch=self.fake_fetch)
        with self.assertRaises(stk.StoxkartAuthError):
            stk._post_or_get("GET", "/auth/token", fetch=self.fake_fetch)
        self.assertEqual(self.request_paths, [])

    def test_stoxkart_invalid_secret_not_stored(self):
        with self.assertRaises(stk.StoxkartAuthError):
            stk.start(USER, {"apiKey":API_KEY, "apiSecret":"short",
                             "clientCode":CLIENT}, now=1000)
        self.assertFalse(stk.status(USER, now=1000)["pendingLogin"])

    def test_stoxkart_no_orders_and_preview_blocked(self):
        x = preflight({
            "market": "NIFTY", "broker": "Stoxkart", "side": "BUY",
            "orderType": "LIMIT", "quantity": 75, "limitPrice": 120.5,
            "riskBudget": 300, "dailyStop": 600, "maxTrades": 2,
            "strategyId": 1, "contractSymbol": "NIFTY30NOV26CE",
        }, USER)
        self.assertEqual(x["broker"], "Stoxkart")
        self.assertFalse(x["canSubmitOrder"])
        self.assertFalse(x["liveExecutionEnabled"])
        self.assertGreater(x["blockedCount"], 0)

    def test_stoxkart_disconnect_and_no_broker_order_call(self):
        flow = self.start()
        stk.complete(USER, {"flowId": flow["flowId"], "requestToken": REQUEST_TOKEN},
                     now=1001, fetch=self.fake_fetch)
        reply = stk.disconnect(USER)
        self.assertFalse(reply["connected"])
        self.assertFalse(stk.status(USER, now=1001)["connected"])
        self.assertEqual(self.request_paths,
                         [("POST", "/auth/token"), ("GET", "/auth/profile")])


if __name__ == "__main__":
    unittest.main()
