// Broker-ready interface, NOT a live trading terminal. No broker secrets accepted here.
// Live execution is hard-disabled in the backend, independent of UI state.
const $ = id => document.getElementById(id);
const API = 'https://optionx-market-feed.onrender.com';
const DOCS = {Zerodha:'https://kite.trade/docs/connect/v3/',Angel:'https://smartapi.angelone.in/docs',Dhan:'https://dhanhq.co/docs/v2/authentication/',Delta:'https://docs.delta.exchange/'};
const marketBrokers = {NIFTY:['Zerodha','Angel','Dhan'],BANKNIFTY:['Zerodha','Angel','Dhan'],BTC:['Delta']};
const formats = {INR: new Intl.NumberFormat('en-IN',{style:'currency',currency:'INR',maximumFractionDigits:2}),USD:new Intl.NumberFormat('en-US',{style:'currency',currency:'USD',maximumFractionDigits:2})};
export function mountLive({client, onPage}){
 let user=null, busy=false, last=null;
 const msg=t=>{$('liveStatus').textContent=t};
 const setText=(id,t)=>{$(id).textContent=t};
 function alignMarket(){
  const m=$('liveMarket').value,b=$('liveBroker');
  for(const opt of b.options)opt.disabled=!marketBrokers[m].includes(opt.value);
  if(!marketBrokers[m].includes(b.value))b.value=marketBrokers[m][0];
  $('liveBrokerDocs').href=DOCS[b.value];
  $('liveCurrency').textContent=m==='BTC'?'USD':'INR';
  $('liveContractHint').textContent=m==='BTC'?'Exact approved Delta contract/product ID (not a spot ticker)':'Exact NFO option/future contract label (not NIFTY index)';
 }
 function checks(items=[]){
  const box=$('liveCheckResults');box.replaceChildren();
  for(const item of items){
   const d=document.createElement('div');d.className='live-check';
   const badge=document.createElement('strong');badge.textContent='BLOCKED · '+item.code;
   const desc=document.createElement('span');desc.textContent=item.detail;
   d.append(badge,desc);box.append(d);
  }
 }
 async function token(){
  if(!user||!client)throw Error('Sign in to your OPTIONX account first.');
  const {data,error}=await client.auth.getSession();
  if(error||!data.session?.access_token)throw Error('Session expired. Please sign in again.');
  if(data.session.user?.id!==user.id)throw Error('Account changed. Reload session first.');
  return data.session.access_token;
 }
 async function request(path, options={}){
  const access=await token();
  const controller=new AbortController(),tid=setTimeout(()=>controller.abort(),15000);
  try{
   const res=await fetch(API+path,{...options,headers:{Authorization:'Bearer '+access,...(options.headers||{})},signal:controller.signal,mode:'cors',cache:'no-store'});
   const data=await res.json();if(!res.ok)throw Error(data.error||'Gateway HTTP '+res.status);return data;
  }finally{clearTimeout(tid);}
 }
 async function status(){
  if(!user)return;
  setText('liveGateway','Checking secure gateway…');
  try{const data=await request('/api/live/status');
   setText('liveGateway',data.identityVerified?'Login verified · LIVE LOCKED':'Session not verified');
   setText('liveBrokerStatus',data.brokerConnected?'Broker linked':'NO BROKER CONNECTED');
   setText('liveOwnerStatus',data.ownerBindingConfigured?(data.ownerMatch?'Owner matched':'Owner mismatch'):'Owner binding pending');
   msg(data.nextStep||'Broker gateway is not ready.');
  }catch(e){setText('liveGateway','Gateway unavailable');msg('Live gateway error: '+e.message+' · No real orders can be sent.');}
 }
 async function preview(){
  if(busy)return;busy=true;$('liveCheck').disabled=true;checks();msg('Validating order preview against fail-closed gateway…');
  try{
   const market=$('liveMarket').value;
   const body={market,broker:$('liveBroker').value,side:$('liveSide').value,orderType:'LIMIT',
     contractSymbol:$('liveContract').value.trim(),strategyId:Number($('liveStrategy').value),
     quantity:Number($('liveQuantity').value),limitPrice:Number($('liveLimit').value),
     riskBudget:Number($('liveRisk').value),dailyStop:Number($('liveDaily').value),maxTrades:Number($('liveMax').value)};
   const result=await request('/api/live/preflight',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)});
   last=result;const currency=market==='BTC'?'USD':'INR';
   setText('livePreview',`${result.preview.side} ${result.preview.quantity} × ${result.preview.contractLabel || '(missing contract)'} @ ${formats[currency].format(result.preview.limitPrice)} · indicative notional ${formats[currency].format(result.preview.estimatedNotional)}`);
   checks(result.checks||[]);
   msg(`${result.blockedCount} mandatory live checks remain BLOCKED. NO ORDER WAS SENT. Quote, margin and lot size are unverified.`);
  }catch(e){msg('Preview rejected: '+e.message+' · NO ORDER WAS SENT.');}
  finally{busy=false;$('liveCheck').disabled=!user;}
 }
 function choose(market, strategy){
  if(!marketBrokers[market])return;
  $('liveMarket').value=market;if(Number.isInteger(strategy)&&strategy>=1&&strategy<=200000)$('liveStrategy').value=String(strategy);
  alignMarket();onPage('live');msg('Strategy selected for preparation. This is NOT a live trading authorization.');
 }
 $('liveMarket').addEventListener('change',alignMarket);
 $('liveBroker').addEventListener('change',alignMarket);
 $('liveRefresh').addEventListener('click',status);
 $('liveCheck').addEventListener('click',preview);
 $('livePaper').addEventListener('click',()=>onPage('paper'));
 $('liveBrokerDocs').href=DOCS.Zerodha;alignMarket();checks([]);
 return {async setUser(u){user=u||null;$('liveCheck').disabled=!user;$('liveRefresh').disabled=!user;if(!user){
    setText('liveGateway','Sign in required');setText('liveBrokerStatus','Not connected');setText('liveOwnerStatus','Not configured');
    setText('livePreview','No live orders; preview only.');checks();return;
   }await status();},choose};
}
