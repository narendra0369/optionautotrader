"""Offline regression for Angel One NFO order mapping; NEVER submits orders."""
import unittest
from copy import deepcopy
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from live_v7.angel_order_contracts import (
    OrderContractError, limit_entry, protective_stop,
)

NOW = datetime(2026, 11, 25, 11, 15, tzinfo=ZoneInfo("Asia/Kolkata"))


def inputs():
    contract = {
        "broker": "Angel", "exchange": "NFO", "market": "NIFTY",
        "kind": "CE", "tradingsymbol": "NIFTY01DEC2624450CE",
        "symboltoken": "123456", "lot_size": 65, "tick_size": "0.05",
        "verified_from_broker": True,
    }
    approved = dict.fromkeys((
        "owner_account_verified", "broker_session_verified",
        "broker_orders_reconciled", "static_ip_registered_with_angel",
        "algo_api_approved_by_broker", "kill_switch_healthy",
        "margin_verified", "contract_master_fresh",
        "trade_day_calendar_verified", "risk_limits_approved_by_owner",
    ), True)
    approved.update(
        emergency_stop=False, unresolved_or_unknown_orders=False,
        existing_market_exposure=False, entries_reserved_today=0,
        unique_intent_reserved_durably=True, quote_at=NOW,
        approved_max_notional="20000",
    )
    return dict(
        market="NIFTY", contract=contract,
        quote={"broker": "Angel", "symboltoken": "123456",
               "authenticated": True, "bid": "99.95", "ask": "100.05"},
        quantity=65, limit_price="100.05",
        owner_snapshot=approved, now=NOW,
    )


def stop_inputs():
    p = inputs()
    return dict(
        contract=p["contract"],
        confirmed_fill={
            "authenticated": True, "broker": "Angel", "side": "BUY",
            "symboltoken": "123456", "net_open_quantity": 65,
            "filled_quantity": 65, "order_id": "order_123456",
            "verified_at": NOW, "average_price": "100.05",
        },
        broker_state={
            "owner_account_verified": True, "orderbook_reconciled": True,
            "existing_exit_orders": False, "emergency_stop": False,
            "stoploss_limit_supported_for_contract": True,
        },
        trigger_price="94.00", limit_price="93.50", now=NOW,
    )


class AngelOrderContractsTests(unittest.TestCase):
    def test_valid_limit_contract_cannot_submit_real_order(self):
        result = limit_entry(**inputs())
        self.assertFalse(result["canSubmitOrder"])
        self.assertEqual(result["payload"]["ordertype"], "LIMIT")
        self.assertEqual(result["payload"]["duration"], "DAY")
        self.assertEqual(result["payload"]["transactiontype"], "BUY")
        self.assertEqual(result["payload"]["exchange"], "NFO")
        self.assertEqual(result["payload"]["quantity"], "65")

    def test_valid_stop_contract_remains_offline(self):
        result = protective_stop(**stop_inputs())
        self.assertFalse(result["canSubmitOrder"])
        self.assertEqual(result["payload"]["ordertype"], "STOPLOSS_LIMIT")
        self.assertEqual(result["payload"]["transactiontype"], "SELL")
        self.assertEqual(result["payload"]["triggerprice"], "94.00")
        self.assertEqual(result["payload"]["price"], "93.50")

    def test_static_ip_not_confirmed(self):
        p = inputs()
        p["owner_snapshot"]["static_ip_registered_with_angel"] = False
        with self.assertRaisesRegex(OrderContractError, "STATIC_IP"):
            limit_entry(**p)

    def test_unapproved_algo_api(self):
        p = inputs()
        p["owner_snapshot"]["algo_api_approved_by_broker"] = False
        with self.assertRaisesRegex(OrderContractError, "ALGO_API"):
            limit_entry(**p)

    def test_expired_quote(self):
        p = inputs()
        p["owner_snapshot"]["quote_at"] = NOW-timedelta(seconds=11)
        with self.assertRaisesRegex(OrderContractError, "QUOTE_STALE"):
            limit_entry(**p)

    def test_two_entrances_used(self):
        p = inputs()
        p["owner_snapshot"]["entries_reserved_today"] = 2
        with self.assertRaisesRegex(OrderContractError, "TWO_ENTRIES"):
            limit_entry(**p)

    def test_missing_durable_intent_reservation(self):
        p = inputs()
        p["owner_snapshot"]["unique_intent_reserved_durably"] = False
        with self.assertRaisesRegex(OrderContractError, "DURABLE"):
            limit_entry(**p)

    def test_outside_entry_hours(self):
        p = inputs()
        p["now"] = NOW.replace(hour=15)
        p["owner_snapshot"]["quote_at"] = p["now"]
        with self.assertRaisesRegex(OrderContractError, "ENTRY_WINDOW"):
            limit_entry(**p)

    def test_lot_mismatch(self):
        p = inputs()
        p["quantity"] = 64
        with self.assertRaisesRegex(OrderContractError, "LOT"):
            limit_entry(**p)

    def test_price_not_tick_aligned(self):
        p = inputs()
        p["limit_price"] = "100.03"
        with self.assertRaisesRegex(OrderContractError, "TICK"):
            limit_entry(**p)

    def test_proxy_or_wrong_exchange(self):
        p = inputs()
        p["contract"]["exchange"] = "NSE"
        with self.assertRaisesRegex(OrderContractError, "WRONG_BROKER_EXCHANGE"):
            limit_entry(**p)

    def test_untrusted_quote(self):
        p = inputs()
        p["quote"]["authenticated"] = False
        with self.assertRaisesRegex(OrderContractError, "AUTHENTICATED_BROKER_QUOTE"):
            limit_entry(**p)

    def test_limit_price_notional_cap(self):
        p = inputs()
        p["owner_snapshot"]["approved_max_notional"] = "100"
        with self.assertRaisesRegex(OrderContractError, "NOTIONAL"):
            limit_entry(**p)

    def test_emergency_stop_blocks_entry(self):
        p = inputs()
        p["owner_snapshot"]["emergency_stop"] = True
        with self.assertRaisesRegex(OrderContractError, "EMERGENCY_STOP"):
            limit_entry(**p)

    def test_stop_cannot_be_prepared_for_partial_fill(self):
        p = stop_inputs()
        p["confirmed_fill"]["net_open_quantity"] = 30
        with self.assertRaisesRegex(OrderContractError, "PARTIAL_OR_MISMATCHED_FILL"):
            protective_stop(**p)

    def test_stop_requires_fresh_fill(self):
        p = stop_inputs()
        p["confirmed_fill"]["verified_at"] = NOW-timedelta(seconds=20)
        with self.assertRaisesRegex(OrderContractError, "BROKER_FILL_STALE"):
            protective_stop(**p)

    def test_stop_price_must_be_lower_than_trigger(self):
        p = stop_inputs()
        p["limit_price"] = "95.00"
        with self.assertRaisesRegex(OrderContractError, "SELL_STOP"):
            protective_stop(**p)

    def test_stop_requires_verified_broker_support(self):
        p = stop_inputs()
        p["broker_state"]["stoploss_limit_supported_for_contract"] = False
        with self.assertRaisesRegex(OrderContractError, "BROKER_STATE"):
            protective_stop(**p)

    def test_no_oco_bypass_when_an_exit_already_exists(self):
        p = stop_inputs()
        p["broker_state"]["existing_exit_orders"] = True
        with self.assertRaisesRegex(OrderContractError, "BROKER_STATE"):
            protective_stop(**p)

    def test_no_http_or_broker_sdk(self):
        from pathlib import Path
        s = Path(__file__).with_name("angel_order_contracts.py").read_text("utf-8")
        for unsafe in ("urllib", "requests", "SmartConnect", "placeOrder(",
                       "modifyOrder(", "cancelOrder(", "urlopen(", "api_key",
                       "Authorization: Bearer", "placeOrderFullResponse"):
            self.assertNotIn(unsafe, s)


if __name__ == "__main__":
    unittest.main()
