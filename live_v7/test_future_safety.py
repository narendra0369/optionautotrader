"""OPTIONX V7 FUTURE OFFLINE REGRESSION TESTS.

AUTHORED BUT NOT RUN. User requested to defer all testing.
Network and broker credentials are strictly forbidden in these tests.
"""
from __future__ import annotations

import unittest
from datetime import datetime, timedelta, timezone
from decimal import Decimal

from live_v7 import audit_chain, contracts, intent_gate, kill_switch
from live_v7 import protective_exit, read_only_transport, reconciliation
from live_v7.read_only_bridge import ReadOnlyBridgeError, angel_owner_snapshot
from live_v7.readiness import status as readiness_status

NOW = datetime(2026, 11, 24, 10, 30, tzinfo=timezone.utc)


class V7SafetyTests(unittest.TestCase):
    def test_startup_kill_switch_always_blocks(self):
        s = kill_switch.startup_state()
        self.assertEqual(s.state, "STOPPED")
        self.assertTrue(kill_switch.public_status(s)["newEntriesBlocked"])
        self.assertFalse(kill_switch.public_status(s)["canSubmitOrder"])

    def test_reset_request_does_not_enable_trading(self):
        s = kill_switch.KillSwitch(updated_at=NOW.isoformat())
        requested = kill_switch.transition(
            s, "REQUEST_RESET", caller_is_verified_owner=True,
            expected_revision=0, reason="development", now=NOW,
        )
        self.assertEqual(requested.state, "RESET_REQUESTED")
        self.assertTrue(requested.new_entries_blocked)

    def test_nonowner_cannot_transition(self):
        s = kill_switch.startup_state()
        with self.assertRaises(kill_switch.KillSwitchError):
            kill_switch.transition(
                s, "STOP", caller_is_verified_owner=False,
                expected_revision=0, reason="test", now=NOW,
            )

    def test_intent_preflight_never_authorizes_order(self):
        result = intent_gate.evaluate({}, {}, now=NOW)
        self.assertFalse(result["canSubmitOrder"])
        self.assertFalse(result["liveExecutionEnabled"])
        self.assertGreaterEqual(len(result["blockedReasons"]), 1)

    def test_broker_transport_is_off_by_default(self):
        s = read_only_transport.ServerOnlySession(
            broker="Angel", owner_id="verified-owner",
            api_key="example_key_long", bearer_token="x" * 32,
            broker_account_verified=True, session_current=True,
        )
        with self.assertRaises(read_only_transport.ReadOnlyTransportError):
            read_only_transport.fetch_readonly(
                session=s, resource="orderbook", verified_owner_id="verified-owner",
            )
        self.assertFalse(read_only_transport.public_capabilities()["liveOrderExecutionEnabled"])

    def test_transport_never_exposes_arbitrary_path(self):
        s = read_only_transport.ServerOnlySession(
            broker="Delta", owner_id="verified-owner",
            api_key="example_key_long", api_secret="x" * 40,
            broker_account_verified=True, session_current=True,
        )
        with self.assertRaises(read_only_transport.ReadOnlyTransportError):
            read_only_transport.request_headers(
                s, path="/v2/orders/insert", timestamp=1795500000,
            )
        self.assertNotIn("example_key_long", repr(s))

    def test_readonly_bridge_is_off_by_default(self):
        with self.assertRaises(ReadOnlyBridgeError):
            angel_owner_snapshot(verified_optionx_user_id="test-user", resource="positions")

    def test_contract_rejects_unverified_data(self):
        with self.assertRaises(contracts.ContractVerificationError):
            contracts.contract_from_verified_master(
                {"broker": "Angel", "market": "NIFTY", "kind": "CE",
                 "broker_source_verified": False}, now=NOW
            )

    def test_quote_rejects_untrusted_source(self):
        c = contracts.Contract(
            "Angel", "NIFTY", "CE", "NFO", "abc", "NIFTY27NOV26CE",
            1, Decimal("0.05"), Decimal("1"), "INR", NOW + timedelta(days=3),
            NOW, True, True, NOW,
        )
        with self.assertRaises(contracts.ContractVerificationError):
            contracts.quote_from_verified_broker(
                {"broker": "Angel", "token": "abc",
                 "bid": "100", "ask": "101", "as_of": NOW,
                 "source_authenticated": False},
                c, now=NOW,
            )

    def test_protection_cannot_execute(self):
        fill = protective_exit.ConfirmedLongFill(
            "user-verified", "Angel", "order-confirmed", "token-xyz",
            "NIFTY27NOV26CE", 100, 100, Decimal("100"), NOW,
        )
        out = protective_exit.protection_requirements(
            fill=fill, stop_price="95", target_price="110",
            tick_size="0.05", contract_multiplier="1", lot_size=50,
            now=NOW, trusted={},
        )
        self.assertFalse(out["canSendStopOrTarget"])
        self.assertIn("EXIT_ENGINE_NOT_APPROVED_OR_TESTED", out["blockedReasons"])

    def test_reconciliation_stays_blocked_even_if_empty(self):
        result = reconciliation.compare(
            tracked_orders=[], broker_orders=[], broker_positions=[],
            local_positions={}, source_authenticated=True, snapshot_time=NOW,
            now=NOW,
        )
        self.assertTrue(result["newEntriesBlocked"])
        self.assertFalse(result["liveExecutionEnabled"])

    def test_audit_chain_rejects_tampering(self):
        key = b"k" * 32
        e = audit_chain.record(
            previous_digest=audit_chain.GENESIS, secret=key,
            event_id="event_audit_0001", event_type="PREFLIGHT_BLOCKED",
            broker="Angel", market="NIFTY", reason_code="RISK_STOP",
            now=NOW,
        )
        self.assertTrue(audit_chain.verify([e], secret=key)["verified"])
        corrupted = dict(e, reason_code="BYPASS")
        self.assertFalse(audit_chain.verify([corrupted], secret=key)["verified"])

    def test_v7_readiness_is_always_locked(self):
        r = readiness_status(
            {"ownerConfigured": True, "ownerMatch": True, "connected": True}
        )
        self.assertFalse(r["canSubmitOrder"])
        self.assertFalse(r["liveExecutionEnabled"])
        self.assertGreater(len(r["notIndependentlyVerified"]), 5)


if __name__ == "__main__":
    unittest.main()

# Import extended offline cases into the explicit V7 regression entrypoint.
from live_v7.test_extended_offline import DeepOfflineTests

# V7 Stoxkart official-login integration mocked offline regression cases.
from live_v7.test_stoxkart import StoxkartOfflineTests

# Stoxkart handler-level origin, auth and no-order HTTP routing tests.
from live_v7.test_stoxkart_http import StoxkartHttpTests

# Independent Angel V7 private-GET checks run in every staging backend build.
from live_v7.test_angel_readonly_http import AngelReadonlyHttpTests

# GET request headers, mixed cash/NFO filtering, and private diagnostic tests.
from live_v7.test_angel_readfix import AngelGetRepairTests

# Verify server snapshot JSON and browser-required ownership metadata match.
from live_v7.test_angel_snapshot_contract import AngelSnapshotContractTests
