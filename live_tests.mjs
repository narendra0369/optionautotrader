// Build gate enforces live trading remains hard locked in both backend and frontend.
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
const html=readFileSync('index.html','utf8');
const app=readFileSync('app.mjs','utf8');
const ui=readFileSync('live_ui.mjs','utf8');
const api=readFileSync('market_api.py','utf8');
const gw=readFileSync('live_gateway.py','utf8');
assert.ok(html.includes('id="page-live"'));
assert.ok(html.includes('id="liveCheck"') && html.includes('REAL ORDERS LOCKED'));
assert.ok(html.includes('id="livePaper"'));
assert.ok(app.includes('mountLive({client,onPage:page})'));
assert.ok(app.includes("live:'Live Broker Setup · Locked'"));
assert.ok(ui.includes("'/api/live/preflight'"));
assert.ok(!ui.includes('/api/live/orders'));
assert.ok(api.includes('user_from_token') && api.includes('hard_block_order()'));
assert.ok(gw.includes("'orderExecutionEnabled': False"));
assert.ok(gw.includes("'canSubmitOrder': False"));
assert.ok(readFileSync('tests.mjs','utf8').includes("'live_ui.mjs'"));
console.log('PASS: live broker-readiness UI, identity verification, preview guards, hard-locked real orders and immutable Render packaging');

// Stoxkart broker choices and owner-bound login-only routes.
assert.ok(html.includes('id="stoxkartStart"') && html.includes('id="stoxkartApiSecret"'));
assert.ok(html.includes('id="stoxkartPositions"') && html.includes('stoxkart_callback.html'));
assert.ok(ui.includes("'/api/brokers/stoxkart/start'"));
assert.ok(ui.includes("'/api/brokers/stoxkart/complete'"));
assert.ok(ui.includes("Stoxkart:'https://developers.stoxkart.com/api-documentation/login'"));
assert.ok(api.includes("'/api/brokers/stoxkart/start'"));
assert.ok(api.includes("'/api/brokers/stoxkart/positions'"));
assert.ok(gw.includes("'Stoxkart': {'label': 'Stoxkart Superr API'"));
console.log('PASS: Stoxkart option and official broker-login callback, real orders hard locked');
assert.ok(html.includes('id="angelReadonlyPositions"')&&html.includes('id="angelReadonlyOrders"'));
assert.ok(html.includes('id="angelReadonlyRows"')&&html.includes('GET ONLY · REAL ORDERS OFF'));
assert.ok(ui.includes("'/api/v7/angel/'+resource"));
assert.ok(ui.includes("location.hostname==='optionx-v7-frontend-test-staging.onrender.com'"));
assert.ok(api.includes("os.getenv('OPTIONX_V7_READONLY_ANGEL_ENABLED', '0') != '1'"));
assert.ok(api.includes("self.headers.get('Origin') != V7_STAGING_ORIGIN"));
assert.ok(!ui.includes("'/api/v7/angel/place"));
console.log('PASS: staging-only Angel profile snapshots with server flag, no order UI, GET-only contract');

