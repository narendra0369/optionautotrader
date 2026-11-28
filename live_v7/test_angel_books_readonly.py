"""No-network tests for owner-bound Angel three-book GET adapter."""
import io
import json
import os
import unittest
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

import angel_gateway
from live_v7.angel_books_readonly import (
    AngelBookReadError, read_book, read_three_books, RESOURCES,
)

OWNER = "verified-owner-001"
NOW = datetime(2026, 11, 25, 10, 30, tzinfo=timezone(timedelta(hours=5, minutes=30)))


class Response(io.BytesIO):
    status = 200
    def __enter__(self):
        return self
    def __exit__(self, *args):
        self.close()


def mock_broker(req, timeout):
    assert req.get_method() == "GET"
    assert "placeOrder" not in req.full_url
    assert "cancelOrder" not in req.full_url
    assert req.full_url.startswith("https://apiconnect.angelone.in/")
    if req.full_url.endswith("getOrderBook"):
        rows = [{"orderid":"order_12345","tradingsymbol":"NIFTY01DEC2624450CE",
                 "exchange":"NFO","transactiontype":"BUY",
                 "quantity":"65","filledshares":"0","orderstatus":"open"}]
    elif req.full_url.endswith("getPosition"):
        rows = [{"tradingsymbol":"NIFTY01DEC2624450CE","exchange":"NFO",
                 "symboltoken":"123456","netqty":"0"}]
    else:
        rows = [{"tradeid":"trade_1001"}]
    return Response(json.dumps({"status":True,"data":rows}).encode())


class AngelBooksReadOnlyTests(unittest.TestCase):
    def setUp(self):
        self.env = patch.dict(os.environ, {"OPTIONX_OWNER_USER_ID": OWNER})
        self.env.start()
        with angel_gateway.LOCK:
            angel_gateway._SESSIONS[OWNER] = {
                "jwt":"test_jwt","apiKey":"test_key",
                "expires":NOW.timestamp()+900,
                "verifiedAt":NOW.isoformat(),
                "maskedClientCode":"**01",
            }
    def tearDown(self):
        with angel_gateway.LOCK:
            angel_gateway._SESSIONS.pop(OWNER,None)
        self.env.stop()

    def test_three_books_get_no_execution(self):
        urls=[]
        def fetch(req, timeout):
            urls.append(req.full_url)
            return mock_broker(req, timeout)
        with patch("angel_gateway.angel_client_identity_headers", return_value={}):
            result=read_three_books(OWNER,fetch=fetch,now=NOW)
        self.assertEqual(len(urls),3)
        self.assertTrue(result["allReadsSucceeded"])
        self.assertEqual(result["books"]["orderbook"]["orders"][0]["status"],"OPEN")
        self.assertEqual(result["books"]["tradebook"]["tradeRows"],1)
        self.assertEqual(result["books"]["positions"]["positions"][0]["net_quantity"],0)
        self.assertFalse(result["orderAcknowledgementVerified"])
        self.assertFalse(result["tradeFillReconciled"])
        self.assertFalse(result["canSubmitOrder"])

    def test_only_owner_allowed(self):
        seen=[]
        with self.assertRaisesRegex(AngelBookReadError,"OWNER_NOT_AUTHENTICATED"):
            read_book("other-owner-01","orderbook",fetch=lambda *_a,**_k:seen.append(True),now=NOW)
        self.assertEqual(seen,[])

    def test_expired_ram_session_blocks_network(self):
        seen=[]
        with angel_gateway.LOCK:
            angel_gateway._SESSIONS[OWNER]["expires"]=NOW.timestamp()-1
        with self.assertRaisesRegex(AngelBookReadError,"SESSION_EXPIRED"):
            read_book(OWNER,"orderbook",fetch=lambda *_a,**_k:seen.append(True),now=NOW)
        self.assertEqual(seen,[])

    def test_unknown_resource_blocks_network(self):
        with self.assertRaisesRegex(AngelBookReadError,"RESOURCE_NOT_ALLOWLISTED"):
            read_book(OWNER,"place",fetch=mock_broker,now=NOW)

    def test_broker_failure_blocks(self):
        with patch("angel_gateway.angel_client_identity_headers",return_value={}):
            with self.assertRaisesRegex(AngelBookReadError,"BROKER_READ_REJECTED"):
                read_book(OWNER,"orderbook",fetch=lambda req, timeout: Response(b'{"status":false,"data":null}'),now=NOW)

    def test_unknown_order_status_stays_unknown(self):
        def fetch(req,timeout):
            return Response(json.dumps({"status":True,"data":[{
                "orderid":"order_12345", "tradingsymbol":"NIFTY01DEC2624450CE",
                "exchange":"NFO","transactiontype":"BUY","quantity":"65",
                "filledshares":"0","orderstatus":"some new broker state"
            }]}).encode())
        with patch("angel_gateway.angel_client_identity_headers",return_value={}):
            result=read_book(OWNER,"orderbook",fetch=fetch,now=NOW)
        self.assertEqual(result["orders"][0]["status"],"UNKNOWN")

    def test_trade_rows_not_inferred_as_fills(self):
        with patch("angel_gateway.angel_client_identity_headers",return_value={}):
            r=read_book(OWNER,"tradebook",fetch=mock_broker,now=NOW)
        self.assertEqual(r["tradeRows"],1)
        self.assertFalse(r["fillsBrokerVerified"])

    def test_snapshot_fails_closed_on_tradebook_failure(self):
        def fetch(req,timeout):
            if req.full_url.endswith("getTradeBook"):
                raise OSError("simulated timeout")
            return mock_broker(req,timeout)
        with patch("angel_gateway.angel_client_identity_headers",return_value={}):
            with self.assertRaisesRegex(AngelBookReadError,"UNAVAILABLE"):
                read_three_books(OWNER,fetch=fetch,now=NOW)

    def test_no_order_post_code(self):
        from pathlib import Path
        s=Path(__file__).with_name("angel_books_readonly.py").read_text()
        for forbidden in ("placeOrder(", "cancelOrder(", "method=\"POST\"",
                          "SmartConnect", "modifyOrder(", "placeOrderFullResponse"):
            self.assertNotIn(forbidden,s)


if __name__ == "__main__":
    unittest.main()
