"""V49 stopped-mode broker lifecycle integration harness.

Integrates V43 durable intent fencing, V44 strict order/tradebook
reconciliation and V47 persistent owner STOP with a synthetic broker.
No Angel session, SDK, network or production database is used. A successful
simulation can NEVER grant broker order permissions.

A mock dispatch is invoked at most once after committing an uncertain-send
fence, and only for a NEW reservation. Existing reservations are not retried.
"""
from __future__ import annotations

from datetime import datetime, timezone

from live_v7.durable_intent_v43 import reserve, seal_uncertain, recover
from live_v7.owner_control_store_v47 import read_state
from live_v7.broker_reconciliation_v44 import reconcile

class LifecycleBlocked(RuntimeError):
    pass

def _off(*, phase, reason, reconciliation=None):
    return {
        "phase":phase,"reason":reason,
        "reconciliation":reconciliation,
        "canSubmitOrder":False,"canRetryUnknownOrder":False,
        "canCancelOrder":False,"liveOrdersEnabled":False,
        "brokerOrdersSent":0,
    }

def run_mock_cycle(*, intent_db, control_db, owner_id, intent_key,
                   draft, now, mock_gateway, scenario):
    """Execute a ONE-SHOT SYNTHETIC lifecycle using mock-only inputs.

    `mock_gateway` must explicitly identify itself as a synthetic gateway
    via `mock_only is True`. This is insufficient for production safety:
    the worker never imports, calls or releases any Angel execution method.
    """
    if not isinstance(now,datetime) or now.utcoffset() is None:
        raise LifecycleBlocked("AWARE_TIME_REQUIRED")
    if getattr(mock_gateway,"mock_only",None) is not True:
        raise LifecycleBlocked("MOCK_GATEWAY_ONLY")
    if not callable(getattr(mock_gateway,"simulate",None)):
        raise LifecycleBlocked("MOCK_SIMULATOR_REQUIRED")
    if read_state(control_db,owner_id=owner_id).get("stopPersisted") is not True:
        raise LifecycleBlocked("PERSISTENT_STOP_REQUIRED")
    if scenario not in ("COMPLETE","PARTIAL","REJECTED","UNKNOWN","CANCELLED"):
        raise LifecycleBlocked("SCENARIO_NOT_ALLOWLISTED")
    # Always preserve the real owner engine in STOPPED/REVIEW_REQUESTED.
    # Neither control state authorizes a real order or a real gateway.
    staged=reserve(intent_db,owner_id=owner_id,
                   idempotency_key=intent_key,order=draft,now=now)
    if staged["result"]!="RESERVED_ONLY":
        return _off(phase="DUPLICATE_NO_DISPATCH",
                    reason="EXISTING_DURABLE_INTENT_NO_RETRY")
    # Commit uncertainty BEFORE simulated dispatch, mirroring the critical
    # crash boundary for future integration tests.
    seal_uncertain(intent_db,owner_id=owner_id,idempotency_key=intent_key,now=now)
    try:
        simulation=mock_gateway.simulate(scenario=scenario,draft=dict(draft))
    except Exception:
        return _off(phase="UNKNOWN_OUTCOME_REQUIRES_RECONCILIATION",
                    reason="SYNTHETIC_GATEWAY_EXCEPTION_NO_RETRY")
    if not isinstance(simulation,dict):
        return _off(phase="UNKNOWN_OUTCOME_REQUIRES_RECONCILIATION",
                    reason="SYNTHETIC_GATEWAY_RESPONSE_INVALID")
    if simulation.get("outcome")!="ACK":
        return _off(phase="UNKNOWN_OUTCOME_REQUIRES_RECONCILIATION",
                    reason="NO_CONFIRMED_SYNTHETIC_ACK")
    broker_id=simulation.get("order_id")
    if not isinstance(broker_id,str) or len(broker_id)<4:
        return _off(phase="UNKNOWN_OUTCOME_REQUIRES_RECONCILIATION",
                    reason="SYNTHETIC_ACK_MISSING_ID")
    book=simulation.get("orderbook")
    trades=simulation.get("tradebook")
    order_intent={
        "broker_order_id":broker_id,
        "tradingsymbol":draft["contract"],
        "symboltoken":draft["token"],
        "transactiontype":draft["side"],
        "quantity":draft["quantity"],
        "producttype":simulation.get("producttype"),
    }
    result=reconcile(
        intent=order_intent,orderbook=book,tradebook=trades,
        as_of=now,now=now,owner_authenticated=True,
        book_sources_verified=True)
    phase="MOCK_BOOKS_CONSISTENT" if not result["blockers"] else "REVIEW_REQUIRED"
    return _off(phase=phase,reason="SYNTHETIC_EVIDENCE_ONLY",
                reconciliation=result)

class DeterministicMockGateway:
    """Local deterministic synthetic broker with explicit mock_only."""
    mock_only=True

    def __init__(self):
        self.calls=0

    def simulate(self,*,scenario,draft):
        self.calls+=1
        if scenario=="UNKNOWN":
            return {"outcome":"UNKNOWN"}
        status={"COMPLETE":"complete","PARTIAL":"partially filled",
                "REJECTED":"rejected","CANCELLED":"cancelled"}[scenario]
        quantity=draft["quantity"]
        filled=quantity if scenario=="COMPLETE" else quantity//2 if scenario=="PARTIAL" else 0
        broker_id="MOCK-ORDER-49"
        producttype="CARRYFORWARD"
        row={
            "orderid":broker_id,"tradingsymbol":draft["contract"],
            "symboltoken":draft["token"],"transactiontype":draft["side"],
            "producttype":producttype,"quantity":str(quantity),
            "filledshares":str(filled),"status":status,
        }
        trades=([{"orderid":broker_id,"tradeid":"MOCK-TRADE-49",
            "tradingsymbol":draft["contract"],"symboltoken":draft["token"],
            "transactiontype":draft["side"],"producttype":producttype,
            "fillshares":str(filled),"fillprice":draft["limit"]}]
            if filled>0 else [])
        return {"outcome":"ACK","order_id":broker_id,"producttype":producttype,
                "orderbook":[row],"tradebook":trades}
