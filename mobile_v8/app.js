// OptionX mobile PWA: public research feed only. No broker tokens, cookies,
// JWT, API keys, PIN/TOTP, AWS account data or any real-order methods.
const PUBLIC_RESEARCH_FEED = 'https://optionx-v7-offline-test-staging.onrender.com';
const FULL_PLATFORM = 'https://optionx-200k-strategy-lab.onrender.com';
const screens = new Map([...document.querySelectorAll('[data-panel]')].map(el => [el.dataset.panel, el]));
const navButtons = [...document.querySelectorAll('[data-nav]')];
const setText = (id, value) => { const el = document.getElementById(id); if (el) el.textContent = value; };
const fields = { market: document.getElementById('marketSelect'),
                 timeframe: document.getElementById('timeframeSelect') };
const TIMEFRAMES = new Set(['1m','5m','15m','30m','1h','4h','1d']);
const MARKETS = new Set(['NIFTY','BANKNIFTY','BTC']);
let fetching = false;
let currentAbort = null;
let isOnline = navigator.onLine;

function navigate(name) {
  if (!screens.has(name)) return;
  for (const [panel, el] of screens) el.hidden = panel !== name;
  for (const button of navButtons) {
    const active = button.dataset.nav === name ||
      (button.dataset.nav === 'more' && ['backtests','access','live'].includes(name));
    button.classList.toggle('active', active);
    button.setAttribute('aria-current', active ? 'page' : 'false');
  }
  if (location.hash !== '#' + name) history.replaceState(null, '', '#' + name);
  if (name === 'markets' && !fetching && isOnline &&
      document.getElementById('lastMarketClose').textContent === '—') {
    refreshMarket();
  }
}
for (const button of navButtons) button.addEventListener('click', () => navigate(button.dataset.nav));
for (const button of document.querySelectorAll('[data-go]')) {
  button.addEventListener('click', () => navigate(button.dataset.go));
}
addEventListener('hashchange', () => navigate(screens.has(location.hash.slice(1)) ? location.hash.slice(1) : 'home'));
navigate(screens.has(location.hash.slice(1)) ? location.hash.slice(1) : 'home');

function networkState(healthy, message) {
  const el = document.getElementById('connectionNotice');
  if (el) {
    el.textContent = message;
    el.dataset.online = healthy ? 'true' : 'false';
  }
  setText('publicFeedState', healthy ? 'Public Feed Online' : 'Offline / Unavailable');
}
async function getJson(path, timeout = 14000) {
  // Fixed host + fixed public paths. No credentials sent or persisted.
  if (!path.startsWith('/health') && !path.startsWith('/api/candles?')) {
    throw new Error('Public feed route not permitted');
  }
  const controller = new AbortController();
  const stop = setTimeout(() => controller.abort(), timeout);
  try {
    const response = await fetch(PUBLIC_RESEARCH_FEED + path, {
      method: 'GET', mode: 'cors', redirect: 'error',
      credentials: 'omit', cache: 'no-store', signal: controller.signal,
      headers: {'Accept':'application/json'}
    });
    if (!response.ok) throw new Error('HTTP ' + response.status);
    const data = await response.json();
    if (!data || typeof data !== 'object') throw new Error('Unexpected public feed response');
    return data;
  } finally { clearTimeout(stop); }
}
async function checkPublicServer() {
  if (!navigator.onLine) {
    networkState(false, 'Phone is offline. Cached app navigation works; current prices do not.');
    return;
  }
  try {
    const data = await getJson('/health', 12000);
    if (data.status !== 'ok' || data.liveOrdersEnabled !== false || data.paperOnly !== true) {
      throw new Error('Unexpected server safety contract');
    }
    networkState(true, 'HTTPS public research server connected. Broker and private AWS session NOT connected; real orders OFF.');
  } catch {
    networkState(false, 'Public research server unavailable or still starting. Full website may still work. No broker session connected.');
  }
}
function clearCandles(message) {
  setText('lastMarketClose', '—');
  setText('marketStatus', message);
  setText('marketSource', 'No verified provider candles.');
  setText('marketStamp', 'No timestamp.');
  const visual = document.getElementById('miniChart');
  if (visual) visual.replaceChildren();
}
function chartBars(bars) {
  // SVG graphics from numeric, shape-checked public OHLC values. Never innerHTML.
  const values = bars.slice(-55).map(row => row.close);
  const min = Math.min(...values), max = Math.max(...values);
  const chart = document.getElementById('miniChart');
  if (!chart || values.length < 2) return;
  const range = max - min || 1;
  const points = values.map((v, i) => {
    const x = 5 + i * (290 / (values.length - 1));
    const y = 92 - ((v - min) / range) * 82;
    return x.toFixed(2) + ',' + y.toFixed(2);
  }).join(' ');
  const svg = document.createElementNS('http://www.w3.org/2000/svg', 'svg');
  svg.setAttribute('viewBox', '0 0 300 105');
  svg.setAttribute('preserveAspectRatio','none');
  svg.setAttribute('role','img');
  svg.setAttribute('aria-label','Indicative closing-price trend, last ' + values.length + ' complete candles');
  const polyline = document.createElementNS('http://www.w3.org/2000/svg', 'polyline');
  polyline.setAttribute('points', points);
  polyline.setAttribute('fill', 'none');
  polyline.setAttribute('stroke', '#d8bd86');
  polyline.setAttribute('stroke-linejoin','round');
  polyline.setAttribute('stroke-width','2.2');
  svg.append(polyline);
  chart.replaceChildren(svg);
}
async function refreshMarket() {
  if (fetching) return;
  const market = fields.market?.value, timeframe = fields.timeframe?.value;
  if (!MARKETS.has(market) || !TIMEFRAMES.has(timeframe)) {
    clearCandles('Choose a supported market and timeframe.');
    return;
  }
  if (!navigator.onLine) {
    clearCandles('Offline: cannot fetch fresh candles. No made-up prices.');
    return;
  }
  fetching = true;
  const button = document.getElementById('refreshMarket');
  if (button) button.disabled = true;
  clearCandles('Loading latest published historical OHLC candles…');
  try {
    const data = await getJson('/api/candles?market=' + encodeURIComponent(market) +
                             '&timeframe=' + encodeURIComponent(timeframe), 19000);
    if (data.market !== market || data.timeframe !== timeframe || !Array.isArray(data.bars)) {
      throw new Error('Feed contract mismatch');
    }
    const bars = data.bars.filter(b => b && Number.isFinite(b.time) &&
      Number.isFinite(b.open) && Number.isFinite(b.high) &&
      Number.isFinite(b.low) && Number.isFinite(b.close) &&
      b.open > 0 && b.close > 0 && b.low > 0 &&
      b.high >= Math.max(b.open,b.close) && b.low <= Math.min(b.open,b.close));
    if (bars.length < 25) throw new Error('Insufficient valid provider candles');
    const last = bars.at(-1);
    const prefix = market === 'BTC' ? '$' : '₹';
    setText('lastMarketClose', prefix + last.close.toLocaleString('en-IN', {maximumFractionDigits:2}));
    setText('marketStatus', 'Public provider returned ' + bars.length + ' OHLC candles (not execution-grade).');
    setText('marketSource', (data.provider || 'Unknown provider') + ' · ' + (data.notice || 'Indicative only'));
    setText('marketStamp', 'Last OHLC candle: ' + new Date(last.time).toLocaleString('en-IN', {
      timeZone:'Asia/Kolkata',hour12:true}) + ' IST · fetched ' +
      new Date(data.fetchedAt || Date.now()).toLocaleTimeString('en-IN', {
        timeZone:'Asia/Kolkata'}) + ' IST');
    chartBars(bars);
    networkState(true, 'HTTPS public research feed responding. Broker and private AWS account NOT connected; real orders OFF.');
  } catch {
    clearCandles('Public market data temporarily unavailable. Try later or open full charts. No substitute prices shown.');
  } finally {
    fetching = false;
    if (button) button.disabled = false;
  }
}
document.getElementById('refreshMarket')?.addEventListener('click', refreshMarket);
fields.market?.addEventListener('change', () => clearCandles('Market changed; tap Load Server Candles.'));
fields.timeframe?.addEventListener('change', () => clearCandles('Timeframe changed; tap Load Server Candles.'));
addEventListener('online', () => { isOnline = true; checkPublicServer(); });
addEventListener('offline', () => { isOnline = false; networkState(false, 'Phone offline; live market data unavailable. Cached app shell only.'); });
document.addEventListener('visibilitychange', () => {
  if (!document.hidden && navigator.onLine) checkPublicServer();
});
setInterval(() => {
  if (!document.hidden && navigator.onLine && !fetching &&
      screens.get('markets')?.hidden === false) refreshMarket();
}, 60_000);

// Android PWA install: no USB/debugging required.
let pending = null;
const installButtons = [...document.querySelectorAll('#install,#installApp')];
function setInstallButtons(label, disabled) {
  for (const button of installButtons) {
    button.textContent = label;
    button.disabled = disabled;
  }
}
addEventListener('beforeinstallprompt', event => {
  event.preventDefault(); pending = event;
  setInstallButtons('Install OptionX on Android', false);
});
for (const button of installButtons) {
  button.addEventListener('click', async () => {
    if (!pending) return;
    pending.prompt(); await pending.userChoice;
    pending = null; setInstallButtons('Use Chrome menu to install', true);
  });
}
addEventListener('appinstalled', () => { pending = null; setInstallButtons('OptionX installed', true); });
if ('serviceWorker' in navigator) {
  addEventListener('load', () => navigator.serviceWorker.register('/service-worker.js').catch(() => {}));
}
checkPublicServer();

// Private auth / order APIs are deliberately not called from this public PWA.
// Existing full working research website remains available at FULL_PLATFORM.
void FULL_PLATFORM;