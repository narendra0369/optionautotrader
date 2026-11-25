"""V27 mock-only quote contract validation. No broker order calls."""
import unittest
from live_v7.manual_sl_quote_v27 import parse_ltp,QuoteBlocked,PATH
SYMBOL="NIFTY29DEC2629000CE";TOKEN="38158"
DATA={"status":True,"data":{"exchange":"NFO","tradingsymbol":SYMBOL,
    "symboltoken":TOKEN,"ltp":"100.25"}}
class V27ManualSLQuoteTests(unittest.TestCase):
 def test_valid_quote(self):
  self.assertEqual(parse_ltp(DATA,symbol=SYMBOL,token=TOKEN),"100.25")
 def test_wrong_contract_denied(self):
  with self.assertRaisesRegex(QuoteBlocked,"MISMATCH"):
   parse_ltp(DATA,symbol="BANKNIFTY29DEC26CE",token=TOKEN)
 def test_wrong_token_denied(self):
  with self.assertRaisesRegex(QuoteBlocked,"MISMATCH"):
   parse_ltp(DATA,symbol=SYMBOL,token="99999")
 def test_failed_broker_response_denied(self):
  with self.assertRaisesRegex(QuoteBlocked,"FAILED"):
   parse_ltp(dict(DATA,status=False),symbol=SYMBOL,token=TOKEN)
 def test_missing_ltp_denied(self):
  with self.assertRaisesRegex(QuoteBlocked,"INVALID"):
   parse_ltp(dict(DATA,data=dict(DATA["data"],ltp=None)),symbol=SYMBOL,token=TOKEN)
 def test_zero_ltp_denied(self):
  with self.assertRaisesRegex(QuoteBlocked,"INVALID"):
   parse_ltp(dict(DATA,data=dict(DATA["data"],ltp=0)),symbol=SYMBOL,token=TOKEN)
 def test_negative_ltp_denied(self):
  with self.assertRaisesRegex(QuoteBlocked,"INVALID"):
   parse_ltp(dict(DATA,data=dict(DATA["data"],ltp="-2")),symbol=SYMBOL,token=TOKEN)
 def test_nan_denied(self):
  with self.assertRaisesRegex(QuoteBlocked,"INVALID"):
   parse_ltp(dict(DATA,data=dict(DATA["data"],ltp="NaN")),symbol=SYMBOL,token=TOKEN)
 def test_fixed_market_data_endpoint(self):
  self.assertEqual(PATH,"/rest/secure/angelbroking/order/v1/getLtpData")
 def test_no_order_api_calls(self):
  from pathlib import Path
  source=Path(__file__).with_name("manual_sl_quote_v27.py").read_text()
  self.assertNotIn("placeOrder",source)
  self.assertNotIn("modifyOrder",source)
  self.assertNotIn("cancelOrder",source)
  self.assertNotIn("angel_execution_transport",source)
if __name__=="__main__":unittest.main()
