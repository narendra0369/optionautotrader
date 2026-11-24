"""Pure Angel One day-bound READ-ONLY session lifetime policy.

The official SmartAPI documentation says an authenticated session usually
lasts until the broker's daily session boundary, but the broker can revoke
or reject it sooner. This policy NEVER extends a token beyond its signed
JWT 'exp' *claim*, and it only uses 'exp' to shorten/limit, never as proof
of JWT authenticity. The profile is independently checked by the existing
broker login flow. Missing/opaque/invalid JWT expiries retain the old
15-minute conservative limit. No credentials or network calls here.

The optional extended policy is for a separately trusted, owner-bound AWS
HTTPS process ONLY, never a reason to enable real-money order execution.
"""
from __future__ import annotations

import base64
import binascii
from datetime import datetime, timedelta, timezone
import json
from zoneinfo import ZoneInfo

IST = ZoneInfo("Asia/Kolkata")
BASE_SECONDS = 15 * 60
PROFILE_EXPIRY_MARGIN_SECONDS = 120
# An owner-chosen conservative end of the NSE regular trading day.
CLOSE_HOUR = 15
CLOSE_MINUTE = 30
MAX_DAY_SESSION_SECONDS = 8 * 60 * 60


def _jwt_exp(jwt):
    """Parse untrusted expiry *only to cap* a locally allowed session."""
    if not isinstance(jwt, str) or len(jwt) > 8192:
        return None
    parts = jwt.split(".")
    if len(parts) != 3 or len(parts[1]) > 4096:
        return None
    try:
        raw = base64.urlsafe_b64decode(parts[1] + "=" * (-len(parts[1]) % 4))
        payload = json.loads(raw)
        exp = payload.get("exp")
        if isinstance(exp, bool) or not isinstance(exp, int):
            return None
        if not (0 < exp < 4_102_444_800):
            return None
        return exp
    except (ValueError, TypeError, UnicodeDecodeError, OverflowError, binascii.Error):
        return None


def bounded_readonly_expiry(login_epoch, jwt, *, day_policy_requested=False):
    """Calculate a best-effort read-only session cap, not an auth guarantee.

    Returns (expiry_epoch, scope). Same-session actions do not require
    another PIN/TOTP until local expiry or broker rejection, but no claim of
    continuous connectivity, auto-relogin, or live trading is made.
    """
    if isinstance(login_epoch, bool) or not isinstance(login_epoch, (int, float)):
        raise ValueError("INVALID_SESSION_CLOCK")
    moment = datetime.fromtimestamp(login_epoch, timezone.utc).astimezone(IST)
    normal = login_epoch + BASE_SECONDS
    if day_policy_requested is not True:
        return normal, "SHORT_READONLY"
    last = moment.replace(hour=CLOSE_HOUR, minute=CLOSE_MINUTE, second=0, microsecond=0)
    if moment.weekday() >= 5 or moment >= last:
        return normal, "SHORT_READONLY"
    exp = _jwt_exp(jwt)
    if exp is None:
        # Cannot validate token's claimed expiry: do not extend session.
        return normal, "SHORT_READONLY"
    proposed = min(
        last.timestamp(),
        login_epoch + MAX_DAY_SESSION_SECONDS,
        exp - PROFILE_EXPIRY_MARGIN_SECONDS,
    )
    if proposed <= normal:
        return min(normal, max(login_epoch, proposed)), "SHORT_READONLY"
    return proposed, "TRADING_DAY_READONLY"


def is_day_scope_allowed(environment):
    """Extra opt-in only for a *separately secured AWS private gateway*.

    Do not enable for public Render staging. Code flags alone are not network
    identity verification, and must not be interpreted as order permissions.
    """
    return (environment.get("OPTIONX_ANGEL_READONLY_DAY_SESSION") == "1"
            and environment.get("OPTIONX_AWS_OWNER_HTTPS_GATEWAY_VERIFIED") == "1"
            and bool(environment.get("OPTIONX_OWNER_USER_ID", "").strip())
            and environment.get("OPTIONX_REAL_ORDERS_ENABLED", "0") == "0"
            and environment.get("OPTIONX_LIVE_ORDERS_ENABLED", "0") == "0")
