"""Angel V7 response-contract regression. All broker data synthetic, no network.

Prevents the exact mismatch where a 200 response had a different envelope
or lacked the safety and verified-account fields required by the browser.
"""
from __future__ import annotations

import os
import unittest
from unittest.mock import patch

from live_v7.read_only_bridge import angel_owner_snapshot, ReadOnlyBridgeError

USER = "contract-test-owner"
SESSION = {"apiKey":"synthetic-readonly-key",
           "jwt":"synthetic-jwt-"+"x"*32}
PROTOCOL = "OPTIONX_V7_ANGEL_READONLY_V2"

class AngelSnapshotContractTests(unittest.TestCase):
    def _request(self, resource, rows):
        with patch.dict(os.environ,{"OPTIONX_OWNER_USER_ID":USER}), \
             patch("live_v7.read_only_bridge.angel_gateway._clean_session",
                   return_value=SESSION), \
             patch("live_v7.read_only_bridge.fetch_readonly",
                   return_value={"status":True,"data":rows}) as fetch:
            result=angel_owner_snapshot(
                verified_optionx_user_id=USER,
                resource=resource,
                server_feature_flag_enabled=True)
            self.assertEqual(fetch.call_count,1)
        return result

    def test_empty_nfo_positions_have_full_owner_verified_envelope(self):
        result=self._request("positions",[])
        self.assertEqual(result["snapshotContract"],PROTOCOL)
        self.assertEqual(result["trustedAccount"],"OWNER_PROFILE_MATCHED")
        self.assertIs(result["canSubmitOrder"],False)
        self.assertIs(result["orderExecutionEnabled"],False)
        self.assertIs(result["quoteAndContractMasterVerified"],False)
        self.assertEqual(result["broker"],"Angel")
        self.assertEqual(result["resource"],"positions")
        self.assertEqual(result["recordCount"],len(result["records"]))
        self.assertEqual(result["records"],[])
        self.assertNotIn("jwt",str(result).lower())
        self.assertNotIn("apiKey",str(result))

    def test_nfo_orderbook_has_same_contract_and_no_execute_permission(self):
        row={"exchange":"NFO","orderid":"order0001",
             "tradingsymbol":"NIFTY27NOV26CE","transactiontype":"BUY",
             "orderstatus":"open","quantity":"25","filledshares":"0"}
        result=self._request("orderbook",[row])
        self.assertEqual(result["snapshotContract"],PROTOCOL)
        self.assertEqual(result["resource"],"orderbook")
        self.assertEqual(result["recordCount"],1)
        self.assertEqual(result["records"][0]["status"],"OPEN")
        self.assertFalse(result["canSubmitOrder"])
        self.assertFalse(result["orderExecutionEnabled"])

    def test_unbound_owner_cannot_receive_owner_verified_contract(self):
        with patch.dict(os.environ,{"OPTIONX_OWNER_USER_ID":"someone-else"}), \
             patch("live_v7.read_only_bridge.fetch_readonly") as fetch:
            with self.assertRaises(ReadOnlyBridgeError):
                angel_owner_snapshot(verified_optionx_user_id=USER,
                                     resource="positions",server_feature_flag_enabled=True)
            fetch.assert_not_called()

if __name__=="__main__":
    unittest.main()
