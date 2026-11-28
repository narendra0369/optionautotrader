"""V46 owner-only live unlock readiness, never a broker execution switch.

Website button asks server for verifiable status only. This module does not
alter stop guards, accept approval claims from clients, or send any order.
"""
from __future__ import annotations
from live_v7.angel_execution_transport import capabilities as execution_capabilities

def live_unlock_status(*, owner_match:bool, verified_session:bool):
    transport=execution_capabilities()
    blocked=[]
    if owner_match is not True:
        blocked.append("OWNER_BINDING_UNVERIFIED_ON_THIS_SERVER")
    if verified_session is not True:
        blocked.append("BROKER_SESSION_NOT_ACTIVE_ON_THIS_SERVER")
    if transport.get("sourceLockEnabled") is not False:
        blocked.append("BROKER_TRANSPORT_SOURCE_LOCKED")
    # These must derive from independently audited production systems,
    # never a browser toggle, check box or user-supplied form.
    blocked.extend((
        "PRODUCTION_ORDER_JOURNAL_NOT_CERTIFIED",
        "LIVE_ORDER_RECOVERY_NOT_CERTIFIED",
        "PRODUCTION_STOP_GUARD_NOT_RELEASED",
        "ACCOUNT_WRITE_ENTITLEMENT_NOT_INDEPENDENTLY_VERIFIED",
    ))
    return {
        "mode":"OWNER_READINESS_ONLY",
        "liveOrdersEnabled":False,
        "canSubmitOrder":False,
        "canCancelOrder":False,
        "canUnlockFromBrowser":False,
        "ownerMatchOnThisServer":owner_match is True,
        "brokerSessionOnThisServer":verified_session is True,
        "blockers":blocked,
        "message":"Real orders remain OFF. This is an owner-only readiness check; it cannot bypass the AWS source lock or STOP guard."
    }
