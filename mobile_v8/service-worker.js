const CACHE='optionx-v8-public-shell-1';
const allowed=new Set(['/','/index.html','/styles.css','/app.js','/manifest.webmanifest','/icons/icon-192.png','/icons/icon-512.png']);
self.addEventListener('install',event=>event.waitUntil(caches.open(CACHE).then(cache=>cache.addAll([...allowed])).then(()=>self.skipWaiting())));
self.addEventListener('activate',event=>event.waitUntil(caches.keys().then(keys=>Promise.all(keys.filter(k=>k!==CACHE).map(k=>caches.delete(k)))).then(()=>self.clients.claim())));
self.addEventListener('fetch',event=>{
  const req=event.request,pathname=new URL(req.url).pathname;
  if(req.method!=='GET'||new URL(req.url).origin!==self.location.origin||!allowed.has(pathname))return;
  event.respondWith(fetch(req,{cache:'no-store'}).then(response=>{
    if(response.ok&&response.type==='basic'){
      const copy=response.clone();caches.open(CACHE).then(cache=>cache.put(req,copy)).catch(()=>{});
    }return response;
  }).catch(()=>caches.match(req).then(match=>match||Response.error())));
});