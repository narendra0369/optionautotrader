"""OPTIONX V83 offline-only safety reference. No I/O, secrets, network, or broker APIs."""
from dataclasses import dataclass, replace
from enum import Enum

READ_SCOPES = frozenset({"status.read", "diagnostics.read"})
MAX_ENTRIES_PER_DAY = 2

@dataclass(frozen=True)
class GateInputs:
    scope: str
    owner_authenticated: bool = False
    independently_attested: bool = False
    reviewer_separate: bool = False
    proof_fresh: bool = False
    nonce_unique: bool = False
    reviewer_not_revoked: bool = False
    worker_verified: bool = False
    owner_stop: bool = True

def diagnostic_scope_allowed(g: GateInputs) -> bool:
    """Offline policy only: TRUE permits a mock diagnostic, NEVER broker action."""
    return (g.scope in READ_SCOPES
            and g.owner_authenticated
            and g.independently_attested and g.reviewer_separate
            and g.proof_fresh and g.nonce_unique
            and g.reviewer_not_revoked and g.worker_verified)
    # owner_stop intentionally does NOT grant any execution permission.

def live_execution_permitted(g: GateInputs) -> bool:
    """V83 cannot authorize real orders under ANY conditions."""
    return False

@dataclass(frozen=True)
class PaperRisk:
    balance: int
    entries_today: int
    loss_today: int = 0

    @property
    def lots(self) -> int:
        return max(1, 1 + (max(0, self.balance - 30000) // 40000))

    @property
    def trade_risk(self) -> int:
        return 300 * self.lots

    @property
    def target(self) -> int:
        return 600 * self.lots

    @property
    def daily_loss_limit(self) -> int:
        return 600 * self.lots

    def new_paper_entry_allowed(self, owner_stop: bool) -> bool:
        return (not owner_stop and self.entries_today < MAX_ENTRIES_PER_DAY
                and self.loss_today < self.daily_loss_limit)

class OrderState(str, Enum):
    NEW = "NEW"
    PARTIAL = "PARTIAL"
    FILLED = "FILLED"
    CANCELLED = "CANCELLED"
    CLOSED = "CLOSED"
    NEEDS_RECONCILIATION = "NEEDS_RECONCILIATION"

@dataclass(frozen=True)
class OfflineOrder:
    requested_qty: int
    filled_qty: int = 0
    exited_qty: int = 0
    state: OrderState = OrderState.NEW

def mock_fill(order: OfflineOrder, additional_qty: int) -> OfflineOrder:
    if order.state not in (OrderState.NEW, OrderState.PARTIAL):
        raise ValueError("FILL_INVALID_STATE")
    if additional_qty <= 0 or order.filled_qty + additional_qty > order.requested_qty:
        raise ValueError("INVALID_FILL_QUANTITY")
    total = order.filled_qty + additional_qty
    return replace(order, filled_qty=total,
                   state=OrderState.FILLED if total == order.requested_qty else OrderState.PARTIAL)

def mock_cancel(order: OfflineOrder) -> OfflineOrder:
    if order.state not in (OrderState.NEW, OrderState.PARTIAL):
        raise ValueError("CANCEL_REQUIRES_OPEN_ENTRY")
    # Partial fills leave exposure: reconciliation is mandatory, not 'flat'.
    return replace(order, state=(OrderState.NEEDS_RECONCILIATION
                                if order.filled_qty else OrderState.CANCELLED))

def mock_exit(order: OfflineOrder, qty: int, reason: str) -> OfflineOrder:
    if reason not in ("SL", "TARGET") or order.state not in (OrderState.FILLED, OrderState.PARTIAL):
        raise ValueError("EXIT_NOT_PERMITTED")
    if qty <= 0 or qty > order.filled_qty - order.exited_qty:
        raise ValueError("INVALID_EXIT_QUANTITY")
    exited = order.exited_qty + qty
    return replace(order, exited_qty=exited,
                   state=(OrderState.CLOSED if exited == order.filled_qty and order.state == OrderState.FILLED
                          else OrderState.NEEDS_RECONCILIATION))
