"""Owner-bound Render egress IP diagnostic. Does NOT enable broker orders.

Two independent HTTPS IP echo services report the CURRENT observed IPv4.
A matching observation is NOT proof of static egress, broker registration, or
regulatory approval. Free Render egress can rotate across shared IP ranges.
No user tokens, broker credentials, browser-supplied IPs or trade requests are
sent to these third-party providers.
"""
from __future__ import annotations

import ipaddress
import ssl
import urllib.error
import urllib.request
from typing import Callable

SOURCES = ("https://api.ipify.org", "https://ipv4.icanhazip.com")


def _public_ipv4(raw: object) -> str | None:
    if not isinstance(raw, str):
        return None
    try:
        value = ipaddress.ip_address(raw.strip())
    except ValueError:
        return None
    return str(value) if value.version == 4 and value.is_global else None


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def _read_ip(url: str) -> str | None:
    if url not in SOURCES:
        return None
    try:
        req = urllib.request.Request(url, headers={
            "Accept": "text/plain",
            "User-Agent": "OptionX-Egress-Diagnostic/1.0",
        }, method="GET")
        opener = urllib.request.build_opener(
            urllib.request.HTTPSHandler(context=ssl.create_default_context()),
            _NoRedirect(),
        )
        with opener.open(req, timeout=5) as response:
            if getattr(response, "status", 200) != 200:
                return None
            raw = response.read(65)
        if len(raw) > 64:
            return None
        return _public_ipv4(raw.decode("ascii"))
    except (OSError, TimeoutError, ValueError, UnicodeDecodeError, urllib.error.URLError):
        return None


def check_egress(*, fetch: Callable[[str], str | None] = _read_ip,
                 registered_ipv4: str = "") -> dict:
    """For a previously authenticated OptionX owner only; never public.

    Caller MUST enforce exact staging origin and trusted owner binding.
    registered_ipv4 comes only from securely configured server environment,
    never a client query parameter. It is an assertion, not broker proof.
    """
    observed = [fetch(url) for url in SOURCES]
    safe = [_public_ipv4(x) for x in observed]
    agreement = len(safe) == 2 and all(safe) and safe[0] == safe[1]
    recorded = _public_ipv4(registered_ipv4) if registered_ipv4 else None
    return {
        "diagnostic": "OPTIONX_V7_READONLY_EGRESS",
        "source": "SERVER_OUTBOUND_OBSERVATION",
        "observations": safe,
        "sourcesAgreed": bool(agreement),
        "registeredIpv4Configured": recorded is not None,
        "observedMatchesConfiguredIpv4": bool(agreement and recorded and safe[0] == recorded),
        "dedicatedStaticIpVerified": False,
        "angelBrokerRegistrationVerified": False,
        "angelAlgoExecutionApprovalVerified": False,
        "liveExecutionEnabled": False,
        "canSubmitOrder": False,
        "notice": "An observed matching IPv4 never proves stable routing or Angel approval. Free/shared Render egress is unsuitable for certified live order submission.",
    }
