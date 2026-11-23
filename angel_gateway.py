"""OptionX Angel One: owner-bound, temporary, read-only SmartAPI login verification.

Sensitive input arrives only via authenticated HTTPS POST, is used once, and is
never returned, logged, persisted or uploaded to Supabase. The short-lived JWT
stays in one Python process's RAM only. NO order methods or routes exist.
"""
from __future__ import annotations

import ipaddress
import json
import os
import re
import socket
import threading
import time
import urllib.error
import urllib.request
import uuid
from datetime import datetime, timezone

API = 'https://apiconnect.angelone.in'
LOGIN = '/rest/auth/angelbroking/user/v1/loginByPassword'
PROFILE = '/rest/secure/angelbroking/user/v1/getProfile'
MAX_SESSION_SECONDS = 15 * 60
MAX_ATTEMPTS = 3
ATTEMPT_WINDOW = 15 * 60
LOCK = threading.Lock()
_SESSIONS: dict[str, dict] = {}
_ATTEMPTS: dict[str, list[float]] = {}

class AuthError(Exception):
    """Public-safe error with no source credentials or broker server payload."""
    pass

class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise AuthError('Broker redirected unexpectedly; connection not accepted')


def _post_or_get(method: str, endpoint: str, key: str, token: str = '', payload=None, *, fetch=None) -> dict:
    if (method, endpoint) not in (('POST', LOGIN), ('GET', PROFILE)):
        raise AuthError('Unsupported read-only Angel endpoint')
    if not key or not isinstance(key, str):
        raise AuthError('Angel API key is required')
    headers = {
        'Accept': 'application/json',
        'Content-Type': 'application/json',
        'X-PrivateKey': key,
        'X-UserType': 'USER',
        'X-SourceID': 'WEB',
        'User-Agent': 'OptionX-ReadOnly/6.0',
        'X-ClientLocalIP': '127.0.0.1',
        'X-MACAddress': ':'.join(f'{(uuid.getnode() >> shift) & 255:02x}' for shift in (40, 32, 24, 16, 8, 0)),
    }
    # Never invent or misrepresent a static outgoing IP. The broker may reject
    # the request without this optional header. REAL orders remain blocked.
    outbound = os.getenv('ANGEL_EGRESS_PUBLIC_IPV4', '').strip()
    if outbound:
        try:
            ip = ipaddress.ip_address(outbound)
            if ip.version == 4 and not ip.is_private and not ip.is_loopback and not ip.is_multicast:
                headers['X-ClientPublicIP'] = str(ip)
        except ValueError:
            raise AuthError('Configured Angel IP is invalid')
    elif fetch is None:
        # Match the SDK's observed-public-IP login header best-effort. This
        # never establishes static IP ownership/whitelisting for API orders.
        try:
            ip_req = urllib.request.Request('https://api.ipify.org', headers={'User-Agent': 'OptionX-ReadOnly/6.0'})
            with urllib.request.urlopen(ip_req, timeout=3) as reply:
                seen_ip = reply.read(64).decode('ascii').strip()
            public_ip = ipaddress.ip_address(seen_ip)
            if public_ip.version == 4 and public_ip.is_global:
                headers['X-ClientPublicIP'] = str(public_ip)
        except (urllib.error.URLError, TimeoutError, OSError, ValueError, UnicodeDecodeError):
            pass  # upstream may reject login; never fake a verified IP
    if token:
        headers['Authorization'] = 'Bearer ' + token
    data = json.dumps(payload, separators=(',', ':')).encode() if payload is not None else None
    req = urllib.request.Request(API + endpoint, data=data, headers=headers, method=method)
    try:
        if fetch:
            response = fetch(req, timeout=10)
        else:
            response = urllib.request.build_opener(NoRedirect()).open(req, timeout=10)
        with response as r:
            if getattr(r, 'status', 200) != 200:
                raise AuthError('Angel One rejected the connection request')
            raw = r.read(32_769)
            if len(raw) > 32_768:
                raise AuthError('Angel response too large')
        result = json.loads(raw)
    except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError, OSError, ValueError, UnicodeDecodeError):
        raise AuthError('Angel One login/profile unavailable or rejected; check API app and credentials') from None
    if not isinstance(result, dict) or result.get('status') is not True or not isinstance(result.get('data'), dict):
        raise AuthError('Angel One rejected the credentials or the session expired')
    return result['data']


def _owner_bound(user_id: str) -> bool:
    expected = os.getenv('OPTIONX_OWNER_USER_ID', '').strip()
    return bool(user_id and expected and user_id == expected)


def _mask_client(client: str) -> str:
    return ('•' * max(2, len(client) - 2)) + client[-2:]


def _clean_session(user_id: str, now: float) -> dict | None:
    with LOCK:
        session = _SESSIONS.get(user_id)
        if session and now >= session['expires']:
            _SESSIONS.pop(user_id, None)
            session = None
        return session.copy() if session else None


def status(user_id: str, *, now=None) -> dict:
    current = time.time() if now is None else now
    configured = bool(os.getenv('OPTIONX_OWNER_USER_ID', '').strip())
    allowed = _owner_bound(user_id)
    session = _clean_session(user_id, current) if allowed else None
    return {
        'provider': 'Angel One SmartAPI',
        'ownerConfigured': configured,
        'ownerMatch': allowed,
        'connected': bool(session),
        'verifiedAt': session['verifiedAt'] if session else None,
        'expiresAt': datetime.fromtimestamp(session['expires'], timezone.utc).isoformat() if session else None,
        'maskedClientCode': session['maskedClientCode'] if session else None,
        'orderExecutionEnabled': False,
        'sessionStorage': 'SERVER_RAM_ONLY',
        'notice': 'Temporary broker profile verification only. NO real order methods; static-IP execution approval not verified.'
    }


def connect(user_id: str, body: dict, *, fetch=None, now=None) -> dict:
    current = time.time() if now is None else now
    if not _owner_bound(user_id):
        raise PermissionError('This OptionX account is not bound as the private broker owner')
    if not isinstance(body, dict) or set(body) != {'apiKey', 'clientCode', 'pin', 'totp'}:
        raise AuthError('Expected Angel API key, client code, PIN and 6-digit TOTP')
    api_key, client, pin, totp = (body.get(name) for name in ('apiKey', 'clientCode', 'pin', 'totp'))
    if not isinstance(api_key, str) or not re.fullmatch(r'[A-Za-z0-9_-]{8,128}', api_key):
        raise AuthError('Angel SmartAPI key format invalid')
    if not isinstance(client, str) or not re.fullmatch(r'[A-Za-z0-9]{4,24}', client):
        raise AuthError('Angel Client Code format invalid')
    if not isinstance(pin, str) or not (4 <= len(pin) <= 128) or any(ord(ch) < 33 or ord(ch) > 126 for ch in pin):
        raise AuthError('Angel PIN/password format invalid')
    if not isinstance(totp, str) or not re.fullmatch(r'\d{6}', totp):
        raise AuthError('Enter a fresh six-digit Angel TOTP code')
    expected_client = os.getenv('ANGEL_ALLOWED_CLIENT_CODE', '').strip().upper()
    if expected_client and expected_client != client.upper():
        raise PermissionError('This SmartAPI client code is not the approved personal account')
    with LOCK:
        attempts = [t for t in _ATTEMPTS.get(user_id, []) if current - t < ATTEMPT_WINDOW]
        if len(attempts) >= MAX_ATTEMPTS:
            raise AuthError('Too many login attempts. Try after 15 minutes')
        attempts.append(current)
        _ATTEMPTS[user_id] = attempts
    data = _post_or_get('POST', LOGIN, api_key, payload={'clientcode': client, 'password': pin, 'totp': totp}, fetch=fetch)
    jwt = data.get('jwtToken')
    if not isinstance(jwt, str) or len(jwt) < 20:
        raise AuthError('Angel One did not issue a usable session token')
    # Profile endpoint is a read-only remote verification of the supplied login.
    profile = _post_or_get('GET', PROFILE, api_key, token=jwt, fetch=fetch)
    result_client = profile.get('clientcode')
    if not isinstance(result_client, str) or result_client.upper() != client.upper():
        raise AuthError('Broker profile does not match the intended Angel account')
    verified = datetime.fromtimestamp(current, timezone.utc).isoformat()
    with LOCK:
        _SESSIONS[user_id] = {
            'jwt': jwt, 'apiKey': api_key, 'client': result_client,
            'verifiedAt': verified, 'maskedClientCode': _mask_client(result_client),
            'expires': current + MAX_SESSION_SECONDS,
        }
    return status(user_id, now=current)


def disconnect(user_id: str) -> dict:
    if not _owner_bound(user_id):
        raise PermissionError('Only the bound owner can disconnect the personal broker session')
    with LOCK:
        _SESSIONS.pop(user_id, None)
    return {'connected': False, 'orderExecutionEnabled': False,
            'notice': 'In-memory OptionX broker session cleared. This does not log you out of the Angel One app.'}
