"""Run a complete V8 simulated Angel order lifecycle on a disposable local DB.

Usage: python3 -m live_v8.offline_demo
No broker keys, no network, no production state. Explicitly OFFLINE ONLY.
"""
from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path
import tempfile

from .angel_order_plans import BrokerContract, preview_entry, preview_protective_stop
from .shadow_journal import (
    open_dev_db, reserve, mark_synthetic_send_unknown,
    observe_entry, observe_protection, snapshot,
)
from .restart_recovery import assess_restart


def run():
    now=datetime(2026, 11, 24, 5, 0, tzinfo=timezone.utc)
    owner="test_owner_001"
    intent="demo_trade_001"
    symbol="NIFTY27NOV2626000CE"  # SYNTHETIC contract, NOT verified against Angel today.
    token="123456"
    contract=BrokerContract(symbol,token,lot_size=65,tick_size="0.05",
                            contract_master_verified=True,
                            owner_account_verified=True)
    # Above booleans are simulated harness assertions ONLY, not real broker proofs.
    entry=preview_entry(contract=contract,qty=65,limit_price="155.00",intent_id=intent)
    stop=preview_protective_stop(contract=contract,filled_open_qty=65,
             trigger_price="140.00",limit_price="139.00",intent_id="demo_stop_001",
             fill_verified=True,position_verified=True,exit_rules_verified=True)
    with tempfile.TemporaryDirectory(prefix="optionx_v8_offline_") as temp:
        db=open_dev_db(Path(temp)/"shadow.sqlite3")
        try:
            reserved=reserve(db,owner=owner,intent=intent,symbol=symbol,
                              token=token,quantity=65,now=now)
            mark_synthetic_send_unknown(db,owner=owner,intent=intent,
                                         event_id="ev_send_demo",now=now)
            observe_entry(db,owner=owner,intent=intent,
                 event_id="ev_fill_demo",broker_id="SIMBUY_0001",
                 broker_status="COMPLETE",cumulative_filled=65,
                 snapshot_authenticated=True,identity_linked=True,asof=now,now=now)
            observe_protection(db,owner=owner,intent=intent,
                 event_id="ev_stop_demo",stop_order_id="SIMSTOP_0001",
                 protected_qty=65,snapshot_authenticated=True,
                 verified_stop_orderbook=True,asof=now,now=now)
            local=snapshot(db,owner=owner,intent=intent)
            reconcile=assess_restart(local=local,now=now,snapshot_at=now,
                 source_authenticated=True,broker_owner_match=True,
                 independent_account_verified=True,
                 orderbook=[
                    {"id":"SIMBUY_0001","symbol":symbol,"token":token,
                     "side":"BUY","quantity":65,"filled":65,"status":"COMPLETE"},
                    {"id":"SIMSTOP_0001","symbol":symbol,"token":token,
                     "side":"SELL","quantity":65,"filled":0,"status":"TRIGGER PENDING",
                     "variety":"STOPLOSS","ordertype":"STOPLOSS_LIMIT"}],
                 tradebook=[{"trade_id":"SIMTRADE_001","order_id":"SIMBUY_0001",
                             "symbol":symbol,"side":"BUY","quantity":65}],
                 positions=[{"symbol":symbol,"token":token,"net_quantity":65}])
            return {
                "mode":"OFFLINE_SIMULATION_NO_BROKER_API",
                "intentReserved":reserved,
                "entryOrderType":entry.payload["ordertype"],
                "entrySide":entry.payload["transactiontype"],
                "plannedStopType":stop.payload["ordertype"],
                "plannedStopSide":stop.payload["transactiontype"],
                "filledQuantity":local["observed_fill"],
                "stopCoverageQuantity":local["protective_qty"],
                "restartShadowConsistent":reconcile["shadowConsistent"],
                "newLiveEntriesBlocked":reconcile["newEntriesBlocked"],
                "canSubmitRealOrder":reconcile["canSubmitOrder"],
                "brokerOrdersSent":reconcile["brokerOrdersSent"],
                "note":"Sample NFO symbol is invented and *not tradable*. All broker observations are synthetic.",
            }
        finally:
            db.close()


def main():
    result=run()
    if (result["restartShadowConsistent"] is not True
        or result["brokerOrdersSent"] != 0
        or result["canSubmitRealOrder"] is not False):
        print("BLOCKED: OFFLINE_DEMO_REGRESSION")
        return 1
    print(json.dumps(result,indent=2))
    print("PASS: OFFLINE_BUY_FILL_STOP_AND_RESTART; LIVE_REAL_ORDERS_OFF")
    return 0


if __name__=="__main__":
    raise SystemExit(main())
