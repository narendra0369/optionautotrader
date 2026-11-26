"""V38 offline broker authorization provenance/expiry safety checkpoint.

This is a documentary evidence classifier, NOT a proof of message authenticity,
account permissions, or final broker activation. It has no order transport.
No combination of locally asserted evidence can unlock live orders.
"""
from __future__ import annotations

from collections.abc import Mapping
from datetime import datetime, timezone, timedelta
from hashlib import sha256
import re

MAX_EVIDENCE_AGE = timedelta(days=30)
STATES = frozenset({"PENDING", "CONDITIONAL", "APPROVED", "REVOKED", "UNKNOWN"})


class EvidenceInvalid(ValueError):
    pass


def _utc_aware(value):
    if not isinstance(value, datetime) or value.utcoffset() is None:
        raise EvidenceInvalid("AWARE_EVIDENCE_TIME_REQUIRED")
    return value.astimezone(timezone.utc)


def inspect_authorization(*, technical, compliance, trading_api,
                          undertaking, static_ip, now, expected_app_digest):
    """Check independent status claims while unconditionally blocking execution.

    Each piece of evidence is a *caller-supplied simulation*, not an
    authenticated broker statement. Required source category + app digest +
    expiry limit reduce accidental conflation but cannot prove authenticity.
    """
    at=_utc_aware(now)
    if (not isinstance(expected_app_digest,str) or
            not re.fullmatch(r"[a-f0-9]{64}",expected_app_digest)):
        raise EvidenceInvalid("EXPECTED_APP_DIGEST_INVALID")

    reasons={"REAL_EXECUTION_SOURCE_LOCKED",
             "LOCAL_EVIDENCE_CANNOT_PROVE_BROKER_AUTHENTICITY",
             "PRODUCTION_ORDER_LIFECYCLE_NOT_CERTIFIED",
             "FINAL_EXACT_ORDER_OWNER_CONSENT_NOT_COLLECTED"}
    required={
       "technical":(technical,"BROKER_TECHNICAL_APPROVAL"),
       "compliance":(compliance,"BROKER_COMPLIANCE_APPROVAL"),
       "trading_api":(trading_api,"ACCOUNT_TRADING_API_ENTITLEMENT"),
       "undertaking":(undertaking,"RETAIL_ALGO_UNDERTAKING"),
       "static_ip":(static_ip,"STATIC_IP_APP_CONFIRMATION"),
    }
    fields={}
    for kind,(record,label) in required.items():
        if not isinstance(record,Mapping):
            reasons.add(label+"_EVIDENCE_MISSING")
            fields[kind]="MISSING"
            continue
        status=record.get("status")
        if status not in STATES:
            reasons.add(label+"_STATUS_INVALID")
            fields[kind]="INVALID"
            continue
        fields[kind]=status
        if status!="APPROVED":
            reasons.add(label+"_"+status)
        # Caller-supplied asserted source categories are advisory only.
        if record.get("source_category") != "BROKER_OFFICIAL":
            reasons.add(label+"_SOURCE_UNVERIFIED")
        if record.get("app_digest") != expected_app_digest:
            reasons.add(label+"_APP_MISMATCH")
        when=record.get("issued_at")
        if not isinstance(when,datetime) or when.utcoffset() is None:
            reasons.add(label+"_DATE_INVALID")
            continue
        stamp=when.astimezone(timezone.utc)
        if stamp>at:
            reasons.add(label+"_DATE_IN_FUTURE")
        elif at-stamp>MAX_EVIDENCE_AGE:
            reasons.add(label+"_EVIDENCE_EXPIRED")
    return {
        "documentaryStatuses":fields,
        "blockedReasons":sorted(reasons),
        "allClaimedApproved":all(v=="APPROVED" for v in fields.values()) and len(fields)==5,
        "evidenceAuthenticatedByThisModule":False,
        "canSubmitOrder":False,
        "canCancelOrder":False,
        "canModifyOrder":False,
        "canRetryUnknownOrder":False,
        "canAutoResubmitLPP17070":False,
        "manualPositionModified":False,
        "realOrdersEnabled":False,
        "status":"DOCUMENTARY_EVIDENCE_ONLY",
    }


def app_reference_digest(application_reference):
    """Hash a non-secret reference locally; not a substitute for broker proof."""
    if (not isinstance(application_reference,str) or
            not 1<=len(application_reference)<=128):
        raise EvidenceInvalid("APPLICATION_REFERENCE_INVALID")
    return sha256(application_reference.encode("utf-8")).hexdigest()
