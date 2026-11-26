"""V50 server-side owner activation coordinator (AWS-only read of readiness).

HTTP must authenticate exact owner independently and provide neither arbitrary
server_evidence nor transport lock flags from browser. Currently no independent
broker WRITE attestation provider is wired: fail closed with explicit blockers.
"""
from __future__ import annotations
from datetime import datetime, timezone
from live_v7.angel_execution_transport import capabilities
from live_v7.owner_activation_v50 import CHECKS, eligibility

def inspect_owner_activation(*, owner_authenticated, now=None):
    clock=now if now is not None else datetime.now(timezone.utc)
    # No known completed live broker lifecycle write test. V41 read-only
    # success, V45 fake Postgres and V49 mock gateway are NOT real evidence.
    trusted={k:False for k in CHECKS}
    if owner_authenticated is True:
        # Do not assert MFA unless user session is freshly independently proven.
        trusted["owner_session_mfa_fresh"]=False
    status=eligibility(evidence=trusted,owner_verified=owner_authenticated,
                       now=clock)
    locked=capabilities().get("sourceLockEnabled") is not False
    if locked: status["blockers"].append("ANGEL_SOURCE_LOCK_STILL_ACTIVE")
    return {"state":"STOPPED","eligible":False,
            "blockers":status["blockers"],"canRequestActivation":True,
            "canArmNow":False,"canSubmitOrder":False,
            "liveOrdersEnabled":False,
            "message":"Production eligibility is not yet verified. Owner action cannot bypass source lock or replace broker write certification."}
