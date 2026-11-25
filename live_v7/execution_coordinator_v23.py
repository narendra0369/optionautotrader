"""V23 fail-closed ownership, protective exit and restart RECOVERY simulation.

No broker order transport. No trading authorization. This is an isolated,
deterministic state-machine used for offline crash/network/partial-fill tests.
It DOES NOT modify a real/manual broker position, submit stop, modify target,
or lift the persistent production STOPPED guard.

A native STOPLOSS_LIMIT ACK never guarantees stop execution, and placing both
independent SL and TP SELL orders without an exchange-supported OCO can cause
over-selling. For this reason target submission is NEVER approved here.
"""
from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime, timedelta
from typing import Mapping, Sequence, Any

MAX_AGE=timedelta(seconds=10)


class CoordinationError(ValueError):
    pass


def _valid_int(v: Any, *, minimum: int = 0) -> bool:
    return type(v) is int and minimum <= v <= 2_000_000_000


def _fresh(stamp: datetime, now: datetime) -> bool:
    return (
        isinstance(stamp,datetime) and isinstance(now,datetime)
        and stamp.utcoffset() is not None and now.utcoffset() is not None
        and timedelta(0) <= now-stamp <= MAX_AGE
    )


@dataclass(frozen=True)
class OwnedPosition:
    """ONLY platform-owned order IDs supplied from trusted durable ledger."""
    entry_order_id: str
    contract_token: str
    symbol: str
    entry_filled: int
    exit_filled: int = 0
    stop_order_id: str | None = None
    stop_active_remaining: int = 0
    target_order_id: str | None = None
    exit_outcome_unknown: bool = False

    @property
    def net_open(self) -> int:
        return self.entry_filled-self.exit_filled


def _validate(pos: OwnedPosition) -> None:
    if not isinstance(pos,OwnedPosition):
        raise CoordinationError("TRUSTED_OWNED_POSITION_REQUIRED")
    if not pos.entry_order_id or not pos.contract_token or not pos.symbol:
        raise CoordinationError("OWNED_IDENTITY_INVALID")
    if not _valid_int(pos.entry_filled) or not _valid_int(pos.exit_filled) or pos.exit_filled>pos.entry_filled:
        raise CoordinationError("POSITION_QUANTITY_INVALID")
    if not _valid_int(pos.stop_active_remaining) or pos.stop_active_remaining>pos.net_open:
        raise CoordinationError("STOP_QUANTITY_EXCEEDS_OWNED_OPEN_POSITION")
    if pos.stop_order_id is None and pos.stop_active_remaining:
        raise CoordinationError("STOP_ID_MISSING")
    if pos.stop_order_id is not None and pos.stop_order_id==pos.entry_order_id:
        raise CoordinationError("STOP_REUSES_ENTRY_ID")
    if pos.target_order_id and pos.target_order_id in (pos.entry_order_id,pos.stop_order_id):
        raise CoordinationError("TARGET_ORDER_ID_COLLISION")


def recover_snapshot(*,owned_positions:Sequence[OwnedPosition],
                     broker_orders:Sequence[Mapping[str,Any]],
                     broker_positions:Sequence[Mapping[str,Any]],
                     authenticated_owner:bool, authenticated_broker:bool,
                     books_complete:bool,as_of:datetime,now:datetime,
                     persisted_guard_state:str="STOPPED",
                     daily_auto_entry_reservations:int=0) -> dict[str,Any]:
    """Fail-closed preflight after startup or reconnect, never issue retries.

    Manual broker rows with unknown IDs never become platform-owned, even if
    the same contract appears. A shared account position net quantity cannot
    be assigned to OptionX from symbol alone.
    """
    reasons={"LIVE_ORDER_TRANSPORT_SOURCE_LOCKED"}
    if authenticated_owner is not True or authenticated_broker is not True:
        reasons.add("UNAUTHENTICATED_RECOVERY_SNAPSHOT")
    if books_complete is not True or not _fresh(as_of,now):
        reasons.add("STALE_OR_INCOMPLETE_BROKER_BOOKS")
    if persisted_guard_state!="STOPPED":
        reasons.add("PERSISTED_KILL_SWITCH_INVALID")
    if not _valid_int(daily_auto_entry_reservations) or daily_auto_entry_reservations>2:
        reasons.add("DAILY_ENTRY_COUNTER_INVALID_OR_EXCEEDED")
    if not isinstance(owned_positions,(list,tuple)) or not isinstance(broker_orders,(list,tuple)) or not isinstance(broker_positions,(list,tuple)):
        raise CoordinationError("RECOVERY_BOOK_SHAPE_INVALID")
    if len(broker_orders)>500 or len(broker_positions)>500 or len(owned_positions)>500:
        raise CoordinationError("RECOVERY_BOOK_TOO_LARGE")
    owned={}
    for pos in owned_positions:
        _validate(pos)
        if pos.entry_order_id in owned:
            reasons.add("DUPLICATE_OWNED_ORDER_ID")
        owned[pos.entry_order_id]=pos
        if pos.exit_outcome_unknown:
            reasons.add("UNKNOWN_EXIT_OUTCOME_NO_RETRY")
        if pos.net_open>0 and pos.stop_active_remaining!=pos.net_open:
            reasons.add("OPEN_EXPOSURE_WITHOUT_FULL_STOP")
        if pos.target_order_id:
            reasons.add("UNRESOLVED_TARGET_EXIT_OCO_RACE")
    broker_ids=set()
    untracked=0
    for row in broker_orders:
        if not isinstance(row,Mapping):
            reasons.add("INVALID_BROKER_ORDER_ROW")
            continue
        oid=row.get("order_id")
        if not isinstance(oid,str) or not oid:
            reasons.add("INVALID_BROKER_ORDER_ID")
            continue
        if oid in broker_ids:
            reasons.add("DUPLICATE_BROKER_ORDER_ID")
        broker_ids.add(oid)
        # Stop and target ids may belong to platform, only if ledger owns them.
        platform_ids=set(owned)
        platform_ids.update(p.stop_order_id for p in owned_positions if p.stop_order_id)
        platform_ids.update(p.target_order_id for p in owned_positions if p.target_order_id)
        if oid not in platform_ids:
            untracked+=1
    if untracked:
        reasons.add("MANUAL_OR_UNTRACKED_ORDER_PRESENT")
    for pos in owned_positions:
        if pos.entry_order_id not in broker_ids:
            reasons.add("OWNED_ENTRY_ORDER_NOT_FOUND")
        if pos.stop_order_id and pos.stop_order_id not in broker_ids:
            reasons.add("OWNED_STOP_ORDER_NOT_FOUND")
    exposed=0
    for row in broker_positions:
        if not isinstance(row,Mapping) or type(row.get("net_quantity")) is not int:
            reasons.add("INVALID_BROKER_POSITION_ROW")
            continue
        if row["net_quantity"]:
            exposed+=1
    if exposed:
        reasons.add("ACCOUNT_POSITION_OWNERSHIP_NOT_PARTITIONED")
    return {"recoveredForShadowInspection":not (
                reasons-{"LIVE_ORDER_TRANSPORT_SOURCE_LOCKED"}),
            "untrackedBrokerOrderCount":untracked,
            "positionsWithExposure":exposed,
            "blockedReasons":sorted(reasons),
            "newEntriesBlocked":True,"canResendAmbiguousOrder":False,
            "canCancelOrder":False,"canSubmitOrder":False,
            "liveOrdersEnabled":False,"manualPositionsModified":False}


def evaluate_exit(*,position:OwnedPosition,broker_stop_order:Mapping[str,Any]|None,
                  broker_authenticated:bool,as_of:datetime,now:datetime,
                  target_requested:bool,stop_cancel_confirmation:bool=False) -> dict[str,Any]:
    """No synthetic OCO. Gate every target transition behind hard stop.

    Target cannot be staged while an active or uncertain stop exists: merely
    asking broker to cancel an SL is not confirmation of cancel/fill state.
    Pending stop fill and target races always require broker reconciliation.
    """
    _validate(position)
    reasons=set()
    if broker_authenticated is not True or not _fresh(as_of,now):
        reasons.add("BROKER_STOP_BOOK_UNVERIFIED")
    if position.exit_outcome_unknown:
        reasons.add("AMBIGUOUS_EXIT_OUTCOME")
    if position.net_open==0:
        reasons.add("ALREADY_FLAT_NO_MORE_SELL")
    if position.net_open>0:
        if not position.stop_order_id:
            reasons.add("STOP_NOT_PLACED_OR_UNKNOWN")
        if position.stop_active_remaining!=position.net_open:
            reasons.add("STOP_QUANTITY_NOT_EQUAL_OPEN_EXPOSURE")
    if position.stop_order_id:
        if not isinstance(broker_stop_order,Mapping):
            reasons.add("BROKER_STOP_ORDER_MISSING")
        else:
            if broker_stop_order.get("order_id")!=position.stop_order_id:
                reasons.add("STOP_NOT_PLATFORM_OWNED")
            if broker_stop_order.get("symbol")!=position.symbol or broker_stop_order.get("contract_token")!=position.contract_token:
                reasons.add("STOP_CONTRACT_MISMATCH")
            if broker_stop_order.get("side")!="SELL":
                reasons.add("STOP_SIDE_INVALID")
            if not _valid_int(broker_stop_order.get("remaining_quantity")) or broker_stop_order.get("remaining_quantity")!=position.stop_active_remaining:
                reasons.add("STOP_REMAINING_QUANTITY_MISMATCH")
            if broker_stop_order.get("status") not in ("OPEN","TRIGGER_PENDING"):
                reasons.add("STOP_NOT_BROKER_ACTIVE")
    if target_requested:
        reasons.add("NO_CERTIFIED_ATOMIC_OCO_NO_TARGET_ORDER")
        if position.stop_order_id and stop_cancel_confirmation is not True:
            reasons.add("STOP_CANCELLATION_NOT_CONFIRMED")
        # Even a cancelled STOP is insufficient: independent tradebook and
        # fresh positions must re-check remaining exposure before a target.
        if stop_cancel_confirmation is True:
            reasons.add("POST_CANCEL_RECONCILIATION_REQUIRED")
    return {"stopCoverageShadowVerified":not reasons and position.net_open>0,
            "targetOrderAllowed":False,
            "canPlaceOrCancelBrokerOrder":False,
            "canSubmitOrder":False,"newEntriesBlocked":True,
            "liveOrdersEnabled":False,
            "blockedReasons":sorted(reasons|{"LIVE_ORDER_TRANSPORT_SOURCE_LOCKED"})}


def apply_verified_exit_fill(*,position:OwnedPosition,exit_order_id:str,
                             newly_confirmed_cumulative_exit_qty:int,
                             broker_authenticated:bool,
                             tradebook_verified:bool)->OwnedPosition:
    """Pure monotonic lifecycle; do not infer sell from HTTP ACK.
    
    Unknown/manual broker order IDs NEVER change platform-owned position.
    """
    _validate(position)
    if broker_authenticated is not True or tradebook_verified is not True:
        raise CoordinationError("BROKER_TRADEBOOK_EXIT_NOT_VERIFIED")
    if exit_order_id not in (position.stop_order_id,position.target_order_id):
        raise CoordinationError("EXIT_ORDER_NOT_OWNED")
    if not _valid_int(newly_confirmed_cumulative_exit_qty):
        raise CoordinationError("EXIT_FILL_QUANTITY_INVALID")
    if (newly_confirmed_cumulative_exit_qty<position.exit_filled or
            newly_confirmed_cumulative_exit_qty>position.entry_filled):
        raise CoordinationError("EXIT_FILL_REGRESSION_OR_OVERSELL")
    # Updated stop remaining must be re-fetched from broker; do NOT copy the
    # old acknowledged stop quantity into a now-smaller open exposure.
    return replace(position,exit_filled=newly_confirmed_cumulative_exit_qty,
                   stop_active_remaining=0, exit_outcome_unknown=True)
