// OptionX browser-session paper simulator. Always SIMULATION. NEVER a broker order.
// Evaluates fully closed provider OHLC only. Entry at next bar OPEN is known only AFTER that bar closes.
// This is delayed bar-replay paper accounting, not exchange execution or tick-level fills.
import {configAt,prepare,signalFor} from './engine.mjs';
export const PAPER_MARKETS=['NIFTY','BANKNIFTY','BTC'];
export const PAPER_FRAMES={ '1m':60000,'5m':300000,'15m':900000,'30m':1800000,'1h':3600000,'4h':14400000,'1d':86400000 };
export const PRESETS={NIFTY:{capital:100000,risk:300,dailyLoss:600},BANKNIFTY:{capital:100000,risk:300,dailyLoss:600},BTC:{capital:10000,risk:15,dailyLoss:30}};
const round=(n,d=4)=>Number(n.toFixed(d));
const day=t=>new Date(t).toLocaleDateString('en-CA',{timeZone:'Asia/Kolkata'});
const valid=(n,min,max)=>Number.isFinite(n)&&n>=min&&n<=max;
export function makePaperAccount(market,opts={}){
 if(!PAPER_MARKETS.includes(market))throw Error('Invalid market');
 const preset=PRESETS[market];
 const config={market,timeframe:opts.timeframe||'15m',strategyId:opts.strategyId??1,
 capital:opts.capital??preset.capital,risk:opts.risk??preset.risk,dailyLoss:opts.dailyLoss??preset.dailyLoss,
 maxTrades:opts.maxTrades??2,costBps:opts.costBps??4,slippageBps:opts.slippageBps??2};
 assertConfig(config);
 return {config,state:{armed:false,lastBarTime:null,pending:null,position:null,cash:config.capital,realized:0,peak:config.capital,maxDrawdown:0,
 trades:[],countToday:0,pnlToday:0,day:null,status:'Stopped · never traded',updatedAt:null},version:0};
}
export function assertConfig(c){
 if(!c||!PAPER_MARKETS.includes(c.market)||!PAPER_FRAMES[c.timeframe])throw Error('Unsupported market/timeframe');
 if(!Number.isInteger(c.strategyId)||c.strategyId<1||c.strategyId>200000)throw Error('Strategy ID must be 1–200000');
 if(!valid(c.capital,100,1e9)||!valid(c.risk,0.01,1e7)||!valid(c.dailyLoss,0.01,1e8)||c.risk>c.capital*.1||c.dailyLoss>c.capital*.2)throw Error('Risk/daily loss exceeds paper safety limits');
 if(!Number.isInteger(c.maxTrades)||c.maxTrades<1||c.maxTrades>5)throw Error('Maximum trades per day: 1–5');
 if(!valid(c.costBps,0,100)||!valid(c.slippageBps,0,100))throw Error('Costs and slippage must be 0–100 basis points');
}
function compiledCfg(id){return configAt(id-1);}
export function completed(bars,tf,now=Date.now()){
 const ms=PAPER_FRAMES[tf];if(!ms)throw Error('Unsupported timeframe');
 if(!Array.isArray(bars))throw Error('Missing OHLC history');
 let previous=-Infinity;
 for(const b of bars){if(!valid(b.time,1000000000,now+86400000)||b.time<=previous||!valid(b.open,0.001,1e12)||!valid(b.close,0.001,1e12)||!valid(b.high,0.001,1e12)||!valid(b.low,0.001,1e12)||b.high<Math.max(b.open,b.close)||b.low>Math.min(b.open,b.close))throw Error('Invalid / unordered candles');previous=b.time;}
 return bars.filter(b=>b.time+ms+5000<=now);
}
const clone=a=>JSON.parse(JSON.stringify(a));
function newTradeEvent(type, details){return {type,...details};}
function addHistory(s,event){s.trades=[event,...s.trades].slice(0,100);}
function newDay(s,t){const key=day(t);if(s.day!==key){s.day=key;s.countToday=0;s.pnlToday=0;}}
// Even legacy saved 3-5 settings cannot bypass the user's global 2-entry cap.
function allowed(s,c){return s.countToday<Math.min(2,c.maxTrades)&&s.pnlToday>-c.dailyLoss&&s.cash>0;}
function stopOrTarget(b,pos){const dir=pos.dir;
 if(dir===1&&b.low<=pos.stop)return {price:Math.min(pos.stop,b.open),reason:'STOP'};
 if(dir===-1&&b.high>=pos.stop)return {price:Math.max(pos.stop,b.open),reason:'STOP'};
 if(dir===1&&b.high>=pos.target)return {price:pos.target,reason:'TARGET'};
 if(dir===-1&&b.low<=pos.target)return {price:pos.target,reason:'TARGET'};
 return null;
}
function closePosition(s,c,p,px,t,reason){const slip=c.slippageBps/10000;
 const exit=px*(1-p.dir*slip),qty=p.qty,fee=(Math.abs(p.entry)+Math.abs(exit))*qty*c.costBps/10000;
 const pnl=(exit-p.entry)*p.dir*qty-fee;
 s.cash=round(s.cash+pnl,4);s.realized=round(s.realized+pnl,4);s.pnlToday=round(s.pnlToday+pnl,4);
 s.peak=Math.max(s.peak,s.cash);s.maxDrawdown=round(Math.max(s.maxDrawdown,s.peak-s.cash),4);
 addHistory(s,newTradeEvent('CLOSE',{id:p.id,market:c.market,side:p.dir===1?'LONG':'SHORT',strategyId:c.strategyId,
 qty,entry:p.entry,exit:round(exit,6),netPnl:round(pnl,4),openedAt:p.openedAt,closedAt:t,reason,fee:round(fee,4),simulation:true}));
 s.position=null;
 if(s.pnlToday<=-c.dailyLoss){s.pending=null;s.status='Daily loss guard hit · no new entries';}
}
function openPosition(s,c,b,p){
 const raw=b.open,dir=p.dir,slip=c.slippageBps/10000,entry=raw*(1+dir*slip);
 const stopDist=p.atr*p.stopMult; if(!valid(stopDist,0.00001,1e12))return;
 const perUnitRisk=stopDist + entry*(2*c.costBps+2*c.slippageBps)/10000;
 const riskQty=c.risk/perUnitRisk;
 // No leverage on proxy symbols. BTC allows fractional units; indexes are fictitious whole index units.
 const capitalQty=Math.max(0,s.cash)/entry;
 const qty=c.market==='BTC'?Math.floor(Math.min(riskQty,capitalQty)*1e6)/1e6:Math.floor(Math.min(riskQty,capitalQty));
 if(qty<=0){s.status='Risk budget too small for one simulated unit';return;}
 s.countToday++;
 s.position={id:`paper-${b.time}-${c.market}-${c.strategyId}`,dir,qty,entry:round(entry,6),
 stop:round(entry-dir*stopDist,6),target:round(entry+dir*stopDist*p.rr,6),
 risk:round(stopDist,6),openedAt:b.time,barCount:0,highWater:0,stopMult:p.stopMult,exitMode:p.exitMode,period:p.period};
 s.status='Paper position opened (delayed bar-replay)';
}
export function armPaper(account,bars,now=Date.now()){
 const a=clone(account);assertConfig(a.config);
 const good=completed(bars,a.config.timeframe,now);
 if(good.length<120)throw Error('At least 120 completed OHLC candles required to arm');
 const last=good.at(-1);
 if(!a.state.armed){
  // No historical signals run on initial start. Existing open positions are NEVER silently erased.
  a.state.armed=true;a.state.pending=null;a.state.lastBarTime=last.time;
  a.state.status='Armed · awaiting next completed candle';a.state.updatedAt=new Date(now).toISOString();
 }
 return a;
}
export function disarmPaper(account){const a=clone(account);a.state.armed=false;a.state.pending=null;a.state.status=a.state.position?'Stopped · paper position still open':'Stopped · no new entries';a.state.updatedAt=new Date().toISOString();return a;}
export function emergencyPaperClose(account,lastCompletedBar,now=Date.now()){
 const a=clone(account);a.state.armed=false;a.state.pending=null;
 const p=a.state.position;
 if(p){if(!lastCompletedBar||!valid(lastCompletedBar.close,0.001,1e12))throw Error('Latest completed price needed for emergency simulation close');
  newDay(a.state,now);closePosition(a.state,a.config,p,lastCompletedBar.close,now,'MANUAL_PAPER_FLATTEN');
 }
 a.state.status='Emergency stop · paper engine disarmed';a.state.updatedAt=new Date(now).toISOString();return a;
}
export function stepPaper(account,bars,now=Date.now()){
 const a=clone(account);const c=a.config,s=a.state;assertConfig(c);
 if(!s.armed)return {account:a,changed:false,reason:'Disarmed'};
 const good=completed(bars,c.timeframe,now);
 if(good.length<120)throw Error('Insufficient completed candles');
 const last=good.at(-1);if(s.lastBarTime==null){s.lastBarTime=last.time;s.status='Awaiting next completed candle';s.updatedAt=new Date(now).toISOString();return {account:a,changed:true,reason:'Initialized'};}
 if(last.time<=s.lastBarTime)return {account:a,changed:false,reason:'No new closed candle'};
 const next=good.filter(b=>b.time>s.lastBarTime);
 // Do NOT secretly catch up simulated historical fills after a disconnected session.
 if(next.length>2 || (next.length>1 && next.at(-1).time-next[0].time>2*PAPER_FRAMES[c.timeframe])){
  s.armed=false;s.pending=null;s.status='CIRCUIT BREAK: missed candles; inspect position then re-arm';s.updatedAt=new Date(now).toISOString();
  return {account:a,changed:true,reason:'Gap circuit breaker'};
 }
 const features=prepare(good),strategy=compiledCfg(c.strategyId),f=features[strategy.period];
 for(const b of next){
  const i=good.findIndex(x=>x.time===b.time);
  newDay(s,b.time);
  let exited=false;
  if(s.pending&&s.pending.signalAt<b.time){
    if(allowed(s,c)&&!s.position)openPosition(s,c,b,s.pending);
    s.pending=null;
  }
  if(s.position){
   const p=s.position; p.barCount++;
   const hit=stopOrTarget(b,p);
   if(hit){closePosition(s,c,p,hit.price,b.time,hit.reason);exited=true;}
   else if(p.exitMode===3&&p.barCount>=p.period){closePosition(s,c,p,b.close,b.time,'TIME');exited=true;}
   else if(p.exitMode===1||p.exitMode===2){
    const e=p.dir===1?b.high-p.entry:p.entry-b.low;
    if(e>=p.risk){const candidate=p.exitMode===2?p.entry:p.entry+p.dir*Math.max(0,e-p.risk*.5);
       p.stop=round(p.dir===1?Math.max(p.stop,candidate):Math.min(p.stop,candidate),6);}
   }
  }
  if(!exited&&!s.position&&!s.pending&&allowed(s,c)&&i>=strategy.period*2+5){
   const at=f.at[i];if(Number.isFinite(at)&&at>0&&Number.isFinite(f.rs[i])&&Number.isFinite(f.sSlow[i])){
    const dir=signalFor(good,f,strategy,i);
    if(dir){s.pending={dir,atr:at,signalAt:b.time,rr:strategy.rr,stopMult:strategy.stop,exitMode:strategy.exit,period:strategy.period};s.status='Signal waiting for next completed candle';}
   }
  }
  s.lastBarTime=b.time;
 }
 if(!s.pending&&!s.position&&s.status!=='Daily loss guard hit · no new entries')s.status='Armed · waiting for signals';
 // Once 2 entries have opened, never accept a third regardless of SL or TP.
 // Continue managing an existing paper position until its exit is simulated.
 if(s.countToday>=2){
  s.pending=null;
  if(s.position) s.status='2/2 daily entries used · managing open paper position';
  else {s.armed=false;s.status='2/2 entries used · paper auto stopped for India day';}
 }
 s.updatedAt=new Date(now).toISOString();
 return {account:a,changed:true,reason:'Processed '+next.length+' completed candle(s)'};
}
export function paperMetrics(account,lastClose=null){const s=account.state,c=account.config;
 const closed=s.trades.filter(x=>x.type==='CLOSE'),win=closed.filter(x=>x.netPnl>0).length;
 const unreal=s.position&&Number.isFinite(lastClose)?(lastClose-s.position.entry)*s.position.dir*s.position.qty:0;
 return {equity:round(s.cash+unreal,2),cash:round(s.cash,2),realized:round(s.realized,2),openPnl:round(unreal,2),closedTrades:closed.length,
 winRate:closed.length?round(100*win/closed.length,1):null,maxDrawdown:round(s.maxDrawdown,2),currency:c.market==='BTC'?'USD':'INR'};
}
