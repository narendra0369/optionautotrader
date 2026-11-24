import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import {fileURLToPath} from 'node:url';
const dir=path.join(path.dirname(fileURLToPath(import.meta.url)),'dist');
const manifest=JSON.parse(fs.readFileSync(path.join(dir,'manifest.webmanifest'),'utf8'));
const html=fs.readFileSync(path.join(dir,'index.html'),'utf8');
const js=fs.readFileSync(path.join(dir,'app.js'),'utf8');
const sw=fs.readFileSync(path.join(dir,'service-worker.js'),'utf8');
assert.equal(manifest.display,'standalone');
assert.equal(manifest.icons.length,2);
for(const n of [192,512]){
  const buf=fs.readFileSync(path.join(dir,'icons','icon-'+n+'.png'));
  assert.deepEqual([...buf.subarray(0,8)],[137,80,78,71,13,10,26,10]);
  assert.equal(buf.readUInt32BE(16),n);assert.equal(buf.readUInt32BE(20),n);
}
for(const panel of ['home','strategies','backtests','access'])assert.ok(html.includes('data-panel="'+panel+'"'));
assert.ok(html.includes('NOT connected'));
assert.ok(html.includes('NOT live-synced'));
assert.ok(html.includes('id="daily-angel-connect"'));
assert.ok(html.includes('https://optionx-v7-frontend-test-staging.onrender.com/#live'));
assert.ok(html.includes('15-minute in-memory read-only session'));
assert.ok(html.includes('NOT deployed'));
assert.ok(!html.includes('name="pin"'));

assert.ok(html.includes('href="/manifest.webmanifest"'));
assert.ok(!html.includes('sb_secret_')&&!html.includes('jwtToken')&&!html.includes('43.204.246.235'));
assert.ok(!js.includes('localStorage'));
assert.ok(sw.includes("!allowed.has(pathname)"));
console.log('OPTIONX_PUBLIC_PWA_TESTS_PASS: 4 screens, icons, HTTPS install manifest, no account credentials');
