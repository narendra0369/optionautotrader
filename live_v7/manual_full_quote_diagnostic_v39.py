"""V39 staged Angel FULL quote read-only diagnostic, no order transport.

Never logs broker responses, account identifiers, credentials or exception text.
It checks the same read-only path as V32 with named failure stages.
All real-order execution remains source locked.
"""
from __future__ import annotations

from datetime import datetime, timezone
import angel_gateway
from live_v7.aws_angel_owner_reader import _config, verify_login
from live_v7.angel_books_readonly import read_book
from live_v7.manual_sl_preflight_v26 import assess_manual_positions
from live_v7.manual_full_quote_readonly_v32 import (
    fetch_full_quote, SYMBOL, TOKEN, EXPECTED_QTY,
)

SAFE_STAGES = frozenset({
    "CONFIG", "AUTHENTICATION", "POSITIONS_READ", "ORDERS_READ",
    "POSITION_CHECK", "FULL_QUOTE", "FEED_FRESHNESS",
})


def stage_failure(stage):
    if stage not in SAFE_STAGES:
        stage = "UNKNOWN"
    return {
        "status": "BLOCKED",
        "stage": stage,
        "canSubmitOrder": False,
        "realOrdersEnabled": False,
    }


def assess_position(positions, orders):
    """Same V32 exact position guard, with safe coarse reasons only."""
    inspected = assess_manual_positions(positions, orders)
    if len(inspected) != 1:
        return "POSITION_COUNT_CHANGED"
    item = inspected[0]
    if item["contract"] != SYMBOL or item["instrumentToken"] != TOKEN:
        return "POSITION_CONTRACT_CHANGED"
    if item["netLongQuantity"] != EXPECTED_QTY:
        return "POSITION_QUANTITY_CHANGED"
    if item["activeSellOrders"] != 0:
        return "SELL_ORDER_CONFLICT"
    for order in orders:
        if order.get("symbol") == SYMBOL and not order.get("statusKnown", False):
            return "ORDER_STATUS_UNKNOWN"
    return "PASS"


def diagnostic_run():
    owner = None
    stage = "CONFIG"
    try:
        owner, client = _config()
        stage = "AUTHENTICATION"
        verify_login(owner, client)
        print("V39_AUTHENTICATION: PASS", flush=True)

        stage = "POSITIONS_READ"
        positions = read_book(owner, "positions")["positions"]
        print("V39_POSITIONS_READ: PASS", flush=True)

        stage = "ORDERS_READ"
        orders = read_book(owner, "orderbook")["orders"]
        print("V39_ORDERS_READ: PASS", flush=True)

        stage = "POSITION_CHECK"
        reason = assess_position(positions, orders)
        if reason != "PASS":
            print("V39_POSITION_CHECK: " + reason, flush=True)
            return 2
        print("V39_POSITION_CHECK: PASS", flush=True)

        stage = "FULL_QUOTE"
        quote = fetch_full_quote(owner)
        print("V39_FULL_QUOTE: PASS", flush=True)

        stage = "FEED_FRESHNESS"
        if quote.get("brokerReportedFeedAgeWithin10s") is not True:
            print("V39_FEED_FRESHNESS: STALE_OR_UNVERIFIED", flush=True)
            return 2
        print("V39_FEED_FRESHNESS: PASS", flush=True)
        print("V39_DIAGNOSTIC: PASS_READ_ONLY", flush=True)
        return 0
    except Exception:
        # Deliberately never print exception payloads, full account IDs,
        # JWT/token, broker orderbook, API key, PIN or TOTP.
        result = stage_failure(stage)
        print("V39_DIAGNOSTIC: " + result["status"], flush=True)
        print("V39_BLOCK_STAGE: " + result["stage"], flush=True)
        return 2
    finally:
        if owner:
            try:
                angel_gateway.disconnect(owner)
            except Exception:
                pass
        print("BROKER_ORDER_SUBMITTED: NO | REAL_ORDERS: OFF", flush=True)


if __name__ == "__main__":
    raise SystemExit(diagnostic_run())
