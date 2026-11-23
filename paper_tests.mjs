import assert from 'node:assert/strict';
import {makePaperAccount,assertConfig,armPaper,disarmPaper,stepPaper,emergencyPaperClose,paperMetrics,completed} from './paper_engine.mjs';
import {configAt,TOTAL} from './engine.mjs';
assert.equal(TOTAL,200000);
// Find a deterministic Donchian strategy that is eligible to signal on a breakout.
let strategyId=0;
for(let id=0;id<200000;id++){
 const c=configAt(id);if(c.signal===3&&c.filter===0&&c.exit===0&&c.period===8&&c.stop===1&&c.rr===1&&c.buffer===0){strategyId=c.id;break;}
}
assert(strategyId,'Donchian config is present');
const t0=Date.parse('2026-11-19T00:00:00Z'),m=900_000;
const candle=(i,o=100,h=101,l=99,c=100)=>({time:t0+i*m,open:o,high:h,low:l,close:c,volume:100});
const bars=Array.from({length:131},(_,i)=>candle(i));
const atNow=i=>t0+(i+1)*m+10_000;
let a=makePaperAccount('NIFTY',{strategyId});
assert.equal(a.state.armed,false);
const armed=armPaper(a,bars,atNow(130));assert.equal(armed.state.armed,true);assert.equal(armed.state.trades.length,0);
assert.equal(armed.state.lastBarTime,bars.at(-1).time);
assert.equal(stepPaper(armed,bars,atNow(130)).changed,false);
bars.push(candle(131,100,104,99.6,103));
let ret=stepPaper(armed,bars,atNow(131));assert.equal(ret.changed,true);a=ret.account;
assert.equal(a.state.pending?.dir,1,'signal must occur after bar close');assert.equal(a.state.position,null);
// On the next CLOSED bar, the simulated entry is recorded using THAT candle's opening price.
bars.push(candle(132,104,104.5,103.5,104));ret=stepPaper(a,bars,atNow(132));a=ret.account;
assert.equal(a.state.pending,null);assert(a.state.position);assert.equal(a.state.position.dir,1);assert.equal(a.state.countToday,1);assert.equal(a.state.position.openedAt,bars.at(-1).time);
const sl=a.state.position.stop,tp=a.state.position.target;
// Both SL and TP touched on one bar -> stop-first pessimism.
bars.push(candle(133,104,tp+2,sl-2,104));ret=stepPaper(a,bars,atNow(133));a=ret.account;
assert.equal(a.state.position,null);assert.equal(a.state.trades[0].reason,'STOP');assert(a.state.trades[0].netPnl<0);
assert.equal(paperMetrics(a).closedTrades,1);assert(a.state.realized<0);
const dis=disarmPaper(a);assert.equal(dis.state.armed,false);assert.equal(stepPaper(dis,bars,atNow(133)).changed,false);
assert.throws(()=>makePaperAccount('BTC',{capital:10000,risk:2000}),/safety/i);
assert.throws(()=>makePaperAccount('NIFTY',{maxTrades:8}),/1–5/);
assert.throws(()=>armPaper(makePaperAccount('NIFTY'),bars.slice(0,5),atNow(10)),/120/);
assert.throws(()=>completed([candle(0),candle(0)],'15m',atNow(1)),/unordered/);
// More than two missed bars => fail-closed. No phantom order sequence.
let gap=armPaper(makePaperAccount('BTC',{strategyId}),bars.slice(0,131),atNow(130));
const gapB=[...bars.slice(0,131),candle(131),candle(132),candle(133)];
let stopped=stepPaper(gap,gapB,atNow(133)).account;assert.equal(stopped.state.armed,false);
assert.match(stopped.state.status,/CIRCUIT BREAK/);assert.equal(stopped.state.trades.length,0);
// Emergency paper close preserves completed loss and disarms; no broker interaction.
const e=emergencyPaperClose({...a,state:{...a.state,armed:true,position:{dir:1,qty:1,entry:100,id:'x',openedAt:t0,stop:95,target:110}}},candle(134,100,102,98,101),atNow(134));
assert.equal(e.state.armed,false);assert.equal(e.state.position,null);assert.equal(e.state.trades[0].reason,'MANUAL_PAPER_FLATTEN');
const source=await import('node:fs');
for(const path of ['paper_engine.mjs','paper_ui.mjs','market_api.py']){
 const s=source.readFileSync(path,'utf8');assert(!/place_order\s*\(|api\.india\.delta\.exchange\/v2\/orders|kite\.place_order\(/i.test(s),'Must not include live broker order call: '+path);
}
assert(source.readFileSync('index.html','utf8').includes('id="page-paper"'));
assert(source.readFileSync('app.mjs','utf8').includes("mountPaper({client,onPage:page})"));
console.log('PASS: paper arming, no historical fills on start, next-bar replay, SL-first, risk sizing, stop, emergency flatten, missed-data circuit, no broker order calls');
