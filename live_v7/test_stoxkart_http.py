"""Offline HTTP-handler security regression for Stoxkart V7 routes.

No HTTP sockets or external broker calls: the handler is given in-memory
streams, the OptionX auth verifier and broker adapter are mocked.
"""
from __future__ import annotations

import io
import json
import os
import unittest
from unittest.mock import patch

import market_api
from live_v7.stoxkart_gateway import StoxkartAuthError

STAGING = "https://optionx-v7-frontend-test-staging.onrender.com"

def hit(method, path, *, origin=STAGING, user="verified-owner", body=None, ctype="application/json"):
    content = json.dumps(body).encode("utf-8") if body is not None else b""
    obj = market_api.Handler.__new__(market_api.Handler)
    obj.path = path
    obj.headers = {
        "Origin": origin,
        "Authorization": "Bearer dummy-not-real-token",
        "Content-Type": ctype,
        "Content-Length": str(len(content)),
    }
    obj.rfile = io.BytesIO(content)
    obj.wfile = io.BytesIO()
    obj._status = None
    obj._headers = {}
    obj.send_response = lambda status: setattr(obj, "_status", status)
    obj.send_header = lambda key, val: obj._headers.__setitem__(key, val)
    obj.end_headers = lambda: None
    with patch.dict(os.environ, {"OPTIONX_V7_STAGING_CORS":"1"}), \
         patch("market_api.user_from_token", return_value=user):
        if method == "POST":
            market_api.Handler.do_POST(obj)
        elif method == "GET":
            market_api.Handler.do_GET(obj)
        elif method == "OPTIONS":
            market_api.Handler.do_OPTIONS(obj)
        else:
            raise ValueError("Unexpected method")
    response = json.loads(obj.wfile.getvalue()) if obj.wfile.getvalue() else None
    return obj._status, response, obj._headers


class StoxkartHttpTests(unittest.TestCase):
    def test_stoxkart_start_requires_trusted_origin(self):
        with patch("market_api.stoxkart_start") as broker:
            status, body, _ = hit("POST", "/api/brokers/stoxkart/start", origin="https://evil.example", body={})
        self.assertEqual(status, 403)
        self.assertFalse(broker.called)

    def test_stoxkart_start_requires_valid_optionx_session(self):
        with patch("market_api.stoxkart_start") as broker:
            status, body, _ = hit("POST", "/api/brokers/stoxkart/start", user=None, body={})
        self.assertEqual(status, 401)
        self.assertFalse(broker.called)

    def test_stoxkart_start_rejects_non_json(self):
        with patch("market_api.stoxkart_start") as broker:
            status, body, _ = hit("POST", "/api/brokers/stoxkart/start", body={}, ctype="text/plain")
        self.assertEqual(status, 415)
        self.assertFalse(broker.called)

    def test_stoxkart_start_endpoint_routes_only_to_login(self):
        success = {"loginUrl":"https://superrtrade.stoxkart.com/login?api_key=public",
                   "flowId":"safe-id", "canSubmitOrder":False,"orderExecutionEnabled":False}
        with patch("market_api.stoxkart_start", return_value=success) as broker:
            status, body, headers = hit("POST", "/api/brokers/stoxkart/start",
                body={"apiKey":"public","apiSecret":"not-a-real-secret","clientCode":"MOCK"})
        self.assertEqual(status, 200)
        self.assertEqual(body["canSubmitOrder"], False)
        self.assertEqual(broker.call_args.args[0], "verified-owner")
        self.assertEqual(headers.get("Access-Control-Allow-Origin"), STAGING)

    def test_stoxkart_positions_requires_owner_session(self):
        with patch("market_api.stoxkart_positions", side_effect=StoxkartAuthError("no session")):
            status, body, _ = hit("GET", "/api/brokers/stoxkart/positions")
        self.assertEqual(status, 503)
        self.assertIn("no orders sent", body["error"])

    def test_stoxkart_login_status_is_read_only(self):
        answer = {"connected":False,"canSubmitOrder":False,"orderExecutionEnabled":False}
        with patch("market_api.stoxkart_status", return_value=answer):
            status, body, _ = hit("GET", "/api/brokers/stoxkart/status")
        self.assertEqual(status, 200)
        self.assertFalse(body["orderExecutionEnabled"])

    def test_arbitrary_stoxkart_order_route_remains_blocked(self):
        with patch("market_api.stoxkart_start") as b:
            status, body, _ = hit("POST", "/api/brokers/stoxkart/place-order",
                                  body={"side":"BUY"})
        self.assertEqual(status, 423)
        self.assertFalse(body["orderSent"])
        self.assertFalse(b.called)

    def test_stoxkart_get_rejects_unauthorized_origin(self):
        with patch("market_api.stoxkart_status") as b:
            status, body, _ = hit("GET", "/api/brokers/stoxkart/status",
                                  origin="https://unknown.example")
        self.assertEqual(status, 403)
        self.assertFalse(b.called)

    def test_stoxkart_preflight_unauthorized_orders(self):
        status, body, _ = hit("POST", "/api/live/place-order", body={"side":"BUY"})
        self.assertEqual(status, 423)
        self.assertFalse(body["orderSent"])

    def test_cors_staging_origin_opt_in(self):
        status, body, headers = hit("OPTIONS", "/api/brokers/stoxkart/status")
        self.assertEqual(status, 204)
        self.assertEqual(headers.get("Access-Control-Allow-Origin"), STAGING)


if __name__ == "__main__":
    unittest.main()
