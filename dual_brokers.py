"""Two-broker, credential-free research adapters for OPTIONX V5.

Angel One SmartAPI is reserved for NIFTY/BANKNIFTY derivatives; Delta Exchange
India is reserved for BTC derivatives. We never call authenticated/order routes.
All external URLs are fixed by source code and all user inputs are allowlisted.
Real-money order execution is absent, including on failed authorization.
"""
from __future__ import annotations

import json
import math
import re
import threading
import time
from urllib.parse import quote, urlencode
from urllib.request import Request, urlopen

DELTA_ORIGIN = 'https://api.india.delta.exchange'
DELTA_RESOLUTIONS = {'1m': 60, '5m': 300, '15m': 900, '30m': 1800, '1h': 3600, '4h': 14400, '1d': 86400}
DELTA_TYPES = {
    'future': 'perpetual_futures,futures',
    'option': 'call_options,put_options',
}
BROKER_PROFILES = [
    {
        'id': 'Angel', 'name': 'Angel One SmartAPI',
        'markets': ['NIFTY', 'BANKNIFTY'], 'derivatives': ['CE', 'PE', 'FUT'],
        'docs': 'https://smartapi.angelone.in/docs',
        'approval': 'SmartAPI account, registered static IPv4, exchange/broker algo compliance, verified NFO token/lot size',
        'connection': 'NOT_CONNECTED', 'credentialsAccepted': False,
    },
    {
        'id': 'Delta', 'name': 'Delta Exchange India',
        'markets': ['BTC'], 'derivatives': ['PERPETUAL', 'FUT', 'CALL', 'PUT'],
        'docs': 'https://docs.delta.exchange/',
        'approval': 'Delta India account, appropriately scoped key, API IP whitelist, margin and reconciliation checks',
        'connection': 'NOT_CONNECTED', 'credentialsAccepted': False,
    },
]
_CACHE: dict[str, tuple[float, dict]] = {}
_LOCK = threading.Lock()


def catalog() -> dict:
    return {
        'mode': 'READ_ONLY_BROKER_DISCOVERY',
        'brokers': BROKER_PROFILES,
        'liveOrdersEnabled': False,
        'brokerCredentialsStored': False,
        'notes': 'These are public market-data / setup adapters, NOT connected broker accounts. No order routes exist.',
    }


def _fetch_delta(path: str, *, fetch=None) -> dict:
    # Path is ALWAYS built from the fixed API host + validated args in this module.
    url = DELTA_ORIGIN + path
    if not path.startswith('/v2/') or not url.startswith(DELTA_ORIGIN + '/v2/'):
        raise ValueError('Unsupported Delta endpoint')
    request = Request(url, headers={
        'Accept': 'application/json', 'User-Agent': 'OptionXResearch-V5/1.0',
    }, method='GET')
    handler = fetch or urlopen
    with handler(request, timeout=9) as response:
        if getattr(response, 'status', 200) != 200:
            raise ValueError('Delta provider returned non-success HTTP status')
        content = response.read(1_600_001)
    if len(content) > 1_600_000:
        raise ValueError('Delta provider response exceeded safe size')
    body = json.loads(content)
    if not isinstance(body, dict) or body.get('success') is not True:
        raise ValueError('Delta provider unavailable or request rejected')
    return body


def _symbol(value: str) -> str:
    if not isinstance(value, str) or not 5 <= len(value) <= 48:
        raise ValueError('Enter a valid BTC derivative contract symbol')
    value = value.upper().strip()
    if not re.fullmatch(r'[A-Z0-9-]{5,48}', value) or 'BTC' not in value:
        raise ValueError('Only BTC derivative symbols are supported')
    return value


def _sanitize_product(raw: dict) -> dict:
    if not isinstance(raw, dict):
        raise ValueError('Provider product has invalid structure')
    ticker = str(raw.get('symbol') or '').upper()
    if not ticker or 'BTC' not in ticker:
        raise ValueError('Product is not a BTC contract')
    result = {
        'id': raw.get('id') if isinstance(raw.get('id'), int) else None,
        'symbol': ticker[:48],
        'contractType': str(raw.get('contract_type') or '')[:48],
        'state': str(raw.get('state') or '')[:30],
        'tradingStatus': str(raw.get('trading_status') or '')[:40],
        'tickSize': str(raw.get('tick_size') or '')[:35],
        'contractValue': str(raw.get('contract_value') or '')[:35],
        'contractCurrency': str(raw.get('contract_unit_currency') or '')[:16],
        'settlementTime': str(raw.get('settlement_time') or '')[:35] or None,
        'description': str(raw.get('description') or '')[:160],
    }
    if result['id'] is None or result['id'] <= 0:
        raise ValueError('Invalid Delta product ID')
    result['currentlyTradable'] = result['state'] == 'live' and result['tradingStatus'] == 'operational'
    return result


def delta_product(symbol: str, *, fetch=None) -> dict:
    symbol = _symbol(symbol)
    key = f'product:{symbol}'
    with _LOCK:
        old = _CACHE.get(key)
        if old and time.time()-old[0] < 30:
            return dict(old[1])
    data = _fetch_delta('/v2/products/' + quote(symbol, safe=''), fetch=fetch)
    result = _sanitize_product(data.get('result'))
    if result['symbol'] != symbol:
        raise ValueError('Delta returned a different symbol')
    with _LOCK: _CACHE[key] = (time.time(), result)
    return dict(result)


def delta_products(kind: str, *, fetch=None) -> dict:
    if kind not in DELTA_TYPES:
        raise ValueError('Contract type must be future or option')
    key = f'products:{kind}'
    with _LOCK:
        old = _CACHE.get(key)
        if old and time.time()-old[0] < 60:
            return dict(old[1])
    q = urlencode({'contract_types': DELTA_TYPES[kind], 'states': 'live', 'page_size': '100'})
    data = _fetch_delta('/v2/products?' + q, fetch=fetch)
    candidates = data.get('result')
    if not isinstance(candidates, list):
        raise ValueError('Invalid Delta product listing')
    cleaned = []
    for item in candidates:
        try:
            p = _sanitize_product(item)
            if p['state'] == 'live' and p['contractType'] in (('perpetual_futures','futures') if kind=='future' else ('call_options','put_options')):
                cleaned.append(p)
        except ValueError:
            continue
    # The public products list is paginated: do not imply this is exhaustive.
    answer = {'broker': 'Delta', 'market': 'BTC', 'kind': kind,
              'products': cleaned[:30], 'returned': len(cleaned[:30]),
              'firstPageOnly': True, 'disclaimer': 'First provider page only. Verify expiry and quotes before paper research. No orders sent.',
              'fetchedAt': int(time.time() * 1000)}
    with _LOCK: _CACHE[key] = (time.time(), answer)
    return dict(answer)


def delta_candles(symbol: str, timeframe: str, *, fetch=None, now=None) -> dict:
    symbol = _symbol(symbol)
    if timeframe not in DELTA_RESOLUTIONS:
        raise ValueError('Unsupported timeframe')
    # Avoid open-ended API pulls; <= 720 bars and provider's max is 2000.
    epoch = int(time.time() if now is None else now)
    secs = DELTA_RESOLUTIONS[timeframe]
    end = epoch - epoch % secs
    start = end - 700 * secs
    key = f'candles:{symbol}:{timeframe}:{end}'
    with _LOCK:
        old = _CACHE.get(key)
        if old and time.time()-old[0] < 40: return dict(old[1])
    params = urlencode({'resolution': timeframe, 'symbol': symbol, 'start': start, 'end': end})
    data = _fetch_delta('/v2/history/candles?' + params, fetch=fetch)
    items = data.get('result')
    if not isinstance(items, list): raise ValueError('Invalid Delta candle response')
    rows = []
    for item in items:
        if not isinstance(item, dict): continue
        try:
            t = int(item['time']); t = t if t < 10**12 else t // 1000
            o, h, l, c = [float(item[k]) for k in ('open', 'high', 'low', 'close')]
            vol = float(item.get('volume', 0) or 0)
            if not all(math.isfinite(v) for v in (o,h,l,c,vol)):
                continue
            if min(o,h,l,c) <= 0 or h < max(o,c) or l > min(o,c):
                continue
            # Only completed candles, no future or currently forming bar.
            if t < start or t + secs > end: continue
            rows.append({'time': t*1000, 'open':o,'high':h,'low':l,'close':c,'volume':max(0,vol)})
        except (TypeError, ValueError, KeyError, OverflowError):
            continue
    bars = sorted({x['time']: x for x in rows}.values(), key=lambda x:x['time'])[-700:]
    if len(bars)<25: raise ValueError('Delta returned insufficient completed candles')
    result = {'market':'BTC','symbol':symbol,'timeframe':timeframe,
              'provider':'Delta Exchange India derivative OHLC (public API)',
              'notice':'BTC derivative research data, not authenticated account quotes, fills, positions or guaranteed execution P&L.',
              'feedType':'delta-derivatives','historyLimited':True,
              'bars':bars,'fetchedAt':epoch*1000}
    with _LOCK:_CACHE[key]=(time.time(), result)
    return dict(result)
