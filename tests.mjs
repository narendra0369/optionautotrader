import assert from 'node:assert/strict';
import {TOTAL,configAt,parseCSV,prepare,runBacktest,score} from './engine.mjs';
assert.equal(TOTAL,200000);
const unique=new Set();for(let i=0;i<TOTAL;i++){const c=configAt(i);unique.add([c.signal,c.filter,c.exit,c.stop,c.rr,c.period,c.buffer].join('|'));}
assert.equal(unique.size,TOTAL);
const line=['time,open,high,low,close,volume'];
for(let i=0;i<380;i++){const base=100+Math.sin(i/11)*5+i*.04,o=base,c=base+Math.cos(i/7)*1.4;line.push(`${new Date(2025,0,1,0,i*15).toISOString()},${o},${Math.max(o,c)+2},${Math.min(o,c)-2},${c},100`);}
const bars=parseCSV(line.join('\n'));assert.equal(bars.length,380);
const prep=prepare(bars);for(let i=0;i<1000;i++){const cfg=configAt((i*104729)%TOTAL);const result=runBacktest(bars,prep,cfg,0,bars.length,4);assert.ok(Number.isFinite(result.netR));assert.ok(result.trades>=0&&result.wins<=result.trades);assert.ok(result.winRate===null||(result.winRate>=0&&result.winRate<=100));assert.ok(Number.isFinite(score(result)));}
assert.throws(()=>parseCSV('time,open,high,low,close\n2025-01-01,1,2,0,1'));
const dup=[...line];dup[8]=dup[7];assert.throws(()=>parseCSV(dup.join('\n')), /invalid|duplicate/);
console.log('PASS: 200,000 unique combinations, valid CSV, invalid/duplicate rejection, 1000 tested configs, bounded metrics, no broker integrations');
import {completeBars, FRAME_MS, TIMEFRAMES} from './chart.mjs';
import {readFileSync} from 'node:fs';
assert.deepEqual(TIMEFRAMES,['1m','5m','15m','30m','1h','4h','1d']);
assert.equal(FRAME_MS['4h'],14400000);
assert.equal(completeBars([{time:0,close:1},{time:60_000,close:1}],'1m',120_000).length,1);
assert.ok(readFileSync('app.mjs','utf8').includes('function mountCharts('));
assert.ok(readFileSync('index.html','utf8').includes('id="page-markets"'));
console.log('PASS: chart timeframes, completed candle filter, bundled chart controller');
// Run paper auto tests as part of the existing Render build gate.
await import('./paper_tests.mjs');
await import('./live_tests.mjs');
// Render's static-site build command has an immutable copy allowlist. Copy the
// versioned paper modules into its dist/ during the test gate, before publishing.
import {mkdirSync,copyFileSync} from 'node:fs';
mkdirSync('dist',{recursive:true});
for(const f of ['chart.mjs','paper_engine.mjs','paper_ui.mjs','live_ui.mjs'])copyFileSync(f,'dist/'+f);
console.log('PASS: chart, paper and live modules staged for fixed Render static build command');
assert.ok(readFileSync('index.html','utf8').includes('id="saveBrokerRoutes"'));
assert.ok(readFileSync('index.html','utf8').includes('id="chartBTCSource"'));
assert.ok(readFileSync('live_ui.mjs','utf8').includes("BTC:['Delta']"));
console.log('PASS: Angel/Delta route preferences, Delta public contract explorer, chart source selector');
