"""OptionX read-only market candle adapter. No trading, tokens or account data.

Kraken Spot OHLC provides BTC/USD; Yahoo chart is an *unofficial, potentially
 delayed* index research feed, with intraday history limits. Provider failures
 are surfaced explicitly; candles are never fabricated.
"""
from __future__ import annotations

import json
import os
import threading
import time
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, quote, urlsplit, urlencode
from urllib.request import Request, urlopen
from zoneinfo import ZoneInfo
from live_gateway import capabilities, status as live_status, user_from_token, preflight, hard_block_order
from dual_brokers import catalog as broker_catalog, delta_product, delta_products, delta_candles
from angel_gateway import status as angel_status, connect as angel_connect, disconnect as angel_disconnect, AuthError
from live_v7.readiness import status as v7_dev_readiness

MARKETS = {'NIFTY': '^NSEI', 'BANKNIFTY': '^NSEBANK', 'BTC': 'XBTUSD'}
TIMEFRAMES = {'1m': 60, '5m': 300, '15m': 900, '30m': 1800, '1h': 3600, '4h': 14400, '1d': 86400}
KRAKEN_INTERVALS = {'1m': 1, '5m': 5, '15m': 15, '30m': 30, '1h': 60, '4h': 240, '1d': 1440}
YAHOO_INTERVALS = {'1m': ('1m', '5d'), '5m': ('5m', '1mo'), '15m': ('15m', '1mo'), '30m': ('30m', '1mo'), '1h': ('60m', '3mo'), '4h': ('60m', '3mo'), '1d': ('1d', '1y')}
ALLOWED_ORIGIN = 'https://optionx-200k-strategy-lab.onrender.com'
_CACHE: dict[tuple[str, str], tuple[float, dict]] = {}
_CACHE_LOCK = threading.Lock()


def _fetch_json(url: str) -> dict:
    req = Request(url, headers={'User-Agent': 'Mozilla/5.0 (compatible; OptionXResearch/2.0)', 'Accept': 'application/json'})
    with urlopen(req, timeout=11) as response:
        if response.status != 200:
            raise ValueError(f'Feed returned HTTP {response.status}')
        raw = response.read(2_500_001)
        if len(raw) > 2_500_000:
            raise ValueError('Provider response too large')
        return json.loads(raw)


def _valid(t, o, h, l, c, v=0):
    vals = (o, h, l, c)
    if any(a is None for a in vals): return None
    try:
        t = int(t); o, h, l, c = map(float, vals); v = float(v or 0)
        if o <= 0 or c <= 0 or l <= 0 or h < max(o, c) or l > min(o, c): return None
        return {'time': t * 1000, 'open': o, 'high': h, 'low': l, 'close': c, 'volume': v}
    except (TypeError, ValueError, OverflowError): return None


def _aggregate_4h(bars):
    """Aggregate to local IST wall-clock 4h buckets; never average price."""
    aggregated = []
    for b in bars:
        local = datetime.fromtimestamp(b['time']/1000, ZoneInfo('Asia/Kolkata'))
        bucket = local.replace(hour=(local.hour//4)*4, minute=0, second=0, microsecond=0)
        group = int(bucket.timestamp()) * 1000
        if aggregated and aggregated[-1]['time'] == group:
            last = aggregated[-1]
            last['high'] = max(last['high'], b['high']); last['low'] = min(last['low'], b['low'])
            last['close'] = b['close']; last['volume'] += b['volume']
        else: aggregated.append({'time': group, 'open': b['open'], 'high': b['high'], 'low': b['low'], 'close': b['close'], 'volume': b['volume']})
    return aggregated


def get_candles(market: str, timeframe: str) -> dict:
    if market not in MARKETS or timeframe not in TIMEFRAMES: raise ValueError('Unsupported market or timeframe')
    key = (market, timeframe)
    with _CACHE_LOCK:
        cached = _CACHE.get(key)
        if cached and time.time() - cached[0] < 40:
            return {**cached[1], 'cacheAgeSeconds': round(time.time()-cached[0], 1)}
    if market == 'BTC':
        url = 'https://api.kraken.com/0/public/OHLC?' + urlencode({'pair': MARKETS[market], 'interval': KRAKEN_INTERVALS[timeframe]})
        payload = _fetch_json(url)
        if payload.get('error'): raise ValueError('Kraken: ' + ', '.join(payload['error']))
        root = payload.get('result') or {}
        pair = next((k for k in root if k != 'last'), None)
        if not pair: raise ValueError('Kraken did not return candles')
        bars = [_valid(row[0], row[1], row[2], row[3], row[4], row[6]) for row in root[pair]]
        provider, symbol, notice = 'Kraken Spot Public API', 'BTC/USD', 'Exchange spot feed, polled every 45s; not a futures contract or execution quote.'
    else:
        interval, period = YAHOO_INTERVALS[timeframe]
        symbol = MARKETS[market]
        path = quote(symbol, safe='')
        params = urlencode({'interval': interval, 'range': period, 'includePrePost': 'false'})
        last_error = None
        for host in ('query1.finance.yahoo.com', 'query2.finance.yahoo.com'):
            try:
                payload = _fetch_json(f'https://{host}/v8/finance/chart/{path}?{params}')
                if payload.get('chart', {}).get('error'):
                    raise ValueError(str(payload['chart']['error'].get('description') or 'Provider response error'))
                res = (payload.get('chart', {}).get('result') or [None])[0]
                if not res: raise ValueError('Yahoo returned no chart result')
                q = res['indicators']['quote'][0]
                bars = [_valid(ts, q['open'][i], q['high'][i], q['low'][i], q['close'][i], (q.get('volume') or [0]*len(res['timestamp']))[i]) for i, ts in enumerate(res['timestamp'])]
                last_error = None
                break
            except Exception as e: last_error = e
        if last_error: raise ValueError('Yahoo index feed unavailable: ' + str(last_error)[:180])
        if timeframe == '4h': bars = _aggregate_4h([x for x in bars if x])
        provider, symbol = 'Yahoo Finance chart (unofficial)', ('NIFTY 50 index' if market == 'NIFTY' else 'NIFTY BANK index')
        notice = 'Indicative / potentially delayed index OHLC, NOT exchange-authorized real-time ticks or option contract candles. Provider may impose limits.'
    bars = sorted({b['time']: b for b in bars if b}.values(), key=lambda x: x['time'])[-1200:]
    if len(bars) < 25: raise ValueError('Feed has insufficient valid candles')
    result = {'market': market, 'symbol': symbol, 'timeframe': timeframe, 'provider': provider, 'notice': notice, 'bars': bars, 'fetchedAt': int(time.time()*1000), 'feedType': 'spot' if market == 'BTC' else 'indicative-index', 'historyLimited': True}
    with _CACHE_LOCK: _CACHE[key] = (time.time(), result)
    return result


class Handler(BaseHTTPRequestHandler):
    def _json(self, status: int, body: dict):
        encoded = json.dumps(body, separators=(',', ':'), allow_nan=False).encode('utf-8')
        self.send_response(status)
        origin = self.headers.get('Origin', '')
        if origin == ALLOWED_ORIGIN or origin.startswith('http://localhost:') or origin.startswith('http://127.0.0.1:'):
            self.send_header('Access-Control-Allow-Origin', origin)
            self.send_header('Vary', 'Origin')
        self.send_header('Content-Type', 'application/json; charset=utf-8')
        self.send_header('Cache-Control', 'no-store')
        self.send_header('X-Content-Type-Options', 'nosniff')
        self.send_header('Content-Length', str(len(encoded)))
        self.end_headers()
        self.wfile.write(encoded)

    def do_OPTIONS(self):
        self.send_response(204)
        origin = self.headers.get('Origin', '')
        if origin == ALLOWED_ORIGIN or origin.startswith('http://localhost:') or origin.startswith('http://127.0.0.1:'):
            self.send_header('Access-Control-Allow-Origin', origin)
            self.send_header('Access-Control-Allow-Methods', 'GET, POST, OPTIONS')
            self.send_header('Access-Control-Allow-Headers', 'Content-Type, Authorization')
        self.send_header('Content-Length', '0'); self.end_headers()

    def do_GET(self):
        path = urlsplit(self.path)
        if path.path == '/health': return self._json(200, {'status': 'ok', 'service': 'optionx-public-market-feed', 'paperOnly': True, 'liveOrdersEnabled': False})
        if path.path == '/api/v7/readiness':
            user = user_from_token(self.headers.get('Authorization'))
            if not user:
                return self._json(401, {'error': 'Verified OPTIONX session required'})
            return self._json(200, v7_dev_readiness(angel_status(user)))
        if path.path == '/api/live/capabilities': return self._json(200, capabilities())
        if path.path == '/api/brokers/delta/candles':
            qs = parse_qs(path.query)
            symbol = qs.get('symbol', ['BTCUSD'])[0]
            timeframe = qs.get('timeframe', ['15m'])[0]
            try:
                return self._json(200, delta_candles(symbol, timeframe))
            except ValueError as exc:
                return self._json(400, {'error': str(exc)[:160]})
            except Exception:
                return self._json(503, {'error': 'Delta India candle provider unavailable; original CSV research remains available.'})
        if path.path == '/api/brokers/angel/status':
            user = user_from_token(self.headers.get('Authorization'))
            return self._json(200, angel_status(user)) if user else self._json(401, {'error': 'Sign in required'})
        if path.path.startswith('/api/brokers/'):
            user = user_from_token(self.headers.get('Authorization'))
            if not user: return self._json(401, {'error':'Sign in to OptionX to inspect broker routes'})
            if path.path == '/api/brokers/catalog': return self._json(200, broker_catalog())
            if path.path == '/api/brokers/delta/product':
                qs = parse_qs(path.query)
                try: return self._json(200, delta_product(qs.get('symbol', ['BTCUSD'])[0]))
                except ValueError as exc: return self._json(400, {'error': str(exc)[:160]})
                except Exception: return self._json(503, {'error': 'Delta product feed unavailable'})
            if path.path == '/api/brokers/delta/products':
                qs = parse_qs(path.query)
                try: return self._json(200, delta_products(qs.get('kind', ['future'])[0]))
                except ValueError as exc: return self._json(400, {'error': str(exc)[:160]})
                except Exception: return self._json(503, {'error':'Delta product list currently unavailable'})
            return self._json(404, {'error': 'Unsupported broker discovery route'})
        if path.path == '/api/live/status':
            user = user_from_token(self.headers.get('Authorization'))
            return self._json(200, live_status(user)) if user else self._json(401, {'error': 'Valid signed-in session required'})
        if path.path.startswith('/api/live/'):
            return self._json(423, hard_block_order())
        if path.path != '/api/candles': return self._json(404, {'error': 'Not found'})
        qs = parse_qs(path.query)
        market = qs.get('market', [''])[0].upper()
        timeframe = qs.get('timeframe', ['15m'])[0]
        if market not in MARKETS or timeframe not in TIMEFRAMES: return self._json(400, {'error': 'Choose supported market (NIFTY/BANKNIFTY/BTC) and timeframe (1m/5m/15m/30m/1h/4h/1d).'})
        try: return self._json(200, get_candles(market, timeframe))
        except Exception as exc: return self._json(503, {'error': str(exc)[:220], 'market': market, 'timeframe': timeframe, 'fallback': 'Upload OHLC CSV or open the external chart. No synthetic prices are shown.'})

    def do_POST(self):
        path = urlsplit(self.path).path
        if path in ('/api/brokers/angel/connect', '/api/brokers/angel/disconnect'):
            # CSRF defense: only the published OPTIONX HTTPS origin can send
            # personal broker login secrets to this endpoint.
            origin = self.headers.get('Origin', '')
            local_allowed = (os.getenv('OPTIONX_LOCAL_ANGEL_TEST', '') == '1' and
                             origin in ('http://localhost:8000', 'http://127.0.0.1:8000'))
            if origin != ALLOWED_ORIGIN and not local_allowed:
                return self._json(403, {'error': 'Untrusted website origin'})
            if self.headers.get('Content-Type','').split(';')[0].strip().lower() != 'application/json':
                return self._json(415, {'error': 'JSON required'})
            user = user_from_token(self.headers.get('Authorization'))
            if not user: return self._json(401, {'error': 'Valid OPTIONX login required'})
            try:
                n = int(self.headers.get('Content-Length', '0'))
                if n < 2 or n > 2048: return self._json(413, {'error': 'Invalid request size'})
                data = json.loads(self.rfile.read(n))
                if path.endswith('/connect'):
                    return self._json(200, angel_connect(user, data))
                if data != {}: return self._json(400, {'error': 'Unexpected disconnect payload'})
                return self._json(200, angel_disconnect(user))
            except PermissionError:
                return self._json(403, {'error': 'Angel One connection is limited to the configured personal OPTIONX owner'})
            except AuthError as exc:
                return self._json(400, {'error': str(exc)})
            except (ValueError, TypeError, UnicodeDecodeError, json.JSONDecodeError):
                return self._json(400, {'error': 'Invalid Angel connection request'})
        if path.startswith('/api/brokers/'):
            return self._json(423, hard_block_order())
        if path != '/api/live/preflight':
            # Deliberately no order/margin/cancel POST endpoint. Always fail closed.
            return self._json(423, hard_block_order()) if path.startswith('/api/live/') else self._json(404, {'error': 'Not found'})
        user = user_from_token(self.headers.get('Authorization'))
        if not user:
            return self._json(401, {'error': 'Valid signed-in session required'})
        try:
            n = int(self.headers.get('Content-Length', '0'))
            if n < 2 or n > 8192:
                return self._json(413, {'error': 'Invalid preview request size'})
            body = json.loads(self.rfile.read(n))
            # Note: preview has no writes, broker connection, or order side effects.
            return self._json(200, preflight(body, user))
        except (ValueError, TypeError, UnicodeDecodeError, json.JSONDecodeError) as exc:
            return self._json(400, {'error': str(exc)[:180]})

    def log_message(self, fmt, *args):
        # No request headers, credentials or user identifiers written.
        return


if __name__ == '__main__':
    port = int(os.getenv('PORT', '10000'))
    print(f'OptionX market-feed read-only listening on :{port}', flush=True)
    ThreadingHTTPServer(('0.0.0.0', port), Handler).serve_forever()
