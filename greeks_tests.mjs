// OptionX strategy Greeks research calculator safety: no broker network.
import assert from 'node:assert/strict';
globalThis.location={hostname:'optionx-v7-frontend-test-staging.onrender.com'};
const {planGreekExit}=await import('./live_ui.mjs');
const base={strategy:'ORB18',optionType:'CE',orderType:'LIMIT',duration:'DAY',
 premium:'100',lotSize:'50',lots:'1',tick:'0.05',maxRisk:'300',reward:'600',
 delta:'0.5',gamma:'0.001',theta:'-4',vega:'2',iv:'20',
 spotMove:'10',ivShock:'1',minutes:'15'};
const ok=planGreekExit(base);
assert.equal(ok.status,'PREVIEW_READY');
assert.equal(ok.entryOrderType,'LIMIT');
assert.equal(ok.stopOrderType,'STOPLOSS_LIMIT');
assert.equal(ok.targetOrderType,'LIMIT');
assert.equal(ok.duration,'DAY');
assert.equal(ok.stopTrigger,94);
assert.equal(ok.stopLimit,93.95);
assert.equal(ok.targetLimit,112);
assert.equal(ok.estimatedLossINR,300);
assert.equal(ok.estimatedProfitINR,600);
assert.equal(ok.sourceAuthenticated,false);
assert.equal(ok.canSubmitRealOrder,false);
assert.equal(ok.brokerOrdersSent,0);
assert.equal(ok.protectiveExitRequiresBrokerFill,true);
assert.equal(ok.targetRequiresStopCancellationAndFreshPosition,true);

function block(mod,reason){
 const s=planGreekExit({...base,...mod});
 assert.equal(s.status,'BLOCKED',JSON.stringify(mod));
 assert.equal(s.code,reason,JSON.stringify(mod));
 assert.equal(s.canSubmitRealOrder,false);
 assert.equal(s.brokerOrdersSent,0);
}
block({orderType:'MARKET'},'MARKET_OR_IOC_NOT_PERMITTED');
block({duration:'IOC'},'MARKET_OR_IOC_NOT_PERMITTED');
block({orderType:'STOPLOSS'},'MARKET_OR_IOC_NOT_PERMITTED');
block({optionType:'XX'},'OPTION_TYPE_REQUIRED');
block({strategy:'HFT'},'INVALID_STRATEGY');
block({delta:''},'FRESH_VERIFIED_NUMERIC_INPUT_REQUIRED');
block({premium:''},'FRESH_VERIFIED_NUMERIC_INPUT_REQUIRED');
block({lotSize:''},'FRESH_VERIFIED_NUMERIC_INPUT_REQUIRED');
block({delta:'NaN'},'FRESH_VERIFIED_NUMERIC_INPUT_REQUIRED');
block({theta:'Infinity'},'FRESH_VERIFIED_NUMERIC_INPUT_REQUIRED');
block({lotSize:'50.5'},'INVALID_LOT_SIZE');
block({lotSize:'0'},'INVALID_LOT_SIZE');
block({premium:'100.01'},'OPTION_PREMIUM_TICK_MISMATCH');
block({delta:'-0.5'},'CONTRACT_OR_GREEKS_OUT_OF_RANGE');
block({iv:'201'},'CONTRACT_OR_GREEKS_OUT_OF_RANGE');
block({gamma:'-0.1'},'CONTRACT_OR_GREEKS_OUT_OF_RANGE');
block({ivShock:'-1'},'CONTRACT_OR_GREEKS_OUT_OF_RANGE');
block({minutes:'500'},'CONTRACT_OR_GREEKS_OUT_OF_RANGE');
block({lotSize:'5000',maxRisk:'1'},'RISK_BUDGET_LESS_THAN_ONE_TICK');
block({premium:'0.05'},'CONTRACT_OR_GREEKS_OUT_OF_RANGE');

const pe=planGreekExit({...base,optionType:'PE',delta:'-0.5'});
assert.equal(pe.status,'PREVIEW_READY');
assert.ok(pe.greekAdverse<0);
const cautious=planGreekExit({...base,strategy:'IV_DEFENSE'});
assert.equal(cautious.status,'PREVIEW_READY');
assert.ok(cautious.estimatedLossINR<ok.estimatedLossINR);
assert.equal(cautious.targetLimit,ok.targetLimit);
const trend=planGreekExit({...base,strategy:'EMA'});
assert.equal(trend.status,'PREVIEW_READY');
assert.ok(trend.estimatedLossINR<=ok.estimatedLossINR);
assert.ok(Number.isFinite(trend.greekFavourable));
for(const strategy of ['ORB18','EMA','IV_DEFENSE']){
 const p=planGreekExit({...base,strategy,reward:'375',risk:'300'});
 assert.equal(p.status,'PREVIEW_READY');
 assert.ok(p.estimatedLossINR<=300.00000001);
 assert.ok(p.estimatedProfitINR>=375);
 assert.ok(p.stopLimit<p.stopTrigger && p.stopTrigger<p.entryLimit);
 assert.ok(p.targetLimit>p.entryLimit);
}
// Real order transports and private credentials remain absent from Greeks source.
import {readFileSync} from 'node:fs';
const ui=readFileSync('live_ui.mjs','utf8');
const html=readFileSync('index.html','utf8');
for(const id of ['greekCalculate','greekStop','greekTarget','greekPlanState',
                  'greek_lotSize','greek_premium','greek_iv','greek_delta'])
 assert.ok(html.includes('id="'+id+'"'),id);
assert.ok(!ui.includes("'/api/live/place-order"));
assert.ok(!ui.includes("'/api/live/orders"));
assert.ok(html.includes('MARKET / IOC BLOCKED'));
console.log('PASS: OPTIONX GREEKS SL/TP offline preview, MARKET/IOC hard blocked, fail closed and no live orders');
