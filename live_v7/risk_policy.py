"""OptionX V7 capital and lot-size policy: no live order authorization.

Preserves the owner's previously selected *paper* tier model:
₹30,000 virtual starting capital -> 1 lot; each additional ₹40,000 -> 1 lot,
₹300 risk / lot, ₹600 target / lot, ₹600 daily-stop / lot.
At ₹500,000 virtual: 12 lots, ₹3,600 risk, ₹7,200 target/stop.

This is a research position-size policy, not a broker margin/risk guarantee.
For real orders, risk must be recalculated using actual contract lot sizes,
premium, margin, bid/ask spread and execution costs; the live profile remains
disabled until the owner confirms a distinct live-funds risk plan.
"""
from __future__ import annotations

from decimal import Decimal, InvalidOperation
from typing import Any

PAPER_START = Decimal("30000")
PAPER_STEP = Decimal("40000")
PAPER_BASE_LOT = 1
PAPER_RISK_PER_LOT = Decimal("300")
PAPER_TARGET_PER_LOT = Decimal("600")
PAPER_DAILY_STOP_PER_LOT = Decimal("600")
MAX_TRADES_PER_DAY = 2


class RiskPolicyError(ValueError):
    pass


def _rupees(x: Any) -> Decimal:
    if isinstance(x, bool) or not isinstance(x, (str, int, Decimal)):
        raise RiskPolicyError("Exact cash value required")
    try:
        out = Decimal(x)
    except (ValueError, InvalidOperation, TypeError):
        raise RiskPolicyError("Invalid cash") from None
    if not out.is_finite() or out < 0:
        raise RiskPolicyError("Cash must be nonnegative and finite")
    return out


def stepped_paper_plan(virtual_capital: str | int | Decimal) -> dict[str, object]:
    cash = _rupees(virtual_capital)
    lots = (PAPER_BASE_LOT + int((cash - PAPER_START) // PAPER_STEP)) if cash >= PAPER_START else 0
    return {
        "market": "PAPER_RESEARCH_ONLY",
        "virtualCapitalINR": str(cash),
        "illustrativeLots": lots,
        "riskINR": str(PAPER_RISK_PER_LOT * lots),
        "rewardINR": str(PAPER_TARGET_PER_LOT * lots),
        "dailyStopINR": str(PAPER_DAILY_STOP_PER_LOT * lots),
        "maxTradesPerDay": MAX_TRADES_PER_DAY,
        "lotSizeVerifiedByBroker": False,
        "premiumAndMarginVerified": False,
        "canSubmitOrder": False,
        "liveExecutionEnabled": False,
    }


def live_risk_readiness(
    *,
    user_approved_live_budget: bool,
    confirmed_contract_lot_size: bool,
    execution_grade_quote: bool,
    verified_margin_available: bool,
    max_loss_includes_costs_and_slippage: bool,
    daily_loss_broker_reconciled: bool,
    broker_risk_approval: bool,
) -> dict[str, object]:
    """No live profile can be enabled from this source-only V7 version."""
    fields = {
        "USER_APPROVED_LIVE_BUDGET": user_approved_live_budget,
        "BROKER_LOT_SIZE": confirmed_contract_lot_size,
        "EXECUTION_GRADE_QUOTE": execution_grade_quote,
        "VERIFIED_MARGIN": verified_margin_available,
        "COSTS_AND_SLIPPAGE": max_loss_includes_costs_and_slippage,
        "BROKER_RECONCILED_DAILY_PNL": daily_loss_broker_reconciled,
        "BROKER_RISK_APPROVAL": broker_risk_approval,
    }
    missing = [key for key, valid in fields.items() if valid is not True]
    return {
        "mode": "LIVE_RISK_PREPARATION_ONLY",
        "missing": missing,
        "liveBudgetNotAutoCopiedFromPaper": True,
        "additionalTestsAndExplicitApprovalRequired": True,
        "maxTradesPerDayHardCap": MAX_TRADES_PER_DAY,
        "canSubmitOrder": False,
        "liveExecutionEnabled": False,
    }
