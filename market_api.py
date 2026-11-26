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
from live_v7.owner_live_unlock_v46 import live_unlock_status as v46_live_unlock_status
from live_v7.owner_activation_coordinator_v50 import inspect_owner_activation
from live_v7.render_aws_relay_v48 import forward_owner_control, RelayBlocked
from live_v7.egress_diagnostic import check_egress
from live_v7.angel_greeks import angel_selected_contract_greeks
from live_v7.angel_auto_atm import angel_auto_atm_readonly
from live_v7.read_only_bridge import angel_owner_snapshot, ReadOnlyBridgeError
from live_v7.angel_marketdata import list_contracts as angel_list_contracts, quote_ltp as angel_quote_ltp, historical_15m as angel_candles_15m, MarketDataError
from live_v7.stoxkart_gateway import (status as stoxkart_status, start as stoxkart_start, complete as stoxkart_complete, disconnect as stoxkart_disconnect, positions as stoxkart_positions, StoxkartAuthError)

MARKETS = {'NIFTY': '^NSEI', 'BANKNIFTY': '^NSEBANK', 'BTC': 'XBTUSD'}
TIMEFRAMES = {'1m': 60, '5m': 300, '15m': 900, '30m': 1800, '1h': 3600, '4h': 14400, '1d': 86400}
KRAKEN_INTERVALS = {'1m': 1, '5m': 5, '15m': 15, '30m': 30, '1h': 60, '4h': 240, '1d': 1440}
YAHOO_INTERVALS = {'1m': ('1m', '5d'), '5m': ('5m', '1mo'), '15m': ('15m', '1mo'), '30m': ('30m', '1mo'), '1h': ('60m', '3mo'), '4h': ('60m', '3mo'), '1d': ('1d', '1y')}
ALLOWED_ORIGIN = 'https://optionx-200k-strategy-lab.onrender.com'
V7_STAGING_ORIGIN = 'https://optionx-v7-frontend-test-staging.onrender.com'
V8_MOBILE_PUBLIC_ORIGIN = 'https://optionx-v8-mobile-paper-staging.onrender.com'


def _permitted_origin(origin: str, request_path: str = '') -> bool:
    """Do not allow staging browser access to the production backend.

    V7 backend staging can opt in explicitly; env setting defaults to OFF
    and has no real-order implication.
    """
    # The public Android PWA may read only public market resources.
    # Never grant this origin any private account, token, or broker routes.
    if origin == V8_MOBILE_PUBLIC_ORIGIN:
        return request_path in ('/health', '/api/candles')
    if origin == ALLOWED_ORIGIN:
        return True
    if origin == V7_STAGING_ORIGIN:
        # Public candle/health resources are safe for the V7 Paper UI.
        # Broker/account routes still require an independent owner-bound gate.
        if request_path in ('/health', '/api/candles', '/api/v7/owner/egress'):
            return True
        return os.getenv('OPTIONX_V7_STAGING_CORS', '0') == '1'
    if origin.startswith('http://localhost:') or origin.startswith('http://127.0.0.1:'):
        host, sep, port = origin.rpartition(':')
        return bool(sep and port.isdigit() and 0 < int(port) < 65536)
    return False

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
        if _permitted_origin(origin, urlsplit(self.path).path):
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
        if _permitted_origin(origin, urlsplit(self.path).path):
            self.send_header('Access-Control-Allow-Origin', origin)
            self.send_header('Access-Control-Allow-Methods', 'GET, POST, OPTIONS')
            self.send_header('Access-Control-Allow-Headers', 'Content-Type, Authorization')
        self.send_header('Content-Length', '0'); self.end_headers()

    def do_GET(self):
        path = urlsplit(self.path)
        if path.path == '/health': return self._json(200, {'status': 'ok', 'service': 'optionx-public-market-feed', 'paperOnly': True, 'liveOrdersEnabled': False})
        if path.path == '/api/v7/owner/egress':
            # The backend process itself measures outbound IPv4. Strict browser
            # origin + verified Supabase owner; never trust client-supplied IPs.
            if self.headers.get('Origin') != V7_STAGING_ORIGIN:
                return self._json(403, {'error': 'PRIVATE_STAGING_OWNER_ONLY', 'canSubmitOrder': False})
            user = user_from_token(self.headers.get('Authorization'))
            if not user or angel_status(user).get('ownerMatch') is not True:
                return self._json(403, {'error': 'VERIFIED_OWNER_REQUIRED', 'canSubmitOrder': False})
            if os.getenv('OPTIONX_V7_EGRESS_DIAGNOSTIC_ENABLED', '0') != '1':
                return self._json(423, {'error': 'EGRESS_DIAGNOSTIC_DISABLED', 'canSubmitOrder': False})
            return self._json(200, check_egress(
                registered_ipv4=os.getenv('OPTIONX_ANGEL_REGISTERED_IPV4', '').strip()))
        if path.path == '/api/v50/owner/activation-eligibility':
            # Read-only. This Render process CANNOT certify the AWS broker
            # worker and never trusts browser-submitted proof flags.
            user = user_from_token(self.headers.get('Authorization'))
            if not user or angel_status(user).get('ownerMatch') is not True:
                return self._json(403, {'error':'OWNER_ONLY',
                                        'liveOrdersEnabled':False})
            return self._json(200, inspect_owner_activation(
                owner_authenticated=True))
        if path.path == '/api/v46/owner/live-unlock-status':
            # Trusted Supabase session AND server-side owner binding required.
            # This endpoint is GET/READ-ONLY, with no broker order or gate write.
            user = user_from_token(self.headers.get('Authorization'))
            if not user:
                return self._json(401, {'error':'AUTHENTICATED_OWNER_REQUIRED',
                                        'liveOrdersEnabled':False})
            broker_state = angel_status(user)
            if broker_state.get('ownerMatch') is not True:
                return self._json(403, {'error':'OWNER_ONLY',
                                        'liveOrdersEnabled':False})
            return self._json(200, v46_live_unlock_status(
                owner_match=True,
                verified_session=broker_state.get('connected') is True))
        if path.path == '/api/v7/readiness':
            user = user_from_token(self.headers.get('Authorization'))
            if not user:
                return self._json(401, {'error': 'Verified OPTIONX session required'})
            return self._json(200, v7_dev_readiness(angel_status(user), stoxkart_status(user)))
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
        if path.path == '/api/v7/angel/auto-atm':
            # No PIN/API key or account data from public users. Auto ATM only
            # on separately authenticated, feature-flagged V7 staging.
            if (self.headers.get('Origin')!=V7_STAGING_ORIGIN
                or os.getenv('OPTIONX_V7_STAGING_CORS','0')!='1'):
                return self._json(403,{'error':'PRIVATE_OWNER_STAGING_REQUIRED',
                                        'canSubmitOrder':False})
            user=user_from_token(self.headers.get('Authorization'))
            if not user:
                return self._json(401,{'error':'Verified OptionX owner required'})
            if (os.getenv('OPTIONX_V7_AUTO_ATM_READONLY_ENABLED','0')!='1'
                or os.getenv('OPTIONX_V7_MARKETDATA_ANGEL_ENABLED','0')!='1'
                or os.getenv('OPTIONX_V7_GREEKS_ANGEL_ENABLED','0')!='1'):
                return self._json(423,{'error':'AUTO_ATM_READONLY_NOT_APPROVED',
                                        'canSubmitOrder':False,'liveOrdersEnabled':False,
                                        'fillETASeconds':None})
            params=parse_qs(path.query,keep_blank_values=True)
            if (set(params)!={'market','strategy'} or
                any(len(v)!=1 for v in params.values())):
                return self._json(400,{'error':'Expect exactly one market and strategy'})
            try:
                return self._json(200,angel_auto_atm_readonly(
                  user,params['market'][0],params['strategy'][0]))
            except MarketDataError as exc:
                return self._json(
                  429 if exc.code=='AUTO_ATM_READ_RATE_LIMIT' else
                  400 if exc.code=='UNSUPPORTED_AUTO_ATM_REQUEST' else 503,
                  {'error':'Trusted broker automatic ATM preview unavailable',
                   'diagnosticCode':exc.code,'canSubmitOrder':False,
                   'liveOrdersEnabled':False,'fillETASeconds':None})

        if path.path in ('/api/v7/angel/contracts', '/api/v7/angel/ltp', '/api/v7/angel/candles', '/api/v7/angel/greeks'):
            # Owner-bound, fixed-source NFO market-data reads only. LTP uses the
            # broker's read-only POST endpoint server-side; no order APIs exist.
            if (self.headers.get('Origin') != V7_STAGING_ORIGIN
                    or os.getenv('OPTIONX_V7_STAGING_CORS', '0') != '1'):
                return self._json(403, {'error':'Market-data pilot is V7 staging only',
                                        'liveExecutionEnabled':False,'canSubmitOrder':False})
            user = user_from_token(self.headers.get('Authorization'))
            if not user:
                return self._json(401, {'error':'Verified OPTIONX owner session required'})
            if os.getenv('OPTIONX_V7_MARKETDATA_ANGEL_ENABLED', '0') != '1':
                return self._json(423, {'error':'Angel market-data pilot is disabled',
                                        'liveExecutionEnabled':False,'canSubmitOrder':False})
            if path.path.endswith('/greeks') and os.getenv('OPTIONX_V7_GREEKS_ANGEL_ENABLED','0')!='1':
                return self._json(423, {'error':'V7_OWNER_ANGEL_GREEKS_READ_DISABLED',
                                        'canSubmitOrder':False,'liveExecutionEnabled':False})
            params=parse_qs(path.query,keep_blank_values=True)
            allowed = ({'market','side','strike'} if path.path.endswith('/contracts') else
                       {'token','days'} if path.path.endswith('/candles') else {'token'})
            if any(k not in allowed or len(v)!=1 for k,v in params.items()):
                return self._json(400, {'error':'Unsupported market-data query parameters'})
            try:
                if path.path.endswith('/contracts'):
                    return self._json(200, angel_list_contracts(
                        user, params.get('market',[''])[0],params.get('side',[''])[0],
                        strike=params.get('strike',[None])[0]))
                if path.path.endswith('/candles'):
                    days=params.get('days',['3'])[0]
                    if days not in ('1','2','3','5','7'):
                        return self._json(400, {'error':'Historical contract window must be 1,2,3,5 or 7 days'})
                    return self._json(200, angel_candles_15m(
                        user, params.get('token',[''])[0], days=int(days)))
                if path.path.endswith('/greeks'):
                    return self._json(200, angel_selected_contract_greeks(
                        user, params.get('token',[''])[0]))
                return self._json(200, angel_quote_ltp(user,params.get('token',[''])[0]))
            except MarketDataError as exc:
                status = (429 if exc.code in ('QUOTE_POLL_RATE_LIMIT','CANDLE_POLL_RATE_LIMIT','GREEKS_POLL_RATE_LIMIT') else
                          400 if exc.code in ('INVALID_CONTRACT_FILTER','INVALID_INSTRUMENT_TOKEN',
                                              'INVALID_INSTRUMENT_NUMBER') else
                          401 if exc.code=='ANGEL_SESSION_EXPIRED' else 503)
                return self._json(status, {'error':'Angel NFO market-data read unavailable',
                                           'diagnosticCode':exc.code,
                                           'liveExecutionEnabled':False,
                                           'orderExecutionEnabled':False,'canSubmitOrder':False})
        if path.path in ('/api/v7/angel/orderbook', '/api/v7/angel/tradebook', '/api/v7/angel/positions'):
            # Private broker reads ONLY from the separate V7 staging UI.
            # A valid OPTIONX JWT alone does not grant another website account access.
            if (self.headers.get('Origin') != V7_STAGING_ORIGIN
                    or os.getenv('OPTIONX_V7_STAGING_CORS', '0') != '1'):
                return self._json(403, {'error': 'Angel account inspection is staging-owner-only',
                                        'liveExecutionEnabled': False, 'canSubmitOrder': False})
            user = user_from_token(self.headers.get('Authorization'))
            if not user:
                return self._json(401, {'error': 'Verified OPTIONX session required'})
            # Read-only inspection is disabled until independently approved,
            # reviewed, and tested. Never derive this from browser payloads.
            if os.getenv('OPTIONX_V7_READONLY_ANGEL_ENABLED', '0') != '1':
                return self._json(423, {'error': 'V7_READONLY_ACCOUNT_INSPECTION_DISABLED',
                                        'liveExecutionEnabled': False})
            resource = ('orderbook' if path.path.endswith('/orderbook') else
                        'tradebook' if path.path.endswith('/tradebook') else 'positions')
            try:
                return self._json(200, angel_owner_snapshot(
                    verified_optionx_user_id=user, resource=resource,
                    server_feature_flag_enabled=True))
            except ReadOnlyBridgeError as exc:
                return self._json(503, {'error': 'Owner-bound read-only broker snapshot unavailable',
                                        'diagnosticCode': exc.diagnostic_code,
                                        'canSubmitOrder': False,
                                        'liveExecutionEnabled': False})
        if path.path in ('/api/brokers/stoxkart/status', '/api/brokers/stoxkart/positions'):
            if self.headers.get('Origin') != V7_STAGING_ORIGIN or os.getenv('OPTIONX_V7_STAGING_CORS','0') != '1':
                return self._json(403, {'error':'Stoxkart profile inspection is available on V7 staging only'})
            user = user_from_token(self.headers.get('Authorization'))
            if not user: return self._json(401, {'error':'Verified OptionX owner session required'})
            try:
                if path.path.endswith('/status'):
                    return self._json(200, stoxkart_status(user))
                return self._json(200, stoxkart_positions(user))
            except PermissionError:
                return self._json(403, {'error':'Broker access is limited to the configured OptionX owner'})
            except StoxkartAuthError:
                return self._json(503, {'error':'Stoxkart read-only session missing or positions unavailable; no orders sent'})
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
        if path == '/api/v48/owner/request-unlock-review':
            # Owner-bound, CSRF-guarded server-to-server signed command.
            # Never accepts arbitrary order params or browser supplied HMAC.
            if (self.headers.get('Origin') != V7_STAGING_ORIGIN
                or os.getenv('OPTIONX_V7_STAGING_CORS','0') != '1'):
                return self._json(403, {'error':'OWNER_STAGING_ORIGIN_REQUIRED',
                                        'liveOrdersEnabled':False})
            if self.headers.get('Content-Type','').split(';')[0].strip().lower() != 'application/json':
                return self._json(415, {'error':'JSON_REQUIRED','liveOrdersEnabled':False})
            user = user_from_token(self.headers.get('Authorization'))
            if not user or angel_status(user).get('ownerMatch') is not True:
                return self._json(403, {'error':'VERIFIED_OWNER_REQUIRED',
                                        'liveOrdersEnabled':False})
            if os.getenv('OPTIONX_V48_CONTROL_RELAY_ENABLED','0') != '1':
                return self._json(423, {'error':'AWS_CONTROL_CHANNEL_NOT_DEPLOYED',
                                        'liveOrdersEnabled':False})
            try:
                n = int(self.headers.get('Content-Length','0'))
                if n != 2 or json.loads(self.rfile.read(n)) != {}:
                    return self._json(400, {'error':'EMPTY_JSON_REQUIRED',
                                            'liveOrdersEnabled':False})
                response=forward_owner_control(
                    verified_owner_id=user,
                    expected_owner_id=os.getenv('OPTIONX_OWNER_USER_ID',''),
                    action='REQUEST_UNLOCK_REVIEW',
                    signing_key=os.getenv('OPTIONX_V48_CONTROL_HMAC_KEY','').encode('utf-8'),
                    aws_endpoint=os.getenv('OPTIONX_V48_AWS_HTTPS_URL',''))
                return self._json(200,response)
            except (RelayBlocked,ValueError,TypeError):
                return self._json(503, {'error':'AWS_OWNER_CONTROL_NOT_CONFIRMED',
                                        'liveOrdersEnabled':False})
        if path in ('/api/brokers/stoxkart/start', '/api/brokers/stoxkart/complete', '/api/brokers/stoxkart/disconnect'):
            # Stoxkart credentials are accepted ONLY from the dedicated staging
            # frontend, using an authenticated OptionX owner session.
            if self.headers.get('Origin') != V7_STAGING_ORIGIN or os.getenv('OPTIONX_V7_STAGING_CORS','0') != '1':
                return self._json(403, {'error':'Stoxkart login allowed on trusted V7 staging origin only'})
            if self.headers.get('Content-Type','').split(';')[0].strip().lower() != 'application/json':
                return self._json(415, {'error':'JSON required'})
            user = user_from_token(self.headers.get('Authorization'))
            if not user: return self._json(401, {'error':'Verified OptionX session required'})
            try:
                n = int(self.headers.get('Content-Length','0'))
                if n < 2 or n > 2048: return self._json(413, {'error':'Invalid request size'})
                body = json.loads(self.rfile.read(n))
                if path.endswith('/start'):
                    return self._json(200, stoxkart_start(user, body))
                if path.endswith('/complete'):
                    return self._json(200, stoxkart_complete(user, body))
                if body != {}: return self._json(400, {'error':'Invalid session-clear request'})
                return self._json(200, stoxkart_disconnect(user))
            except PermissionError:
                return self._json(403, {'error':'Stoxkart limited to configured private OptionX owner'})
            except StoxkartAuthError as exc:
                return self._json(400, {'error':str(exc)})
            except (ValueError, TypeError, UnicodeDecodeError, json.JSONDecodeError):
                return self._json(400, {'error':'Malformed Stoxkart login request'})
        if path in ('/api/brokers/angel/connect', '/api/brokers/angel/disconnect'):
            # CSRF defense: only the published OPTIONX HTTPS origin can send
            # personal broker login secrets to this endpoint.
            origin = self.headers.get('Origin', '')
            local_allowed = (os.getenv('OPTIONX_LOCAL_ANGEL_TEST', '') == '1' and
                             origin in ('http://localhost:8000', 'http://127.0.0.1:8000'))
            staging_allowed = (origin == V7_STAGING_ORIGIN
                               and os.getenv('OPTIONX_V7_STAGING_CORS', '0') == '1')
            if origin != ALLOWED_ORIGIN and not staging_allowed and not local_allowed:
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
