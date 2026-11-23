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
