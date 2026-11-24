// Paper Auto UI + Supabase RLS state. No broker secrets and NO live order endpoints.
import {makePaperAccount,assertConfig,armPaper,disarmPaper,emergencyPaperClose,stepPaper,paperMetrics,completed,PAPER_MARKETS,PAPER_FRAMES} from './paper_engine.mjs';
const $=id=>document.getElementById(id);
const money=(n,m)=>new Intl.NumberFormat('en-IN',{style:'currency',currency:m==='BTC'?'USD':'INR',maximumFractionDigits:2}).format(n);
const fmt=t=>t?new Date(t).toLocaleString('en-IN',{timeZone:'Asia/Kolkata',hour12:true}):'—';
const API='https://optionx-market-feed.onrender.com';
const DOCS={Zerodha:'https://kite.trade/docs/connect/v3/',Angel:'https://smartapi.angelone.in/docs',Dhan:'https://dhanhq.co/docs/v2/authentication/',Delta:'https://docs.delta.exchange/'};
export function mountPaper({client,onPage}){
 const accounts={};const latest={};let user=null,current='NIFTY',busy=false,lastError='',requestGeneration=0;
 const info=s=>{$('paperStatus').textContent=s;};
 const lock=flag=>{busy=flag;for(const id of ['paperStart','paperStop','paperFlat','paperReset','paperSync'])$(id).disabled=flag||!user;};
 const configForm=()=>{
  const m=current;
  return {market:m,timeframe:$('paperFrame').value,strategyId:Number($('paperStrategyId').value),capital:Number($('paperCapital').value),
   risk:Number($('paperRisk').value),dailyLoss:Number($('paperDaily').value),maxTrades:Number($('paperMaxTrades').value),
   costBps:Number($('paperCost').value),slippageBps:Number($('paperSlippage').value)};
 };
 const render=()=>{
  const a=accounts[current]||makePaperAccount(current),s=a.state,c=a.config,p=latest[current]?.bars?.at(-1)||null,metric=paperMetrics(a,p?.close);
  $('paperBadge').textContent=s.armed?'PAPER ARMED · TAB ACTIVE':'PAPER STOPPED';
  $('paperBadge').className='paper-badge '+(s.armed?'armed':'');
  $('paperBalance').textContent=money(metric.equity,current);
  $('paperRealized').textContent=money(metric.realized,current);
  $('paperToday').textContent=money(s.pnlToday,current);
  $('paperDrawdown').textContent=money(metric.maxDrawdown,current);
  $('paperTrades').textContent=metric.closedTrades+' closed · '+(metric.winRate===null?'—':metric.winRate+'% win');
  $('paperPosition').textContent=s.position?`${s.position.dir===1?'LONG':'SHORT'} ${s.position.qty} units @ ${s.position.entry} | Stop ${s.position.stop} | Target ${s.position.target}`:'No open paper position';
  $('paperEngineStatus').textContent=s.status;
  $('paperCheckpoint').textContent=s.lastBarTime?'Last processed closed candle: '+fmt(s.lastBarTime):'No candle processed yet';
  $('paperSource').textContent=latest[current]?`${latest[current].provider} · ${latest[current].notice}`:'Provider not checked in this browser session';
  $('paperStart').disabled=busy||!user||s.armed;
  $('paperStop').disabled=busy||!user||!s.armed;
  $('paperFlat').disabled=busy||!user||!s.position;
  $('paperReset').disabled=busy||!user;
  $('paperSync').disabled=busy||!user;
  const tbody=$('paperHistory');tbody.replaceChildren();
  const closed=s.trades.filter(t=>t.type==='CLOSE');
  if(!closed.length){const tr=document.createElement('tr'),td=document.createElement('td');td.colSpan=7;td.className='empty';td.textContent='No completed paper trades yet. Strategy scans and simulations do not guarantee a signal.';tr.append(td);tbody.append(tr);}
  for(const t of closed.slice(0,35)){
    const tr=document.createElement('tr');
    for(const [j,v] of [fmt(t.closedAt),t.side,String(t.qty),String(t.entry),String(t.exit),money(t.netPnl,current),t.reason].entries()){
      const td=document.createElement('td');td.textContent=v;if(j===5)td.className=t.netPnl>=0?'positive':'negative';tr.append(td);
    }tbody.append(tr);
  }
 };
 const fill=(c)=>{
  $('paperFrame').value=c.timeframe;$('paperStrategyId').value=String(c.strategyId);$('paperCapital').value=c.capital;
  $('paperRisk').value=c.risk;$('paperDaily').value=c.dailyLoss;$('paperMaxTrades').value=String(Math.min(2,c.maxTrades));
  $('paperCost').value=c.costBps;$('paperSlippage').value=c.slippageBps;
 };
 async function load(){if(!user||!client)return;
  const id=++requestGeneration;
  const {data,error}=await client.from('optionx_paper_accounts').select('market,timeframe,strategy_id,config,state,version,updated_at').eq('user_id',user.id);
  if(id!==requestGeneration)return;
  if(error){lastError=error.message;info('Cloud paper account unavailable: '+error.message);return;}
  for(const m of PAPER_MARKETS){const row=(data||[]).find(x=>x.market===m);
   if(row){try{const a={config:row.config,state:row.state,version:Number(row.version)};assertConfig(a.config);accounts[m]=a;}catch{info('Invalid saved config for '+m+'; server record must be reviewed.');}}
   else accounts[m]=makePaperAccount(m);
  }
  fill(accounts[current].config);render();
 }
 async function readOne(m){const {data,error}=await client.from('optionx_paper_accounts').select('market,config,state,version').eq('user_id',user.id).eq('market',m).maybeSingle();if(error)throw Error(error.message);
  if(data)return {config:data.config,state:data.state,version:Number(data.version)};return makePaperAccount(m);
 }
 async function commit(m,prev,next){const table=client.from('optionx_paper_accounts');let result;
  if(prev.version===0){
    // version=0 denotes new account; existing rows always have version>=1.
    result=await table.insert({user_id:user.id,market:m,timeframe:next.config.timeframe,strategy_id:next.config.strategyId,config:next.config,state:next.state,version:1}).select('market,config,state,version').single();
  }else{
    result=await table.update({timeframe:next.config.timeframe,strategy_id:next.config.strategyId,config:next.config,state:next.state,version:prev.version+1,updated_at:new Date().toISOString()})
     .eq('user_id',user.id).eq('market',m).eq('version',prev.version).select('market,config,state,version').maybeSingle();
  }
  if(result.error)throw Error('Cloud write failed: '+result.error.message);
  if(!result.data)throw Error('Another device changed this paper account. Refresh first; no duplicate simulated trade saved.');
  accounts[m]={config:result.data.config,state:result.data.state,version:Number(result.data.version)};return accounts[m];
 }
 async function fetchCandles(m,tf){const ctrl=new AbortController(),timeout=setTimeout(()=>ctrl.abort(),45000);
   try{const resp=await fetch(`${API}/api/candles?market=${m}&timeframe=${tf}`,{cache:'no-store',signal:ctrl.signal,mode:'cors'});
      const obj=await resp.json();if(!resp.ok)throw Error(obj.error||`Feed HTTP ${resp.status}`);
      if(obj.market!==m||obj.timeframe!==tf||!Array.isArray(obj.bars)||obj.bars.length<120)throw Error('Provider returned insufficient/mismatched OHLC');
      const bars=completed(obj.bars,tf);if(bars.length<120)throw Error('120 complete bars required');
      latest[m]={...obj,bars};return latest[m];
   }finally{clearTimeout(timeout);}
 }
 async function action(kind){if(!user){info('Sign in first');return;}if(busy)return;lock(true);try{
   const m=current;let old=await readOne(m),next;
   if(kind==='start'){
     const cfg=configForm();assertConfig(cfg);
     if(old.state.position)throw Error('Close existing paper position before changing strategy or timeframe');
     if(old.state.trades.length&&cfg.capital!==old.config.capital)throw Error('Paper starting capital cannot change after trades; use Reset while flat');
     if(old.state.armed)throw Error('Already armed');
     const feed=await fetchCandles(m,cfg.timeframe);
     next=armPaper({...old,config:cfg},feed.bars);
   }else if(kind==='stop')next=disarmPaper(old);
   else if(kind==='flat'){
     if(!confirm('Emergency paper flatten? This simulates closing at the latest COMPLETED provider candle, not a broker fill.'))return;
     const feed=await fetchCandles(m,old.config.timeframe);next=emergencyPaperClose(old,feed.bars.at(-1));
   }else if(kind==='reset'){
     if(old.state.armed||old.state.position)throw Error('Stop and flatten simulated position before Reset');
     if(!confirm('Reset only '+m+' paper account and its trade history? This cannot be undone.'))return;
     const cfg=configForm();assertConfig(cfg);next=makePaperAccount(m,cfg);
   }else return;
   await commit(m,old,next);fill(accounts[m].config);info(kind.toUpperCase()+' saved to your private paper account.');render();
 }catch(e){info(e.message||String(e));}finally{lock(false);render();}}
 async function tickMarket(m){if(!user)return;
   // Re-read before every tick to avoid stale multi-device state. The update itself uses version CAS.
   const old=await readOne(m);accounts[m]=old;
   if(!old.state.armed)return;
   const feed=await fetchCandles(m,old.config.timeframe);
   const result=stepPaper(old,feed.bars);
   if(!result.changed)return;
   await commit(m,old,result.account);
 }
 async function sync(){if(!user||busy)return;lock(true);try{
   let successes=0,errors=[];
   for(const m of PAPER_MARKETS){try{await tickMarket(m);successes++;}catch(e){errors.push(m+': '+e.message);}}
   info(errors.length?'Feed or save issue (no invented fills): '+errors.join(' | '):`Paper accounts checked at ${fmt(Date.now())}; closed-bar simulation only.`);
 }finally{lock(false);render();}}
 $('paperMarket').addEventListener('change',()=>{current=$('paperMarket').value;fill((accounts[current]||makePaperAccount(current)).config);render();});
 $('paperStart').addEventListener('click',()=>action('start'));
 $('paperStop').addEventListener('click',()=>action('stop'));
 $('paperFlat').addEventListener('click',()=>action('flat'));
 $('paperReset').addEventListener('click',()=>action('reset'));
 $('paperSync').addEventListener('click',()=>sync());
 $('paperBroker').addEventListener('change',()=>{$('brokerDocs').href=DOCS[$('paperBroker').value];});
 $('brokerDocs').href=DOCS[$('paperBroker').value]||DOCS.Angel;
 setInterval(()=>{if(user&&document.visibilityState==='visible')sync();},45000);
 document.addEventListener('visibilitychange',()=>{if(!document.hidden&&user)sync();});
 render();
 return {
  async setUser(u){user=u||null;requestGeneration++;for(const m of PAPER_MARKETS)accounts[m]=makePaperAccount(m);latest.NIFTY=null;latest.BANKNIFTY=null;latest.BTC=null;
   if(user){await load();info('Signed in · paper auto runs only while this browser tab remains active.');sync();}
   else{info('Sign in to use saved paper auto trading.');render();}
  },
  choose(m,tf,id){if(!PAPER_MARKETS.includes(m)||!PAPER_FRAMES[tf]||!Number.isInteger(id)||id<1||id>200000)return;
    current=m;$('paperMarket').value=m;const a=accounts[m]||makePaperAccount(m);
    if(a.state.armed||a.state.position){info('Stop/flatten existing '+m+' paper run before changing strategy.');}
    else{fill({...a.config,timeframe:tf,strategyId:id});info(`Strategy #${id} loaded from ${m} backtest ranking. Review risk then Start Paper Auto.`);}
    render();onPage('paper');
  }
 };
}
