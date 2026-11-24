// OptionX V7 Android PWA / broker install safety build gate (Node offline).
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {runInNewContext} from 'node:vm';

const html=readFileSync('index.html','utf8');
const manifest=JSON.parse(readFileSync('manifest.webmanifest','utf8'));
const sw=readFileSync('sw.js','utf8');
const install=readFileSync('mobile-install.mjs','utf8');
const offline=readFileSync('offline.html','utf8');
const flutter=readFileSync('mobile_flutter/lib/optionx_v7_broker_hub.dart','utf8');
const callback=readFileSync('stoxkart_callback.html','utf8');

assert.equal(manifest.name.startsWith('OptionX'),true);
assert.equal(manifest.display,'standalone');
assert.equal(manifest.theme_color,'#080d17');
assert.equal(manifest.start_url,'/#dashboard');
assert.equal(manifest.scope,'/');
assert.ok(manifest.shortcuts.find(x=>x.url==='/#paper'));
assert.ok(manifest.shortcuts.find(x=>x.url==='/#live'));
assert.equal(manifest.icons.length,2);
for(const n of [192,512]){
  const path='icons/optionx-'+n+'.png';
  const icon=readFileSync(path);
  assert.deepEqual([...icon.subarray(0,8)],[137,80,78,71,13,10,26,10]);
  assert.equal(icon.readUInt32BE(16),n);
  assert.equal(icon.readUInt32BE(20),n);
  assert.ok(manifest.icons.some(x=>x.src===path&&x.sizes===n+'x'+n));
  assert.deepEqual(readFileSync('dist/'+path),icon);
}
assert.ok(html.includes('rel="manifest"'));
assert.ok(html.includes('id="installOptionX"'));
assert.ok(html.includes('src="/mobile-install.mjs"'));
assert.ok(install.includes('beforeinstallprompt'));
assert.ok(install.includes("navigator.serviceWorker.register('/sw.js'"));
assert.ok(sw.includes("'/stoxkart_callback.html'"));
assert.ok(offline.includes('REAL MONEY ORDERS: OFF'));
assert.ok(offline.includes('Paper Auto does'));
assert.ok(callback.includes("sessionStorage.setItem('optionx_stoxkart_callback_token'"));
assert.ok(flutter.includes("LaunchMode.externalApplication"));
assert.ok(flutter.includes("OptionXV7BrokerHub"));
assert.ok(flutter.includes('REAL MONEY AUTO TRADING: OFF'));
assert.ok(!flutter.includes('package:webview_flutter'));
assert.ok(!flutter.includes('placeOrder('));

// Execute only service-worker event registration & routing with fake browser
// objects, proving that it NEVER handles broker OAuth callback or API GET.
const handlers={};
const self={
 location:{origin:'https://optionx-v7-frontend-test-staging.onrender.com'},
 addEventListener(name, fn){handlers[name]=fn;},
 clients:{claim:async()=>{}},skipWaiting:async()=>{},
};
runInNewContext(sw,{self,URL,Promise,
  fetch:async()=>({status:200}),
  caches:{open:async()=>({addAll:async()=>{}}),keys:async()=>[],
          delete:async()=>{},match:async()=>({status:200})}
});
function isIntercepted(method,mode,path,origin=self.location.origin){
  let yes=false;
  handlers.fetch({request:{method,mode,url:origin+path},
    respondWith(){yes=true;}});
  return yes;
}
assert.equal(isIntercepted('GET','navigate','/stoxkart_callback.html'),false);
assert.equal(isIntercepted('GET','cors','/api/brokers/stoxkart/positions'),false);
assert.equal(isIntercepted('GET','cors','/auth/v1/user'),false);
assert.equal(isIntercepted('POST','navigate','/api/live/place-order'),false);
assert.equal(isIntercepted('GET','navigate','/dashboard','https://evil.example'),false);
assert.equal(isIntercepted('GET','navigate','/'),true);

for(const path of ['manifest.webmanifest','sw.js','offline.html',
                  'mobile-install.mjs','icons/optionx-192.png',
                  'icons/optionx-512.png']){
  assert.ok(readFileSync('dist/'+path).length>16,'PWA dist asset missing: '+path);
}
console.log('PASS: installable Android PWA, 192/512 PNG, OAuth no-cache, offline lock, Flutter update patch (static inspection only)');
