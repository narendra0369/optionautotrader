/* OptionX V7 safe PWA shell. All trading & authenticated requests need network.
 * Cache ONLY an inert offline screen and two public decorative icon files.
 * Never intercept/cache broker OAuth callback, credentials, Supabase sessions,
 * API calls, market data, order previews or strategy backtest results.
 */
const CACHE = 'optionx-v7-offline-shell-20261124-v1';
const SHELL = ['/offline.html','/icons/optionx-192.png','/icons/optionx-512.png'];

self.addEventListener('install', event => {
  event.waitUntil(caches.open(CACHE).then(c=>c.addAll(SHELL)).then(()=>self.skipWaiting()));
});
self.addEventListener('activate', event => {
  event.waitUntil(
    caches.keys().then(keys=>Promise.all(keys.filter(key=>key!==CACHE&&key.startsWith('optionx-v7-offline-shell-')).map(key=>caches.delete(key))))
     .then(()=>self.clients.claim())
  );
});
self.addEventListener('fetch', event => {
  if(event.request.method !== 'GET' || event.request.mode !== 'navigate') return;
  const target = new URL(event.request.url);
  if(target.origin !== self.location.origin) return;
  // Let the browser own the sensitive one-use Stoxkart redirect.
  if(target.pathname === '/stoxkart_callback.html') return;
  event.respondWith(fetch(event.request).catch(()=>caches.match('/offline.html')));
});
