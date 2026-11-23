"""Extended offline V7 regression: no real broker calls or credentials.

Required release tests for later broker integration are still outstanding:
static IP, partial-fill broker reconciliations, durable DB and real slippage.
"""
from __future__ import annotations

import unittest
from datetime import datetime, timedelta, timezone
from decimal import Decimal

from live_v7 import (
    angel_master, audit_chain, broker_readonly, contracts, intent_gate,
    kill_switch, order_journal, protective_exit, reconciliation, risk_policy,
    secret_vault, shadow_recovery,
)

NOW = datetime(2026, 11, 24, 5, 0, tzinfo=timezone.utc)  # 10:30 IST


def angel_master_record():
    return {
        "broker": "Angel", "market": "NIFTY", "kind": "CE",
        "exchange": "NFO", "token": "123456",
        "symbol": "NIFTY30NOV26CE", "lot_size": 75,
        "tick_size": "0.05", "multiplier": "1", "currency": "INR",
        "expires_at": NOW + timedelta(days=6),
        "master_verified_at": NOW - timedelta(minutes=5),
        "broker_source_verified": True, "currently_tradable": True,
        "trading_status_verified_at": NOW - timedelta(seconds=1),
    }


class DeepOfflineTests(unittest.TestCase):
    def test_paper_tier_at_30k(self):
        r = risk_policy.stepped_paper_plan("30000")
        self.assertEqual(r["illustrativeLots"], 1)
        self.assertEqual(r["riskINR"], "300")
        self.assertFalse(r["canSubmitOrder"])

    def test_paper_tier_70k(self):
        r = risk_policy.stepped_paper_plan("70000")
        self.assertEqual(r["illustrativeLots"], 2)
        self.assertEqual(r["dailyStopINR"], "1200")

    def test_paper_tier_500k_retained(self):
        r = risk_policy.stepped_paper_plan("500000")
        self.assertEqual(r["illustrativeLots"], 12)
        self.assertEqual(r["riskINR"], "3600")
        self.assertEqual(r["rewardINR"], "7200")
        self.assertEqual(r["dailyStopINR"], "7200")

    def test_paper_under_minimum_no_lots(self):
        r = risk_policy.stepped_paper_plan("29999")
        self.assertEqual(r["illustrativeLots"], 0)
        with self.assertRaises(risk_policy.RiskPolicyError):
            risk_policy.stepped_paper_plan("NaN")

    def test_life_cycle_replay_and_illegal_transition(self):
        c = order_journal.open_local_journal(":memory:")
        try:
            kw = {
                "owner_id": "user_1000", "intent_id": "intent_0001",
                "market": "NIFTY", "broker": "Angel", "now": NOW,
            }
            self.assertTrue(order_journal.reserve_intent(c, **kw))
            self.assertFalse(order_journal.reserve_intent(c, **kw))
            t = NOW.astimezone(order_journal.IST).date().isoformat()
            self.assertEqual(
                order_journal.transition(
                    c, owner_id="user_1000", intent_id="intent_0001",
                    trade_day_ist=t, event_id="event_0001",
                    target="LOCAL_REJECTED", now=NOW,
                ),
                "LOCAL_REJECTED",
            )
            with self.assertRaises(order_journal.JournalError):
                order_journal.transition(
                    c, owner_id="user_1000", intent_id="intent_0001",
                    trade_day_ist=t, event_id="event_0002",
                    target="FILLED", now=NOW,
                )
            self.assertEqual(order_journal.unresolved_orders(c, "user_1000"), 0)
        finally:
            c.close()

    def test_unknown_broker_response_blocked(self):
        rows = broker_readonly.angel_orders({
            "status": True,
            "data": [{
                "orderid": "ABCD1234", "tradingsymbol": "NIFTY30NOV26CE",
                "exchange": "NFO", "transactiontype": "BUY",
                "quantity": "75", "filledshares": "0",
                "orderstatus": "very_new_state",
            }],
        })
        self.assertEqual(rows[0]["status"], "UNKNOWN")
        self.assertFalse(rows[0]["statusKnown"])
        reconciled = reconciliation.compare(
            tracked_orders=[], broker_orders=rows,
            broker_positions=[], local_positions={},
            source_authenticated=True, snapshot_time=NOW, now=NOW,
        )
        self.assertFalse(reconciled["reconciled"])
        self.assertIn("UNKNOWN_BROKER_ORDER_STATUS", reconciled["blocks"])
        self.assertTrue(reconciled["newEntriesBlocked"])

    def test_broker_readonly_does_not_include_orders_post(self):
        for broker, resources in broker_readonly.READ_ROUTES.items():
            for route in resources:
                spec = broker_readonly.readonly_route(broker, route)
                self.assertEqual(spec["method"], "GET")
        with self.assertRaises(broker_readonly.BrokerSnapshotError):
            broker_readonly.readonly_route("Angel", "placeOrder")

    def test_contract_master_rejects_stale_and_mismatch(self):
        raw = angel_master_record()
        self.assertEqual(
            contracts.contract_from_verified_master(raw, now=NOW).token,
            "123456",
        )
        stale = {**raw, "master_verified_at": NOW - timedelta(days=2)}
        with self.assertRaises(contracts.ContractVerificationError):
            contracts.contract_from_verified_master(stale, now=NOW)
        wrong = {**raw, "exchange": "NSE"}
        with self.assertRaises(contracts.ContractVerificationError):
            contracts.contract_from_verified_master(wrong, now=NOW)

    def test_contract_quote_spread_and_tick(self):
        c = contracts.contract_from_verified_master(angel_master_record(), now=NOW)
        q = contracts.quote_from_verified_broker({
            "broker": "Angel", "token": c.token,
            "bid": "100.00", "ask": "100.50",
            "as_of": NOW - timedelta(seconds=1),
            "source_authenticated": True,
        }, c, now=NOW)
        self.assertTrue(contracts.quote_health(q)["quoteValidForResearch"])
        self.assertFalse(contracts.quote_health(q)["canSubmitOrder"])
        with self.assertRaises(contracts.ContractVerificationError):
            contracts.quote_from_verified_broker({
                "broker": "Angel", "token": c.token,
                "bid": "100.00", "ask": "100.03",
                "as_of": NOW, "source_authenticated": True,
            }, c, now=NOW)

    def test_future_quote_refused(self):
        c = contracts.contract_from_verified_master(angel_master_record(), now=NOW)
        with self.assertRaises(contracts.ContractVerificationError):
            contracts.quote_from_verified_broker({
                "broker": "Angel", "token": c.token,
                "bid": "100", "ask": "101",
                "as_of": NOW + timedelta(minutes=1),
                "source_authenticated": True,
            }, c, now=NOW)

    def test_angel_candidates_not_executable(self):
        feed = [{
            "name": "NIFTY", "exch_seg": "NFO",
            "instrumenttype": "OPTIDX", "symbol": "NIFTY30NOV26CE",
            "token": "123456", "expiry": "30NOV2026",
            "lotsize": "75", "tick_size": "5", "strike": "2000000",
        }]
        r = angel_master.candidates(feed, market="NIFTY", contract_kind="CE",
                downloaded_at=NOW, now=NOW)
        self.assertEqual(r["count"], 1)
        self.assertFalse(r["rows"][0]["canSubmitOrder"])
        self.assertFalse(r["rows"][0]["tickScaleIndependentlyConfirmed"])

    def test_audit_chain_two_events(self):
        key = b"s" * 32
        first = audit_chain.record(previous_digest=audit_chain.GENESIS,
            secret=key, event_id="audit_evt_001", event_type="PREFLIGHT_BLOCKED",
            broker="Angel", market="NIFTY", reason_code="INVALID_PRICE", now=NOW)
        second = audit_chain.record(previous_digest=first["digest"],
            secret=key, event_id="audit_evt_002", event_type="MANUAL_REVIEW_REQUIRED",
            broker="Angel", market="NIFTY", reason_code="MISSING_ORDER", now=NOW)
        result = audit_chain.verify([first, second], secret=key,
                                    expected_head_digest=second["digest"])
        self.assertTrue(result["verified"])
        tampered = audit_chain.verify([first, second], secret=key,
                                      expected_head_digest=audit_chain.GENESIS)
        self.assertFalse(tampered["verified"])

    def test_kill_switch_unknown_restoration_fails_closed(self):
        for x in (None, {}, {"state":"ON","revision":0}, {"state":"STOPPED"}):
            restored = kill_switch.restored_state(x)
            self.assertEqual(restored.state, "STOPPED")
            self.assertTrue(restored.new_entries_blocked)

    def test_secret_vault_refuses_read_and_save(self):
        v = secret_vault.LockedVault()
        ref = secret_vault.VaultReference(
            "00000000-0000-4000-8000-000000000001", "Angel", "opaque-ref"
        )
        with self.assertRaises(secret_vault.VaultUnavailable):
            v.get_for_verified_server_owner(ref, server_owner_verified=True)
        with self.assertRaises(secret_vault.VaultUnavailable):
            v.save(ref, "do-not-save")

    def test_stop_ack_must_be_verified(self):
        fill = protective_exit.ConfirmedLongFill(
            "owner_0001", "Angel", "order_0001", "token_0001",
            "NIFTY30NOV26CE", 75, 75, Decimal("100"), NOW)
        r = protective_exit.verify_protection_ack(
            fill=fill, broker_snapshot={"source_authenticated": True,
                "broker": "Angel", "contract_token": "token_0001",
                "action": "EXIT_SELL", "status": "REJECTED",
                "protected_quantity": 75, "broker_order_id":"stop_0001",
                "as_of": NOW}, now=NOW)
        self.assertIn("PROTECTIVE_STOP_NOT_ACKNOWLEDGED", r["blockedReasons"])
        self.assertFalse(r["canSendStopOrTarget"])

    def test_valid_reconciled_snapshot_still_cannot_execute(self):
        r = reconciliation.compare(
            tracked_orders=[], broker_orders=[], broker_positions=[],
            local_positions={}, source_authenticated=True, snapshot_time=NOW,
            now=NOW)
        self.assertTrue(r["reconciled"])
        self.assertTrue(r["newEntriesBlocked"])
        self.assertFalse(r["liveExecutionEnabled"])

    def test_preflight_rejects_invalid_input_floats(self):
        r = intent_gate.evaluate(
            {"intent_id": "intent_1111", "market": "NIFTY",
             "broker": "Angel", "action": "ENTRY_BUY", "symbol": "NIFTY30NOV26CE",
             "quantity": 75, "entry_price": float("nan"),
             "stop_price": "95", "target_price": "110", "estimated_cost": "0",
             "slippage_reserve": "0", "strategy_id": 1},
            {}, now=NOW,
        )
        self.assertIn("INVALID_ENTRY_PRICE", r["blockedReasons"])
        self.assertFalse(r["canSubmitOrder"])


    def _trusted_entry(self, *, multiplier="1", verified=True, currency="INR"):
        import copy
        c = {
            "broker": "Angel", "exchange": "NFO", "symbol": "NIFTY30NOV26CE",
            "token": "123456", "lot_size": 75, "tick_size": "0.05",
            "verified_at": NOW, "expiry": NOW + timedelta(days=6),
            "multiplier": multiplier, "multiplier_verified": verified,
            "settlement_model": "LINEAR_PRICE_DIFFERENCE", "currency": currency,
        }
        t = {key: True for key in (
            "authenticated_owner", "broker_account_matches_owner",
            "broker_session_current", "broker_api_permission_confirmed",
            "registered_static_ip_confirmed", "exchange_or_algo_requirements_confirmed",
            "kill_switch_healthy", "broker_orderbook_reconciled",
            "no_pending_or_unknown_orders", "no_open_position_in_market",
            "strategy_approved_by_owner", "market_data_is_exchange_grade",
            "broker_quote_authenticated", "contract_master_verified",
            "margin_verified", "exchange_session_verified_for_today",
        )}
        t.update({
            "emergency_stop": False, "intent_id_already_seen": False,
            "contract": c,
            "quote": {"as_of": NOW, "ask": "100.00", "bid": "99.50",
                      "broker": "Angel", "token": "123456",
                      "source_authenticated": True},
            "risk_budget": "300", "daily_loss_limit": "600",
            "today_realized_pnl": "0", "available_margin": "100000",
            "required_margin": "7500", "today_trade_count": 0,
            "max_trades_per_day": 2, "risk_currency": "INR",
        })
        return t

    def _risk_intent(self):
        return {
            "intent_id": "intent_risk_0001", "market": "NIFTY",
            "broker": "Angel", "action": "ENTRY_BUY",
            "symbol": "NIFTY30NOV26CE", "quantity": 75,
            "entry_price": "100.00", "stop_price": "99.00",
            "target_price": "102.00", "estimated_cost": "1",
            "slippage_reserve": "1", "strategy_id": 1,
        }

    def test_multiplier_applied_before_risk_limit(self):
        trusted = self._trusted_entry(multiplier="5")
        result = intent_gate.evaluate(self._risk_intent(), trusted, now=NOW)
        self.assertIn("TRADE_RISK_CAP_EXCEEDED", result["blockedReasons"])
        self.assertEqual(result["calculated"]["lossIfStoppedEstimate"], "377.00")
        self.assertFalse(result["canSubmitOrder"])

    def test_no_multiplier_verification_fails_closed(self):
        trusted = self._trusted_entry(multiplier="1", verified=False)
        result = intent_gate.evaluate(self._risk_intent(), trusted, now=NOW)
        self.assertIn("CONTRACT_MULTIPLIER_UNVERIFIED", result["blockedReasons"])
        self.assertIn("RISK_NOT_COMPUTABLE", result["blockedReasons"])
        self.assertFalse(result["readyForLaterIntegrationTests"])

    def test_unverified_quote_token_fails_closed(self):
        trusted = self._trusted_entry()
        trusted["quote"]["token"] = "wrong-token"
        result = intent_gate.evaluate(self._risk_intent(), trusted, now=NOW)
        self.assertIn("QUOTE_CONTRACT_OR_SOURCE_MISMATCH", result["blockedReasons"])

    def test_risk_currency_mismatch_fails_closed(self):
        trusted = self._trusted_entry(currency="USD")
        result = intent_gate.evaluate(self._risk_intent(), trusted, now=NOW)
        self.assertIn("RISK_CURRENCY_MISMATCH_OR_UNVERIFIED", result["blockedReasons"])

    def test_valid_synthetic_case_never_allows_order(self):
        trusted = self._trusted_entry()
        result = intent_gate.evaluate(self._risk_intent(), trusted, now=NOW)
        self.assertTrue(result["readyForLaterIntegrationTests"])
        self.assertFalse(result["canSubmitOrder"])
        self.assertFalse(result["liveExecutionEnabled"])


    def _shadow_event(self, kind, event_id, **extra):
        return {"kind": kind, "event_id": event_id,
                "as_of": NOW, "source_verified": True, **extra}

    def test_shadow_full_fill_and_stop_ack_no_anomalies(self):
        events = [
            self._shadow_event("ENTRY_FILL", "entry_fill_1", cumulative_quantity=75),
            self._shadow_event("STOP_ACK", "stop_ack_1", protected_quantity=75),
        ]
        r = shadow_recovery.replay(
            events, planned_entry_quantity=75, now=NOW, verified_account=True
        )
        self.assertEqual(r["anomalies"], [])
        self.assertEqual(r["netOpenQuantity"], 75)
        self.assertTrue(r["newEntriesBlocked"])
        self.assertFalse(r["canSubmitOrder"])

    def test_shadow_partial_fill_requires_stop_cover(self):
        events = [
            self._shadow_event("ENTRY_FILL", "entry_fill_1", cumulative_quantity=25),
            self._shadow_event("STOP_ACK", "stop_ack_1", protected_quantity=10),
        ]
        r = shadow_recovery.replay(
            events, planned_entry_quantity=75, now=NOW, verified_account=True
        )
        self.assertIn("OPEN_POSITION_WITHOUT_FULL_STOP_COVERAGE", r["anomalies"])

    def test_shadow_unknown_entry_blocks_without_reconciliation(self):
        r = shadow_recovery.replay([
            self._shadow_event("ENTRY_UNKNOWN", "entry_unk_1"),
        ], planned_entry_quantity=75, now=NOW, verified_account=True)
        self.assertIn("UNKNOWN_BROKER_ORDER_OUTCOME", r["anomalies"])

    def test_shadow_duplicate_fill_events_block(self):
        ev = self._shadow_event("ENTRY_FILL", "fill_00001", cumulative_quantity=25)
        r = shadow_recovery.replay([ev, ev], planned_entry_quantity=75,
                                   now=NOW, verified_account=True)
        self.assertIn("DUPLICATE_EVENT", r["anomalies"])
        self.assertEqual(r["entryFilledQuantity"], 25)

    def test_shadow_exit_more_than_entry_detects_short_risk(self):
        events = [
            self._shadow_event("ENTRY_FILL", "entry_fill_1", cumulative_quantity=25),
            self._shadow_event("EXIT_FILL", "exit_fill_1", cumulative_quantity=50),
        ]
        r = shadow_recovery.replay(
            events, planned_entry_quantity=75, now=NOW, verified_account=True
        )
        self.assertIn("EXIT_REPLAY_OR_POSSIBLE_NAKED_SHORT", r["anomalies"])

    def test_shadow_restart_without_reconcile_blocks(self):
        r = shadow_recovery.replay([], planned_entry_quantity=75,
              now=NOW, verified_account=True, restart_occurred=True)
        self.assertIn("RESTART_REQUIRES_FULL_BROKER_RECONCILIATION",
                      r["anomalies"])

    def test_shadow_stop_rejection_requires_manual_review(self):
        events = [
            self._shadow_event("ENTRY_FILL", "entry_fill_1", cumulative_quantity=75),
            self._shadow_event("STOP_REJECT", "stop_reject_1"),
        ]
        r = shadow_recovery.replay(
            events, planned_entry_quantity=75, now=NOW, verified_account=True)
        self.assertIn("BROKER_STOP_REJECTED", r["anomalies"])

    def test_shadow_exit_after_ack_requires_fresh_reconcile(self):
        events = [
            self._shadow_event("ENTRY_FILL", "entry_fill_1", cumulative_quantity=75),
            self._shadow_event("STOP_ACK", "stop_ack_1", protected_quantity=75),
            self._shadow_event("EXIT_FILL", "exit_fill_1", cumulative_quantity=75),
        ]
        r = shadow_recovery.replay(
            events, planned_entry_quantity=75, now=NOW, verified_account=True)
        self.assertIn("UNKNOWN_BROKER_ORDER_OUTCOME", r["anomalies"])
        self.assertIn("POSSIBLE_ORPHAN_STOP_ORDER", r["anomalies"])

    def test_shadow_untrusted_broker_event_never_counts(self):
        bad = self._shadow_event("ENTRY_FILL", "entry_fill_1", cumulative_quantity=75)
        bad["source_verified"] = False
        r = shadow_recovery.replay(
            [bad], planned_entry_quantity=75, now=NOW, verified_account=True)
        self.assertIn("BROKER_EVENT_NOT_AUTHENTICATED", r["anomalies"])
        self.assertEqual(r["entryFilledQuantity"], 0)


if __name__ == "__main__":
    unittest.main()
