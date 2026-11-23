// Broker-ready interface, NOT a live trading terminal. Angel one-time inputs are sent only over authenticated HTTPS to RAM-only verification.
// Live execution is hard-disabled in the backend, independent of UI state.
const $ = id => document.getElementById(id);
const API = 'https://optionx-market-feed.onrender.com';
const DOCS = {Zerodha:'https://kite.trade/docs/connect/v3/',Angel:'https://smartapi.angelone.in/docs',Dhan:'https://dhanhq.co/docs/v2/authentication/',Delta:'https://docs.delta.exchange/'};
const marketBrokers = {NIFTY:['Angel'],BANKNIFTY:['Angel'],BTC:['Delta']};
const formats = {INR: new Intl.NumberFormat('en-IN',{style:'currency',currency:'INR',maximumFractionDigits:2}),USD:new Intl.NumberFormat('en-US',{style:'currency',currency:'USD',maximumFractionDigits:2})};
export function mountLive({client, onPage}){
 let user=null, busy=false, last=null, loadingProducts=false, lastMarket='NIFTY';
 const msg=t=>{$('liveStatus').textContent=t};
 const setText=(id,t)=>{$(id).textContent=t};
 function alignMarket(){
  const m=$('liveMarket').value,b=$('liveBroker');
  for(const opt of b.options)opt.disabled=!marketBrokers[m].includes(opt.value);
  if(!marketBrokers[m].includes(b.value))b.value=marketBrokers[m][0];
  $('liveBrokerDocs').href=DOCS[b.value];
  $('liveCurrency').textContent=m==='BTC'?'USD':'INR';
  $('liveContractHint').textContent=m==='BTC'?'Exact approved Delta contract/product ID (not a spot ticker)':'Exact NFO option/future contract label (not NIFTY index)';
  if(m!==lastMarket && $('liveRisk').value==='300' && $('liveDaily').value==='600' && m==='BTC'){$('liveRisk').value='5';$('liveDaily').value='10';}
  if(m!==lastMarket && $('liveRisk').value==='5' && $('liveDaily').value==='10' && m!=='BTC'){$('liveRisk').value='300';$('liveDaily').value='600';}
  lastMarket=m;
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
  const controller=new AbortController(),tid=setTimeout(()=>controller.abort(),path==='/api/brokers/angel/connect'?35000:15000);
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

 async function routes(){
  if(!user) return;
  try{
   const {data,error}=await client.from('optionx_broker_routes').select('market,broker,updated_at').in('market',['NIFTY','BANKNIFTY','BTC']);
   if(error)throw Error(error.message);
   const byMarket=Object.fromEntries((data||[]).map(x=>[x.market,x.broker]));
   const count=Object.keys(byMarket).length;
   $('brokerRoutesStatus').textContent=count
     ?`Saved (${count}/3): NIFTY ${byMarket.NIFTY||'—'} · BANKNIFTY ${byMarket.BANKNIFTY||'—'} · BTC ${byMarket.BTC||'—'}. Routing is not a broker session.`
     :'No broker routing saved. Save Angel One for indices and Delta for BTC. No keys are stored.';
  }catch(e){$('brokerRoutesStatus').textContent='Could not read broker preferences: '+e.message;}
 }
 async function saveRoutes(){
  if(!user)return;
  const b=$('saveBrokerRoutes');b.disabled=true;
  $('brokerRoutesStatus').textContent='Saving routing labels securely to your signed-in account…';
  try{
   const assignments=[['NIFTY','Angel'],['BANKNIFTY','Angel'],['BTC','Delta']].map(([market,broker])=>({user_id:user.id,market,broker}));
   const {error}=await client.from('optionx_broker_routes').upsert(assignments,{onConflict:'user_id,market'});
   if(error)throw Error(error.message);
   await routes();
  }catch(e){$('brokerRoutesStatus').textContent='Could not save broker routes: '+e.message;}
  finally{b.disabled=!user;}
 }
 async function loadProducts(){
  if(!user||loadingProducts)return;
  loadingProducts=true;const btn=$('loadDeltaProducts');btn.disabled=true;
  $('deltaProductsList').replaceChildren();
  $('deltaProductsStatus').textContent='Checking Delta India public contract catalog…';
  try{
   const data=await request('/api/brokers/delta/products?kind='+encodeURIComponent($('deltaKind').value));
   const products=(data.products||[]);
   if(!products.length){$('deltaProductsStatus').textContent='Provider returned no BTC contracts in the first page. No contracts invented.';return;}
   for(const p of products){
    const row=document.createElement('div');row.className='delta-product';
    const info=document.createElement('div');
    const title=document.createElement('strong');title.textContent=p.symbol+' · '+p.contractType;
    const meta=document.createElement('small');meta.textContent=`Product #${p.id} · ${p.state} · ${p.tradingStatus} · tick ${p.tickSize||'?'} · value ${p.contractValue||'?'} ${p.contractCurrency||''}`;
    info.append(title,meta);
    const select=document.createElement('button');select.className='outline';select.textContent='Use in preview';
    select.disabled=!p.currentlyTradable;
    select.addEventListener('click',()=>{
     $('liveMarket').value='BTC';alignMarket();$('liveContract').value=p.symbol;
     $('liveQuantity').value='1';
     $('deltaProductsStatus').textContent=`${p.symbol} · Delta product ID ${p.id} selected. Exact multiplier & fill/margin remain unverified; NO ORDER SENT.`;
     msg('Delta public contract selected. Check live readiness for a blocked order preview.');
    });
    row.append(info,select);$('deltaProductsList').append(row);
   }
   $('deltaProductsStatus').textContent=`${products.length} BTC contracts shown from Delta's first live product page. Provider listing may be partial. No broker account linked.`;
  }catch(e){$('deltaProductsStatus').textContent='Delta public feed unavailable: '+e.message+' · No contracts fabricated.';}
  finally{loadingProducts=false;btn.disabled=!user;}
 }
 async function angelStatus(){
  if(!user)return;
  try{
   const s=await request('/api/brokers/angel/status');
   setText('angelAccountState',s.connected?`Angel One profile verified · ${s.maskedClientCode} · ${s.verifiedAt} · expires ${s.expiresAt} · READ ONLY`:'Angel not connected · session expired or not verified · LIVE ORDERS LOCKED');
   setText('angelAuthStatus',!s.ownerConfigured?'Owner binding required: copy the OPTIONX ID below and set OPTIONX_OWNER_USER_ID in the market-feed Render Environment.':!s.ownerMatch?'This login is not authorized as the personal broker owner.':'Owner verified. Only 3 login attempts per 15 minutes. Broker PIN/TOTP are never stored.');
   setText('liveBrokerStatus',s.connected?'Angel profile verified · NO ORDERS':'NO ACTIVE ANGEL SESSION');
   $('angelConnect').disabled=!s.ownerMatch;
   $('angelDisconnect').disabled=!s.connected;
  }catch(e){setText('angelAuthStatus','Angel session status unavailable: '+e.message);$('angelConnect').disabled=true;}
 }
 async function angelVerify(){
  if(!user)return;
  const btn=$('angelConnect');btn.disabled=true;
  const body={apiKey:$('angelApiKey').value.trim(),clientCode:$('angelClient').value.trim().toUpperCase(),pin:$('angelPin').value,totp:$('angelTotp').value.trim()};
  for(const id of ['angelApiKey','angelClient','angelPin','angelTotp'])$(id).value=''; // clear form immediately
  setText('angelAuthStatus','Contacting Angel One via secured server; no real order will be sent…');
  try{
    const s=await request('/api/brokers/angel/connect',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)});
    setText('angelAccountState',`${s.maskedClientCode} · verified ${s.verifiedAt} · expires ${s.expiresAt} · no order permissions`);
    await angelStatus();
    setText('angelAuthStatus','Angel One profile verified. A temporary server-memory session exists; real trading remains blocked.');
  }catch(e){setText('angelAuthStatus','Angel connection failed: '+e.message+' · No real orders sent.');}
  finally{body.apiKey=body.pin=body.totp='';btn.disabled=false;}
 }
 async function angelClear(){
  $('angelDisconnect').disabled=true;
  try{await request('/api/brokers/angel/disconnect',{method:'POST',headers:{'Content-Type':'application/json'},body:'{}'});setText('angelAccountState','Local Angel session cleared · no orders sent.');}
  catch(e){setText('angelAuthStatus','Could not clear local session: '+e.message);}
  await angelStatus();
 }
 $('angelConnect').addEventListener('click',angelVerify);
 $('angelCheck').addEventListener('click',angelStatus);
 $('angelDisconnect').addEventListener('click',angelClear);
 $('angelCopyOwnerId').addEventListener('click',async()=>{
  if(!user)return;
  try{await navigator.clipboard.writeText(user.id);setText('angelAuthStatus','OPTIONX user ID copied (not a broker secret). Configure it in Render only.');}
  catch{setText('angelAuthStatus','Clipboard unavailable. Select and copy the ID manually.');}
 });
 $('saveBrokerRoutes').addEventListener('click',saveRoutes);
 $('refreshBrokerRoutes').addEventListener('click',routes);
 $('loadDeltaProducts').addEventListener('click',loadProducts);
 $('liveMarket').addEventListener('change',alignMarket);
 $('liveBroker').addEventListener('change',alignMarket);
 $('liveRefresh').addEventListener('click',status);
 $('liveCheck').addEventListener('click',preview);
 $('livePaper').addEventListener('click',()=>onPage('paper'));
 $('liveBrokerDocs').href=DOCS.Zerodha;alignMarket();checks([]);
 return {async setUser(u){user=u||null;$('liveCheck').disabled=!user;$('liveRefresh').disabled=!user;$('saveBrokerRoutes').disabled=!user;$('refreshBrokerRoutes').disabled=!user;$('loadDeltaProducts').disabled=!user;if(!user){
    setText('liveGateway','Sign in required');setText('liveBrokerStatus','Not connected');setText('liveOwnerStatus','Not configured');
    setText('angelOwnerId','—');setText('angelAccountState','Angel not connected');setText('angelAuthStatus','Sign in to OPTIONX first');$('angelConnect').disabled=true;$('angelCheck').disabled=true;$('angelDisconnect').disabled=true;$('angelCopyOwnerId').disabled=true;
    setText('livePreview','No live orders; preview only.');$('brokerRoutesStatus').textContent='Sign in to save broker routing.';$('deltaProductsList').replaceChildren();checks();return;
   }setText('angelOwnerId',user.id);$('angelCopyOwnerId').disabled=false;$('angelCheck').disabled=false;await Promise.allSettled([status(),routes()]);await angelStatus();},choose};
}
