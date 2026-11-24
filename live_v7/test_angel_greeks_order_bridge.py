"""Greeks RR3 -> Angel contract bridge, offline synthetic tests only."""
import unittest
from copy import deepcopy
from live_v7.angel_order_contracts import OrderContractError
from live_v7.angel_greeks_order_bridge import preview_entry, preview_protective_stop
from live_v7.test_angel_order_contracts import inputs, stop_inputs


def parameters():
    p = inputs()
    c = p["contract"]
    selected = {
        "realOrdersEnabled": False, "symbol": c["tradingsymbol"],
        "token": c["symboltoken"], "side": c["kind"],
        "market": c["market"], "lotSize": c["lot_size"],
        "selection": "nearest_actual_strike_nearest_expiry",
    }
    plan = {
        "mode": "AUTO_PAPER_RESEARCH_NO_ORDERS",
        "contract": c["tradingsymbol"], "side": c["kind"],
        "quantity": p["quantity"], "canSubmitOrder": False,
        "entryPremium": "100.05", "stopTrigger": "94.00",
        "stopLimit": "93.50", "targetLimit": "120.00",
    }
    return dict(selected=selected, plan=plan, contract=c,
                quote=p["quote"], owner_snapshot=p["owner_snapshot"],
                now=p["now"])


class GreeksOrderBridgeTests(unittest.TestCase):
    def test_rr3_limit_preview_is_safe(self):
        result = preview_entry(**parameters())
        self.assertEqual(result["entry"]["payload"]["ordertype"], "LIMIT")
        self.assertEqual(result["entry"]["payload"]["quantity"], "65")
        self.assertEqual(result["theoreticalRR"], "1:3")
        self.assertFalse(result["canSubmitOrder"])
        self.assertFalse(result["targetOrderDispatchAllowed"])
        self.assertIsNone(result["estimatedFillTimeSeconds"])

    def test_stop_after_confirmed_fill_only(self):
        p = parameters()
        stop = stop_inputs()
        result = preview_protective_stop(
            selected=p["selected"], plan=p["plan"],
            contract=p["contract"], confirmed_fill=stop["confirmed_fill"],
            broker_state=stop["broker_state"], now=p["now"])
        self.assertEqual(result["payload"]["ordertype"], "STOPLOSS_LIMIT")
        self.assertEqual(result["payload"]["price"], "93.50")
        self.assertFalse(result["canSubmitOrder"])

    def test_reject_contract_token_mismatch(self):
        p = parameters()
        p["selected"]["token"] = "999999"
        with self.assertRaisesRegex(OrderContractError, "ATM_CONTRACT"):
            preview_entry(**p)

    def test_reject_rr_below_three(self):
        p = parameters()
        p["plan"]["targetLimit"] = "115.00"
        with self.assertRaisesRegex(OrderContractError, "RR3"):
            preview_entry(**p)

    def test_reject_moved_ask_invalidating_rr(self):
        p = parameters()
        p["quote"]["ask"] = "101.00"
        p["quote"]["bid"] = "100.95"
        with self.assertRaisesRegex(OrderContractError, "RR3"):
            preview_entry(**p)

    def test_reject_fake_approval(self):
        p = parameters()
        p["owner_snapshot"]["algo_api_approved_by_broker"] = False
        with self.assertRaisesRegex(OrderContractError, "ALGO_API"):
            preview_entry(**p)

    def test_reject_second_trade_exhaustion(self):
        p = parameters()
        p["owner_snapshot"]["entries_reserved_today"] = 2
        with self.assertRaisesRegex(OrderContractError, "TWO_ENTRIES"):
            preview_entry(**p)

    def test_reject_duplicate_or_unknown_intent(self):
        p = parameters()
        p["owner_snapshot"]["unique_intent_reserved_durably"] = False
        with self.assertRaisesRegex(OrderContractError, "DURABLE"):
            preview_entry(**p)

    def test_reject_missing_native_stop(self):
        p = parameters()
        p["owner_snapshot"]["broker_native_stop_supported"] = False
        with self.assertRaisesRegex(OrderContractError, "STOP"):
            preview_entry(**p)

    def test_reject_unverified_bidask(self):
        p = parameters()
        p["quote"]["authenticated"] = False
        with self.assertRaisesRegex(OrderContractError, "AUTHENTICATED_BROKER_QUOTE"):
            preview_entry(**p)

    def test_reject_partial_fill_protection(self):
        p = parameters()
        stop = stop_inputs()
        stop["confirmed_fill"]["filled_quantity"] = 30
        with self.assertRaisesRegex(OrderContractError, "PARTIAL"):
            preview_protective_stop(
                selected=p["selected"], plan=p["plan"], contract=p["contract"],
                confirmed_fill=stop["confirmed_fill"], broker_state=stop["broker_state"], now=p["now"])

    def test_reject_unreconciled_existing_stop(self):
        p = parameters()
        stop = stop_inputs()
        stop["broker_state"]["existing_exit_orders"] = True
        with self.assertRaisesRegex(OrderContractError, "BROKER_STATE"):
            preview_protective_stop(
                selected=p["selected"], plan=p["plan"], contract=p["contract"],
                confirmed_fill=stop["confirmed_fill"], broker_state=stop["broker_state"], now=p["now"])

    def test_bridge_has_no_network_or_order_send(self):
        from pathlib import Path
        source = Path(__file__).with_name("angel_greeks_order_bridge.py").read_text()
        for forbidden in ("urllib", "requests.post", "SmartConnect", "placeOrder(",
                          "modifyOrder(", "cancelOrder(", "urlopen(", "Authorization"):
            self.assertNotIn(forbidden, source)


if __name__ == "__main__":
    unittest.main()
