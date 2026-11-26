"""V32 mock-only FULL market quote validation. Never requests real orders."""
import unittest
from datetime import datetime, timezone, timedelta
from pathlib import Path
from live_v7.manual_full_quote_readonly_v32 import (
    parse_full_quote, FullQuoteBlocked, PATH, TOKEN, SYMBOL)

NOW=datetime(2026,11,26,6,10,0,tzinfo=timezone.utc)

def sample(**changes):
    row=dict(symbolToken=TOKEN,tradingSymbol=SYMBOL,exchange="NFO",
             ltp=10.80,exchFeedTime=(NOW+timedelta(hours=5,minutes=30)).strftime("%d-%b-%Y %H:%M:%S"),
             depth={"buy":[{"price":10.75,"quantity":65}],
                    "sell":[{"price":10.85,"quantity":130}]})
    row.update(changes)
    return {"status":True,"data":{"fetched":[row],"unfetched":[]}}

class V32ReadOnlyFullQuoteTests(unittest.TestCase):
    def parse(self, **changes):
        return parse_full_quote(sample(**changes),received_at=NOW)

    def test_valid_mock_depth(self):
        q=self.parse()
        self.assertEqual(q["bestBid"],"10.75")
        self.assertEqual(q["bestAsk"],"10.85")
        self.assertEqual(q["brokerFeedAgeSeconds"],0)
        self.assertTrue(q["bidAtOrAboveDraftLimit"])
        self.assertFalse(q["canSubmitOrder"])
        self.assertFalse(q["feedTimestampIndependentlyExchangeVerified"])

    def test_wrong_token(self):
        with self.assertRaisesRegex(FullQuoteBlocked,"MISMATCH"):
            self.parse(symbolToken="99999")

    def test_wrong_contract(self):
        with self.assertRaisesRegex(FullQuoteBlocked,"MISMATCH"):
            self.parse(tradingSymbol="NIFTY29DEC2629050CE")

    def test_wrong_exchange(self):
        with self.assertRaisesRegex(FullQuoteBlocked,"EXCHANGE"):
            self.parse(exchange="NSE")

    def test_failed_response(self):
        body=sample();body["status"]=False
        with self.assertRaises(FullQuoteBlocked):
            parse_full_quote(body,received_at=NOW)

    def test_multiple_quotes_blocked(self):
        body=sample();body["data"]["fetched"].append(body["data"]["fetched"][0])
        with self.assertRaises(FullQuoteBlocked):
            parse_full_quote(body,received_at=NOW)

    def test_depth_missing(self):
        with self.assertRaises(FullQuoteBlocked):
            self.parse(depth=None)

    def test_no_buy_depth(self):
        with self.assertRaises(FullQuoteBlocked):
            self.parse(depth={"buy":[],"sell":[{"price":11,"quantity":5}]})

    def test_crossed_quote(self):
        with self.assertRaises(FullQuoteBlocked):
            self.parse(depth={"buy":[{"price":11,"quantity":5}],
                              "sell":[{"price":10,"quantity":10}]})

    def test_invalid_bid(self):
        with self.assertRaises(FullQuoteBlocked):
            self.parse(depth={"buy":[{"price":"NaN","quantity":65}],
                              "sell":[{"price":11,"quantity":65}]})

    def test_zero_qty(self):
        with self.assertRaises(FullQuoteBlocked):
            self.parse(depth={"buy":[{"price":10.75,"quantity":0}],
                              "sell":[{"price":10.85,"quantity":65}]})

    def test_stale_feed_remains_unverified(self):
        q=self.parse(exchFeedTime=(NOW+timedelta(hours=5,minutes=29)).strftime("%d-%b-%Y %H:%M:%S"))
        self.assertFalse(q["brokerReportedFeedAgeWithin10s"])

    def test_feed_timestamp_missing_remains_unverified(self):
        q=self.parse(exchFeedTime=None)
        self.assertIsNone(q["brokerFeedTimestampUTC"])
        self.assertFalse(q["brokerReportedFeedAgeWithin10s"])

    def test_future_feed_rejected_for_freshness(self):
        q=self.parse(exchFeedTime=(NOW+timedelta(hours=5,minutes=30,seconds=20)).strftime("%d-%b-%Y %H:%M:%S"))
        self.assertFalse(q["brokerReportedFeedAgeWithin10s"])

    def test_bid_below_draft_limit_does_not_promise_fill(self):
        q=self.parse(depth={"buy":[{"price":10.45,"quantity":5}],
                            "sell":[{"price":10.60,"quantity":10}]})
        self.assertFalse(q["bidAtOrAboveDraftLimit"])

    def test_broker_ist_clock_is_converted_to_utc(self):
        q=self.parse(exchFeedTime="26-Nov-2026 11:40:00")
        self.assertEqual(q["brokerFeedTimestampUTC"],NOW.isoformat())

    def test_epoch_milliseconds(self):
        q=self.parse(exchFeedTime=str(int(NOW.timestamp()*1000)))
        self.assertEqual(q["brokerFeedAgeSeconds"],0)

    def test_read_only_endpoint(self):
        self.assertEqual(PATH,"/rest/secure/angelbroking/market/v1/quote")

    def test_no_order_transport_or_routes(self):
        s=Path(__file__).with_name("manual_full_quote_readonly_v32.py").read_text()
        for forbidden in ("placeOrder","modifyOrder","cancelOrder",
                          "angel_execution_transport","STOPLOSS_LIMIT"):
            self.assertNotIn(forbidden,s)

if __name__=="__main__":
    unittest.main()
