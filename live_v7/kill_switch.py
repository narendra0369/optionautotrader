"""OptionX V7: fail-closed emergency-stop state machine (development only).

ALL states are non-executing. There is intentionally no RUN, ARM or ENABLE
transition. This module cannot turn on real orders.

A later production implementation must persist events in a transactional,
durable DB, verify the owner using server-side authentication, and propagate
a STOP to every process/worker before permitting any future live flow.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Literal

State = Literal["STOPPED", "RESET_REQUESTED", "REVIEW_REQUIRED"]
Action = Literal["STOP", "REQUEST_RESET", "REQUIRE_REVIEW"]


class KillSwitchError(ValueError):
    pass


@dataclass(frozen=True)
class KillSwitch:
    state: State = "STOPPED"
    revision: int = 0
    reason: str = "DEFAULT_DENY"
    updated_at: str = ""

    @property
    def new_entries_blocked(self) -> bool:
        return True

    @property
    def live_execution_enabled(self) -> bool:
        return False


def startup_state() -> KillSwitch:
    """Always start STOPPED, including after reboot or missing DB."""
    return KillSwitch(updated_at=datetime.now(timezone.utc).isoformat())


def restored_state(raw: object) -> KillSwitch:
    """A missing or malformed persisted value is NOT permission to trade."""
    if not isinstance(raw, dict):
        return startup_state()
    state = raw.get("state")
    rev = raw.get("revision")
    reason = raw.get("reason")
    stamp = raw.get("updated_at")
    if (
        state not in ("STOPPED", "RESET_REQUESTED", "REVIEW_REQUIRED")
        or not isinstance(rev, int)
        or isinstance(rev, bool)
        or rev < 0
        or not isinstance(reason, str)
        or not (1 <= len(reason) <= 160)
        or not isinstance(stamp, str)
        or not stamp
    ):
        return startup_state()
    return KillSwitch(state=state, revision=rev, reason=reason, updated_at=stamp)


def transition(
    current: KillSwitch,
    action: Action,
    *,
    caller_is_verified_owner: bool,
    expected_revision: int,
    reason: str,
    now: datetime,
) -> KillSwitch:
    """Safe pure transition to another non-trading state.

    This is only a state-transition draft, not an auth or persistence service.
    A browser input claiming to be an owner is NEVER a trusted auth source.
    """
    if not isinstance(current, KillSwitch):
        raise KillSwitchError("Missing trusted switch state")
    if action not in ("STOP", "REQUEST_RESET", "REQUIRE_REVIEW"):
        raise KillSwitchError("Unsupported switch action")
    if caller_is_verified_owner is not True:
        raise KillSwitchError("Owner authentication required")
    if (
        not isinstance(expected_revision, int)
        or isinstance(expected_revision, bool)
        or current.revision != expected_revision
    ):
        raise KillSwitchError("Version conflict; no change")
    if not isinstance(now, datetime) or now.utcoffset() is None:
        raise KillSwitchError("Server time with timezone required")
    if not isinstance(reason, str) or not (1 <= len(reason.strip()) <= 160):
        raise KillSwitchError("Reason required")
    if action == "STOP":
        next_state: State = "STOPPED"
    elif action == "REQUEST_RESET":
        if current.state != "STOPPED":
            raise KillSwitchError("Reset may be requested only from STOPPED")
        next_state = "RESET_REQUESTED"
    else:
        next_state = "REVIEW_REQUIRED"
    return KillSwitch(
        state=next_state,
        revision=current.revision + 1,
        reason=reason.strip(),
        updated_at=now.astimezone(timezone.utc).isoformat(),
    )


def public_status(state: KillSwitch | None) -> dict[str, object]:
    """No caller can interpret any response as live authorization."""
    s = state if isinstance(state, KillSwitch) else startup_state()
    return {
        "state": s.state,
        "revision": s.revision,
        "newEntriesBlocked": True,
        "liveExecutionEnabled": False,
        "canSubmitOrder": False,
        "nextStep": "Independent broker approval and end-to-end tests required.",
    }
