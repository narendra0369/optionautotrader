"""V8 offline Angel execution/stop/restart regression. No broker connections."""
from __future__ import annotations
import copy
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path
import sqlite3
import tempfile
import unittest

from live_v8.angel_order_plans import (
    BrokerContract, OrderPlanError, preview_entry, preview_protective_stop,
    preview_target_exit, send_real_order,
)
from live_v8.shadow_journal import (
    ShadowJournalError, open_dev_db, reserve, mark_synthetic_send_unknown,
    observe_entry, observe_protection, record_exit, snapshot,
)
from live_v8.restart_recovery import assess_restart

NOW=datetime(2026,11,24,4,30,0,tzinfo=timezone.utc)
OWNER="owner_test_001"
INTENT="trade_000001"
SYMBOL="NIFTY27NOV2626000CE"
TOKEN="123456"
BUYID="B0000001"
STOPID="S0000001"
CONTRACT=BrokerContract(symbol=SYMBOL,token=TOKEN,lot_size=65,tick_size="0.05",
                         contract_master_verified=True,owner_account_verified=True)


def broker_book(qty=130):
    return [
        {"id":BUYID,"symbol":SYMBOL,"token":TOKEN,"side":"BUY","quantity":130,
         "filled":qty,"status":"COMPLETE" if qty==130 else "PARTIAL"},
        {"id":STOPID,"symbol":SYMBOL,"token":TOKEN,"side":"SELL","quantity":qty,
         "filled":0,"status":"TRIGGER PENDING","variety":"STOPLOSS",
         "ordertype":"STOPLOSS_LIMIT"},
    ]


def broker_trades(qty=130):
    return [{"trade_id":"T0000001","order_id":BUYID,"symbol":SYMBOL,
             "side":"BUY","quantity":qty}]


def broker_positions(qty=130):
    return [{"symbol":SYMBOL,"token":TOKEN,"net_quantity":qty}]


class OrderPlans(unittest.TestCase):
    def test_limit_entry_uses_correct_broker_fields(self):
        p=preview_entry(contract=CONTRACT,qty=65,limit_price="155.05",intent_id=INTENT)
        self.assertEqual(p.payload["ordertype"],"LIMIT")
        self.assertEqual(p.payload["exchange"],"NFO")
        self.assertEqual(p.payload["quantity"],"65")
        self.assertEqual(p.payload["transactiontype"],"BUY")
        self.assertFalse(p.can_submit_real_order)
        self.assertNotIn("apiKey",p.payload)
        self.assertNotIn("pin",p.payload)

    def test_stop_loss_limit_plan_requires_confirmed_fill(self):
        p=preview_protective_stop(
            contract=CONTRACT,filled_open_qty=65,trigger_price="140.00",
            limit_price="139.00",intent_id="stop_000001",
            fill_verified=True,position_verified=True,exit_rules_verified=True)
        self.assertEqual(p.payload["variety"],"STOPLOSS")
        self.assertEqual(p.payload["ordertype"],"STOPLOSS_LIMIT")
        self.assertEqual(p.payload["transactiontype"],"SELL")
        self.assertEqual(p.payload["triggerprice"],"140.00")
        self.assertEqual(p.payload["price"],"139.00")

    def test_tick_lot_nan_bools_and_unverified_contract_blocked(self):
        with self.assertRaises(OrderPlanError):
            preview_entry(contract=CONTRACT,qty=66,limit_price="155.05",intent_id=INTENT)
        for price in ("155.03","NaN","Infinity","-1"):
            with self.subTest(price=price),self.assertRaises(OrderPlanError):
                preview_entry(contract=CONTRACT,qty=65,limit_price=price,intent_id=INTENT)
        with self.assertRaises(OrderPlanError):
            preview_entry(contract=CONTRACT,qty=True,limit_price="155.00",intent_id=INTENT)
        unverified=BrokerContract(SYMBOL,TOKEN,65,"0.05",contract_master_verified=False)
        with self.assertRaises(OrderPlanError):
            preview_entry(contract=unverified,qty=65,limit_price="155.00",intent_id=INTENT)

    def test_stop_limit_direction_and_verification_block(self):
        for trigger,limit in (("140.00","140.05"),("0","0"),("140.03","139.00")):
            with self.subTest(trigger=trigger),self.assertRaises(OrderPlanError):
                preview_protective_stop(contract=CONTRACT,filled_open_qty=65,
                    trigger_price=trigger,limit_price=limit,intent_id="stop_000001",
                    fill_verified=True,position_verified=True,exit_rules_verified=True)
        with self.assertRaises(OrderPlanError):
            preview_protective_stop(contract=CONTRACT,filled_open_qty=65,
                trigger_price="140",limit_price="139",intent_id="stop_000001",
                fill_verified=True,position_verified=False,exit_rules_verified=True)

    def test_target_needs_stop_cancel_and_fresh_position(self):
        for flags in (
            (False,True,True),(True,False,True),(True,True,False)
        ):
            with self.subTest(flags=flags),self.assertRaises(OrderPlanError):
                preview_target_exit(contract=CONTRACT,net_open_qty=65,
                    limit_price="175",intent_id="target_000001",
                    stop_cancel_confirmed=flags[0],fresh_position_verified=flags[1],
                    no_other_sell_orders=flags[2])
        p=preview_target_exit(contract=CONTRACT,net_open_qty=65,limit_price="175",
            intent_id="target_000001",stop_cancel_confirmed=True,
            fresh_position_verified=True,no_other_sell_orders=True)
        self.assertEqual(p.payload["transactiontype"],"SELL")
        self.assertEqual(p.payload["ordertype"],"LIMIT")

    def test_no_real_submission_ever(self):
        with self.assertRaisesRegex(PermissionError,"REAL_ORDERS_HARD_LOCKED"):
            send_real_order(object())


class JournalAndRecovery(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(prefix="optionx_v8_test_")
        self.db=open_dev_db(Path(self.temp.name)/"rehearsal.sqlite3")
        self.assertTrue(reserve(self.db,owner=OWNER,intent=INTENT,symbol=SYMBOL,
                                token=TOKEN,quantity=130,now=NOW))

    def tearDown(self):
        self.db.close()
        self.temp.cleanup()

    def mark(self):
        return mark_synthetic_send_unknown(self.db,owner=OWNER,intent=INTENT,
                                           event_id="ev_send_001",now=NOW)

    def buy(self,qty=130,status="COMPLETE",event_id="ev_buy_0001"):
        return observe_entry(self.db,owner=OWNER,intent=INTENT,event_id=event_id,
            broker_id=BUYID,broker_status=status,cumulative_filled=qty,
            snapshot_authenticated=True,asof=NOW,now=NOW,identity_linked=True)

    def stop(self,qty=130):
        return observe_protection(self.db,owner=OWNER,intent=INTENT,
            event_id="ev_stop_001",stop_order_id=STOPID,protected_qty=qty,
            verified_stop_orderbook=True,snapshot_authenticated=True,asof=NOW,now=NOW)

    def recovered(self,**kwargs):
        args=dict(local=snapshot(self.db,owner=OWNER,intent=INTENT),
            orderbook=broker_book(),tradebook=broker_trades(),positions=broker_positions(),
            source_authenticated=True,broker_owner_match=True,
            independent_account_verified=True,snapshot_at=NOW,now=NOW,
            restart_occurred=True)
        args.update(kwargs)
        return assess_restart(**args)

    def full(self):
        self.mark()
        self.buy()
        self.stop()

    def test_duplicate_reservation_never_resends(self):
        self.assertFalse(reserve(self.db,owner=OWNER,intent=INTENT,symbol=SYMBOL,
                                 token=TOKEN,quantity=130,now=NOW))
        self.assertEqual(self.mark(),"ACK_UNKNOWN")
        with self.assertRaises(ShadowJournalError):
            self.mark()
        self.assertTrue(snapshot(self.db,owner=OWNER,intent=INTENT)["manual_review_required"])

    def test_unknown_ack_cannot_become_order_without_identity_proof(self):
        self.mark()
        with self.assertRaises(ShadowJournalError):
            observe_entry(self.db,owner=OWNER,intent=INTENT,event_id="ev_buy_0001",
                broker_id=BUYID,broker_status="COMPLETE",cumulative_filled=130,
                snapshot_authenticated=True,asof=NOW,now=NOW,identity_linked=False)
        self.assertEqual(snapshot(self.db,owner=OWNER,intent=INTENT)["lifecycle"],"ACK_UNKNOWN")

    def test_broker_rejection_no_fill(self):
        self.mark()
        self.buy(0,"REJECTED")
        s=snapshot(self.db,owner=OWNER,intent=INTENT)
        self.assertEqual(s["lifecycle"],"REJECTED")
        self.assertEqual(s["net_open"],0)

    def test_partial_fill_shows_unprotected_gap(self):
        self.mark()
        self.buy(65,"PARTIAL")
        s=snapshot(self.db,owner=OWNER,intent=INTENT)
        self.assertEqual(s["protective_gap"],65)
        self.assertTrue(s["manual_review_required"])
        self.stop(65)
        s=snapshot(self.db,owner=OWNER,intent=INTENT)
        self.assertEqual(s["protective_gap"],0)
        r=self.recovered(orderbook=broker_book(65),
            tradebook=broker_trades(65),positions=broker_positions(65))
        self.assertIn("ENTRY_UNFILLED_REMAINDER_MUST_BE_RESOLVED",r["blockingReasons"])
        self.assertFalse(r["canSubmitOrder"])

    def test_full_fill_and_stop_shadow_reconcile(self):
        self.full()
        r=self.recovered()
        self.assertTrue(r["shadowConsistent"],r["blockingReasons"])
        self.assertFalse(r["canSubmitOrder"])
        self.assertFalse(r["liveExecutionEnabled"])
        self.assertEqual(r["brokerOrdersSent"],0)

    def test_recovery_fails_when_stop_missing(self):
        self.full()
        r=self.recovered(orderbook=broker_book()[:1])
        self.assertIn("OPEN_POSITION_WITHOUT_BROKER_STOP",r["blockingReasons"])

    def test_recovery_fails_if_stop_rejected(self):
        self.full()
        orders=broker_book()
        orders[1]["status"]="REJECTED"
        r=self.recovered(orderbook=orders)
        self.assertIn("BROKER_NATIVE_STOP_NOT_CONFIRMED",r["blockingReasons"])

    def test_missing_tradebook_cannot_pass(self):
        self.full()
        r=self.recovered(tradebook=[])
        self.assertIn("TRADEBOOK_SHADOW_FILL_MISMATCH",r["blockingReasons"])

    def test_stale_or_unowned_snapshot_fails(self):
        self.full()
        self.assertIn("BROKER_SNAPSHOT_NOT_FRESH",
                      self.recovered(snapshot_at=NOW-timedelta(seconds=20))["blockingReasons"])
        self.assertIn("OWNER_ACCOUNT_UNVERIFIED",
                      self.recovered(broker_owner_match=False)["blockingReasons"])

    def test_manual_order_and_other_open_position_block(self):
        self.full()
        orders=broker_book()
        orders.append({"id":"UNKNOWN","symbol":"BANKNIFTYNEW","status":"OPEN"})
        self.assertIn("UNTRACKED_BROKER_ORDERS",
                      self.recovered(orderbook=orders)["blockingReasons"])
        positions=broker_positions()
        positions.append({"symbol":"BANKNIFTYNEW","token":"232323","net_quantity":65})
        self.assertIn("OTHER_OPEN_BROKER_POSITIONS",
                      self.recovered(positions=positions)["blockingReasons"])

    def test_quantity_regression_and_oversize_rejected(self):
        self.mark()
        self.buy(65,"PARTIAL")
        for qty in (20,140):
            with self.subTest(qty=qty),self.assertRaises(ShadowJournalError):
                self.buy(qty,"PARTIAL","ev_buy_change"+str(qty))

    def test_complete_cannot_regress(self):
        self.mark()
        self.buy()
        with self.assertRaises(ShadowJournalError):
            self.buy(0,"OPEN","ev_buy_regress")

    def test_wrong_stop_coverage_rejected(self):
        self.mark()
        self.buy()
        with self.assertRaises(ShadowJournalError):
            self.stop(65)

    def test_duplicate_event_id_rejected_transactionally(self):
        self.mark()
        self.buy()
        with self.assertRaises(sqlite3.IntegrityError):
            observe_entry(self.db,owner=OWNER,intent=INTENT,event_id="ev_buy_0001",
                broker_id=BUYID,broker_status="COMPLETE",cumulative_filled=130,
                snapshot_authenticated=True,asof=NOW,now=NOW,identity_linked=True)
        self.assertEqual(snapshot(self.db,owner=OWNER,intent=INTENT)["observed_fill"],130)

    def test_exit_overage_fails_and_full_exit_needs_stop_resolution(self):
        self.full()
        with self.assertRaises(ShadowJournalError):
            record_exit(self.db,owner=OWNER,intent=INTENT,event_id="ev_exit_bad",
                cumulative_exit=131,broker_tradebook_verified=True,asof=NOW,now=NOW)
        self.assertEqual(record_exit(self.db,owner=OWNER,intent=INTENT,
            event_id="ev_exit_ok",cumulative_exit=130,
            broker_tradebook_verified=True,asof=NOW,now=NOW),0)
        self.assertTrue(snapshot(self.db,owner=OWNER,intent=INTENT)["manual_review_required"])
        r=self.recovered(orderbook=[
            broker_book()[0],
            {**broker_book()[1],"filled":130,"status":"COMPLETE"}],
            tradebook=broker_trades()+[{"trade_id":"T0000002","order_id":STOPID,
                                       "symbol":SYMBOL,"side":"SELL","quantity":130}],
            positions=broker_positions(0))
        self.assertIn("POSSIBLE_ORPHAN_STOP",r["blockingReasons"])

    def test_no_orders_missing_local_state_is_not_ready(self):
        r=assess_restart(local=None,orderbook=[],tradebook=[],positions=[],
            source_authenticated=True,broker_owner_match=True,independent_account_verified=True,
            snapshot_at=NOW,now=NOW)
        self.assertFalse(r["shadowConsistent"])
        self.assertFalse(r["canSubmitOrder"])

    def test_backup_reopen_preserves_unknown_state(self):
        self.mark()
        path=self.db.execute("PRAGMA database_list").fetchone()[2]
        self.db.close()
        self.db=open_dev_db(path)
        self.assertEqual(snapshot(self.db,owner=OWNER,intent=INTENT)["lifecycle"],"ACK_UNKNOWN")
        with self.assertRaises(ShadowJournalError):
            self.mark()


if __name__=="__main__":
    unittest.main()
