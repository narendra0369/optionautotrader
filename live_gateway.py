"""Fail-closed broker integration preparation. NO broker network calls or order writes.

This service intentionally cannot place, modify or cancel real orders. The live
broker rollout needs an owner-bound credential vault, static IP / exchange approval,
contract master, live broker quotes, lifecycle and recovery tests before enabling.
"""
from __future__ import annotations

import math
import os
import urllib.error
import urllib.request
import json
from datetime import datetime, timezone
from angel_gateway import status as angel_status

SUPABASE_URL = 'https://yghijfzwsvmzaffllszl.supabase.co'
# Public (publishable) key only; service role is NEVER required or used.
SUPABASE_PUBLIC_KEY = 'sb_publishable_4MUEQ2Nj1siLELHYIlEJ6g_7L4QVEsr'
BROKERS = {
    'Zerodha': {'label': 'Zerodha Kite Connect', 'docs': 'https://kite.trade/docs/connect/v3/', 'markets': ['NIFTY', 'BANKNIFTY']},
    'Angel': {'label': 'Angel One SmartAPI', 'docs': 'https://smartapi.angelone.in/docs', 'markets': ['NIFTY', 'BANKNIFTY']},
    'Stoxkart': {'label': 'Stoxkart Superr API', 'docs': 'https://developers.stoxkart.com/api-documentation/login', 'markets': ['NIFTY', 'BANKNIFTY']},
    'Dhan': {'label': 'DhanHQ v2', 'docs': 'https://dhanhq.co/docs/v2/authentication/', 'markets': ['NIFTY', 'BANKNIFTY']},
    'Delta': {'label': 'Delta Exchange India API', 'docs': 'https://docs.delta.exchange/', 'markets': ['BTC']},
}
REQUIRED_CHECKS = [
    ('ORDER_GATE', 'Real-order gateway is disabled in code'),
    ('BROKER_AUTH', 'Broker OAuth/session is not linked to this user'),
    ('STATIC_IP', 'Broker-registered static outbound IP is not verified'),
    ('ACCOUNT_MAPPING', 'Personal broker account ownership is not verified'),
    ('CONTRACT_MASTER', 'Exchange contract token, expiry, lot size and tick size are not verified'),
    ('EXECUTION_PRICE', 'Broker execution price feed and quote freshness are not verified'),
    ('BROKER_RECONCILIATION', 'Reject/partial-fill/retry/duplicate/cancel/position reconciliation is untested'),
    ('RISK_AND_MARGIN', 'Broker margin, daily loss guard and exchange compliance are not verified'),
]

def capabilities():
    return {'orderExecutionEnabled': False, 'mode': 'READINESS_ONLY',
            'brokers': [{'id': k, **v, 'connected': False} for k, v in BROKERS.items()],
            'supportedMarkets': ['NIFTY', 'BANKNIFTY', 'BTC'],
            'sourceWarning': 'Public index OHLC / BTC spot research feeds are NOT execution-grade derivatives quotes.',
            'details': 'Static-IP/approved algo prerequisites, real broker sessions and end-to-end lifecycle tests are pending.'}


def user_from_token(header: str | None, *, fetch=None):
    """Verify access token with Supabase Auth; never trust decoded JWT claims alone."""
    if not isinstance(header, str) or not header.startswith('Bearer '):
        return None
    token = header[7:].strip()
    if len(token) < 20 or len(token) > 8192 or any(x.isspace() for x in token):
        return None
    req = urllib.request.Request(SUPABASE_URL + '/auth/v1/user', headers={
        'Authorization': 'Bearer ' + token,
        'apikey': SUPABASE_PUBLIC_KEY,
        'Accept': 'application/json',
        'User-Agent': 'OptionX-Gateway/1.0',
    })
    try:
        resp = fetch(req, timeout=7) if fetch else urllib.request.urlopen(req, timeout=7)
        with resp as r:
            if getattr(r, 'status', 200) != 200:
                return None
            data = json.loads(r.read(16_384))
        uid = data.get('id') if isinstance(data, dict) else None
        # Supabase auth UUID must be 36 characters; never return emails/tokens.
        return uid if isinstance(uid, str) and len(uid) == 36 else None
    except (ValueError, KeyError, TypeError, urllib.error.URLError, OSError, TimeoutError):
        return None


def status(user_id: str) -> dict:
    allowed_owner = os.getenv('OPTIONX_OWNER_USER_ID', '').strip()
    return {'mode': 'READINESS_ONLY', 'identityVerified': bool(user_id),
            'ownerBindingConfigured': bool(allowed_owner),
            'ownerMatch': bool(allowed_owner and user_id == allowed_owner),
            'brokerConnected': angel_status(user_id)['connected'], 'liveExecutionEnabled': False,
            'realOrderCount': 0,
            'nextStep': 'Angel profile verification can be attempted by the configured owner. This never enables real orders. Verify static-IP requirements separately.'}


def _number(data, field, low, high, integer=False):
    x = data.get(field)
    if isinstance(x, bool) or not isinstance(x, (int, float)) or not math.isfinite(x):
        raise ValueError(field + ' must be a finite number')
    if not low <= x <= high or (integer and int(x) != x):
        raise ValueError(field + ' outside allowed preview range')
    return int(x) if integer else float(x)


def preflight(data: dict, user_id: str) -> dict:
    if not user_id:
        raise ValueError('Authenticated user required')
    if not isinstance(data, dict):
        raise ValueError('Expected JSON object')
    market, broker = data.get('market'), data.get('broker')
    if broker not in BROKERS or market not in ('NIFTY', 'BANKNIFTY', 'BTC'):
        raise ValueError('Unsupported broker/market')
    if market not in BROKERS[broker]['markets']:
        raise ValueError('Broker is not mapped for this market')
    if data.get('side') not in ('BUY', 'SELL'):
        raise ValueError('BUY or SELL required')
    if data.get('orderType') != 'LIMIT':
        raise ValueError('Only LIMIT order previews are supported; MARKET orders not supported')
    # These are only user-entered estimates; do not represent exchange-verified risk.
    quantity = _number(data, 'quantity', 1, 100_000, integer=True)
    price = _number(data, 'limitPrice', 0.01, 100_000_000)
    risk = _number(data, 'riskBudget', 1, 100_000)
    daily = _number(data, 'dailyStop', 1, 200_000)
    max_trades = _number(data, 'maxTrades', 1, 5, integer=True)
    if daily < risk:
        raise ValueError('Daily stop must be at least one per-trade risk budget')
    strategy_id = _number(data, 'strategyId', 1, 200_000, integer=True)
    symbol = data.get('contractSymbol', '')
    if not isinstance(symbol, str) or len(symbol) > 72 or any(ord(c) < 32 for c in symbol):
        raise ValueError('Invalid contract label')
    symbol = symbol.strip().upper()
    if not symbol or symbol in ('NIFTY', 'BANKNIFTY', 'BTC', '^NSEI', '^NSEBANK', 'XBTUSD'):
        contract_check = ('MISSING_CONTRACT', 'Index/spot proxy cannot be traded as a derivative contract')
    else:
        contract_check = ('CONTRACT_UNVERIFIED', 'Typed contract is NOT verified against broker instrument master')
    checks = [{'code': key, 'pass': False, 'detail': message} for key, message in REQUIRED_CHECKS]
    checks.append({'code': contract_check[0], 'pass': False, 'detail': contract_check[1]})
    return {'mode': 'PREVIEW_ONLY', 'canSubmitOrder': False, 'liveExecutionEnabled': False,
            'broker': broker, 'market': market, 'strategyId': strategy_id,
            'preview': {'side': data['side'], 'orderType': 'LIMIT', 'contractLabel': symbol,
                        'quantity': quantity, 'limitPrice': price,
                        'estimatedNotional': round(quantity * price, 2), 'riskBudget': risk,
                        'dailyStop': daily, 'maxTrades': max_trades,
                        'warning': 'Estimate only: no verified broker quote, margin, expiry, option greeks or fill simulation.'},
            'checks': checks, 'blockedCount': len(checks),
            'timestamp': datetime.now(timezone.utc).isoformat()}


def hard_block_order():
    return {'error': 'REAL_ORDERS_HARD_LOCKED', 'orderSent': False,
            'detail': 'No broker order placement, modification or cancellation implementation exists in this deployment.'}
