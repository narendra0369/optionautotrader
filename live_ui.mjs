// Broker-ready interface, NOT a live trading terminal. Angel one-time inputs are sent only over authenticated HTTPS to RAM-only verification.
// Live execution is hard-disabled in the backend, independent of UI state.
const $ = id => document.getElementById(id);
const API = (location.hostname === 'optionx-v7-frontend-test-staging.onrender.com')
  ? 'https://optionx-v7-offline-test-staging.onrender.com'
  : 'https://optionx-market-feed.onrender.com';
const DOCS = {Zerodha:'https://kite.trade/docs/connect/v3/',Angel:'https://smartapi.angelone.in/docs',Stoxkart:'https://developers.stoxkart.com/api-documentation/login',Dhan:'https://dhanhq.co/docs/v2/authentication/',Delta:'https://docs.delta.exchange/'};
const marketBrokers = {NIFTY:['Angel','Stoxkart'],BANKNIFTY:['Angel','Stoxkart'],BTC:['Delta']};
const formats = {INR: new Intl.NumberFormat('en-IN',{style:'currency',currency:'INR',maximumFractionDigits:2}),USD:new Intl.NumberFormat('en-US',{style:'currency',currency:'USD',maximumFractionDigits:2})};

// Greeks use manually entered, unverified broker-style snapshot values.
// These functions make PAPER PREVIEWS ONLY: no HTTP calls, order methods or
// storage. MARKET/IOC forbidden, and there is no exchange-native OCO assumed.
export function planGreekExit(d){
 const fail=(code)=>({status:'BLOCKED',code,canSubmitRealOrder:false,brokerOrdersSent:0});
 if(!d||typeof d!=='object')return fail('MISSING_INPUT');
 const preset={ORB18:1,EMA:0.85,IV_DEFENSE:0.65}[d.strategy];
 if(!preset)return fail('INVALID_STRATEGY');
 if(d.orderType!=='LIMIT'||d.duration!=='DAY')return fail('MARKET_OR_IOC_NOT_PERMITTED');
 if(!['CE','PE'].includes(d.optionType))return fail('OPTION_TYPE_REQUIRED');
 const get=k=>d[k]===''||d[k]===undefined||d[k]===null||typeof d[k]==='boolean'?NaN:Number(d[k]);
 const [price,lot,lots,tick,risk,reward,delta,gamma,theta,vega,iv,spot,ivShock,mins]=
 ['premium','lotSize','lots','tick','maxRisk','reward','delta','gamma','theta','vega','iv','spotMove','ivShock','minutes'].map(get);
 if([price,lot,lots,tick,risk,reward,delta,gamma,theta,vega,iv,spot,ivShock,mins].some(x=>!Number.isFinite(x)))
   return fail('FRESH_VERIFIED_NUMERIC_INPUT_REQUIRED');
 if(!Number.isSafeInteger(lot)||!Number.isSafeInteger(lots)||lot<1||lot>10000||lots<1||lots>100||
   lot*lots>100000)return fail('INVALID_LOT_SIZE');
 if(price<=tick||price>1000000||tick<=0||tick>100||risk<=0||risk>1e7||reward<=0||reward>1e7||
    Math.abs(delta)>1||gamma<0||gamma>5||Math.abs(theta)>10000||vega<0||vega>10000||
    iv<=0||iv>200||spot<=0||spot>20000||ivShock<0||ivShock>50||
    mins<=0||mins>375||d.optionType==='CE'&&delta<=0||d.optionType==='PE'&&delta>=0)
   return fail('CONTRACT_OR_GREEKS_OUT_OF_RANGE');
 if(Math.abs(price/tick-Math.round(price/tick))>1e-7)return fail('OPTION_PREMIUM_TICK_MISMATCH');
 const qty=lot*lots,lossPerUnit=risk/qty;
 if(lossPerUnit<tick-1e-10)return fail('RISK_BUDGET_LESS_THAN_ONE_TICK');
 // Hypothetical scenario ONLY, not a price forecast. Theta/day, Vega/IV-pt
 // unit assumptions require independent broker verification.
 const signed=Math.sign(delta),adverseSpot=-signed*spot,positiveSpot=signed*spot;
 const adverse=delta*adverseSpot+0.5*gamma*adverseSpot*adverseSpot+
      theta*(mins/375)-vega*ivShock;
 const favourable=delta*positiveSpot+0.5*gamma*positiveSpot*positiveSpot+
      theta*(mins/375)+vega*ivShock;
 const greekAdverse=Math.max(0,-adverse),greekFavourable=Math.max(0,favourable);
 const width=Math.min(lossPerUnit*preset,Math.max(tick,greekAdverse*preset));
 const sl=Math.ceil((price-width)/tick-1e-9)*tick;
 const tgt=Math.ceil((price+reward/qty)/tick-1e-9)*tick;
 const round=x=>Math.round((x+Number.EPSILON)*1e8)/1e8;
 const stop=round(sl),target=round(tgt),limit=round(sl-tick);
 const loss=round((price-stop)*qty),profit=round((target-price)*qty);
 if(!(limit>0&&stop<price&&target>price&&loss>0&&loss<=risk+1e-6&&profit>=reward-1e-6))
   return fail('NO_VALID_TICK_ALIGNED_EXIT');
 return {status:'PREVIEW_READY',mode:'MANUAL_GREEKS_PAPER_PREVIEW',
   sourceAuthenticated:false,canSubmitRealOrder:false,brokerOrdersSent:0,
   entryLimit:price,quantity:qty,stopTrigger:stop,stopLimit:limit,
   targetLimit:target,estimatedLossINR:loss,estimatedProfitINR:profit,
   greekAdverse:round(adverse),greekFavourable:round(favourable),
   targetAboveScenario:greekFavourable<target-price,
   entryOrderType:'LIMIT',stopOrderType:'STOPLOSS_LIMIT',
   targetOrderType:'LIMIT',duration:'DAY',
   protectiveExitRequiresBrokerFill:true,
   targetRequiresStopCancellationAndFreshPosition:true};
}

export function mountLive({client, onPage}){
 let user=null, busy=false, last=null, loadingProducts=false, lastMarket='NIFTY';
 let selectedAngelContract=null,angelNfoLoading=false,angelQuoteLoading=false;
 let selectedAngelCandles=null,angelCandleLoading=false;
 const msg=t=>{$('liveStatus').textContent=t};
 const setText=(id,t)=>{$(id).textContent=t};
 function alignMarket(){
  const m=$('liveMarket').value,b=$('liveBroker');
  for(const opt of b.options)opt.disabled=!marketBrokers[m].includes(opt.value);
  if(m!=='BTC')b.value=$(m==='NIFTY'?'routeNifty':'routeBankNifty').value;
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
  const controller=new AbortController(),tid=setTimeout(()=>controller.abort(),(path==='/api/brokers/angel/connect'||path==='/api/brokers/stoxkart/complete')?35000:path.startsWith('/api/v7/angel/auto-atm')?65000:path.startsWith('/api/v7/angel/contracts')?45000:20000);
  try{
   const res=await fetch(API+path,{...options,headers:{Authorization:'Bearer '+access,...(options.headers||{})},signal:controller.signal,mode:'cors',cache:'no-store'});
   const data=await res.json();
   if(!res.ok){
    // Only a fixed, non-sensitive error category may be shown from Angel account reads.
    const diagnostic=path.startsWith('/api/v7/angel/')&&/^[A-Z0-9_]{3,48}$/.test(data.diagnosticCode||'')
      ?' ['+data.diagnosticCode+']':'';
    throw Error((data.error||'Gateway HTTP '+res.status)+diagnostic);
   }
   return data;
  }finally{clearTimeout(tid);}
 }
 async function checkEgress(){
  const label=document.getElementById('angelEgressReport');
  if(!label)return;
  label.textContent='Checking backend outbound IPv4 (read-only)…';
  try{
   const r=await request('/api/v7/owner/egress');
   const observed=(r.observations||[]).filter(Boolean);
   label.textContent='Backend observed IPv4: '+(observed.join(' / ')||'UNAVAILABLE')
     +' · Sources: '+(r.sourcesAgreed?'agree':'NOT VERIFIED')
     +' · Registered IP compared: '+(r.registeredIpv4Configured?(r.observedMatchesConfiguredIpv4?'MATCH':'MISMATCH'):'NOT CONFIGURED')
     +' · Static IP certification: NOT VERIFIED · Orders: OFF';
  }catch(e){label.textContent='Outbound IPv4 diagnostic unavailable: '+e.message+' · Orders: OFF';}
 }
 function installEgressControl(){
  if(document.getElementById('angelEgressCheck'))return;
  const parent=$('liveBrokerStatus')?.parentElement;
  if(!parent)return;
  const button=document.createElement('button');
  button.type='button';button.id='angelEgressCheck';
  button.textContent='Check server outbound IPv4 (read-only)';
  const report=document.createElement('div');
  report.id='angelEgressReport';
  report.className='hint';
  report.textContent='Static outbound IPv4 has not been independently verified. Real orders OFF.';
  parent.append(button,report);
  button.addEventListener('click',()=>checkEgress());
 }
 installEgressControl();

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
 async function v7Readiness(){
  if(!user)return;
  setText('v7Readiness','Checking V7 development readiness…');
  try{
   const data=await request('/api/v7/readiness');
   const gates=Array.isArray(data.notIndependentlyVerified)?data.notIndependentlyVerified:[];
   const auth=data.checksConfirmedFromExistingAuth||{};
   setText('v7Readiness',
    'Owner binding: '+(auth.ownerBindingMatched?'MATCHED':'PENDING')
    +' · Angel temporary session: '+(auth.angelProfileSessionActive?'ACTIVE':'NOT ACTIVE')
    +' · Unverified prerequisites: '+gates.length
    +' · Real orders: HARD LOCKED · Offline safety tests passed; real broker order lifecycle not tested.');
  }catch(e){
   setText('v7Readiness','V7 development readiness is not deployed or unavailable. Real orders remain LOCKED.');
  }
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
   if(['Angel','Stoxkart'].includes(byMarket.NIFTY))$('routeNifty').value=byMarket.NIFTY;
   if(['Angel','Stoxkart'].includes(byMarket.BANKNIFTY))$('routeBankNifty').value=byMarket.BANKNIFTY;
   alignMarket();
   $('brokerRoutesStatus').textContent=count
     ?`Saved (${count}/3): NIFTY ${byMarket.NIFTY||'—'} · BANKNIFTY ${byMarket.BANKNIFTY||'—'} · BTC ${byMarket.BTC||'—'}. Routing is not a broker session.`
     :'No broker routing saved. Choose Angel One or Stoxkart for indices and Delta for BTC. No keys are stored.';
  }catch(e){$('brokerRoutesStatus').textContent='Could not read broker preferences: '+e.message;}
 }
 async function saveRoutes(){
  if(!user)return;
  const b=$('saveBrokerRoutes');b.disabled=true;
  $('brokerRoutesStatus').textContent='Saving routing labels securely to your signed-in account…';
  try{
   const assignments=[['NIFTY',$('routeNifty').value],['BANKNIFTY',$('routeBankNifty').value],['BTC','Delta']].map(([market,broker])=>({user_id:user.id,market,broker}));
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
 function clearAngelMarketData(message='Market-data preview cleared. No orders or quotes submitted for execution.'){
  selectedAngelContract=null;selectedAngelCandles=null;
  $('greekFetchBroker').disabled=true;
  for(const name of ['premium','lotSize','tick','delta','gamma','theta','vega','iv'])$('greek_'+name).value='';
  setText('greekBrokerStatus','Broker contract cleared. Greeks fetch requires owner-verified Angel option contract.');
  setText('greekPlanState','Old Greeks/quote cleared. Enter fresh data and recalculate. NO ORDERS.');
  $('angelNfoRows').replaceChildren();
  setText('angelNfoCandleStatus','Contract-specific 15-minute candles have not been fetched.');
  $('angelNfoCandles').disabled=true;
  $('angelNfoCsv').disabled=true;
  setText('angelNfoPrice','No verified contract selected or quote received.');
  setText('angelNfoStatus',message);
  $('angelNfoQuote').disabled=true;
 }
 async function loadAngelNfoContracts(){
  if(!user||angelNfoLoading)return;
  if(location.hostname!=='optionx-v7-frontend-test-staging.onrender.com')return;
  angelNfoLoading=true;$('angelNfoLoad').disabled=true;
  clearAngelMarketData('Loading current NFO instrument master from official Angel One source…');
  const market=$('angelNfoMarket').value,side=$('angelNfoSide').value;
  const strike=$('angelNfoStrike').value.trim();
  if(strike&&(!/^\d{3,6}(?:\.\d{1,2})?$/.test(strike)||Number(strike)<=100||Number(strike)>=500000)){
   setText('angelNfoStatus','Enter a valid optional approximate strike between 100 and 500000.');
   angelNfoLoading=false;$('angelNfoLoad').disabled=false;return;
  }
  const params=new URLSearchParams({market,side});
  if(side!=='FUT'&&strike)params.set('strike',strike);
  try{
   const data=await request('/api/v7/angel/contracts?'+params.toString());
   if(data.broker!=='Angel'||data.market!==market||data.side!==side||
      !Array.isArray(data.contracts)||data.contracts.length>30||
      data.liveExecutionEnabled!==false||data.orderExecutionEnabled!==false||data.canSubmitOrder!==false)
    throw Error('NFO_CONTRACT_METADATA_UNTRUSTED');
   const rows=$('angelNfoRows');
   for(const c of data.contracts){
    if(c.market!==market||c.side!==side||c.exchange!=='NFO'||
       typeof c.symbol!=='string'||!/^\d{2,14}$/.test(c.token)||
       typeof c.expiry!=='string'||!Number.isInteger(c.lotSize)||c.lotSize<1||
       !(Number(c.tickSize)>0))throw Error('NFO_CONTRACT_DATA_FORMAT');
    const line=document.createElement('div');line.className='delta-product';
    const name=document.createElement('div');
    const title=document.createElement('strong');title.textContent=c.symbol;
    const desc=document.createElement('small');
    desc.textContent='Expiry '+c.expiry+' · '+(side==='FUT'?'FUT':'Strike ₹'+Number(c.strike).toLocaleString('en-IN'))+
      ' · Lot '+c.lotSize+' · Tick ₹'+c.tickSize;
    name.append(title,desc);
    const select=document.createElement('button');select.type='button';
    select.className='outline';select.textContent='Select for LTP';
    select.addEventListener('click',()=>{
      selectedAngelContract={...c};selectedAngelCandles=null;
      for(const name of ['premium','lotSize','tick','delta','gamma','theta','vega','iv'])$('greek_'+name).value='';
      $('greek_lotSize').value=String(c.lotSize);
      $('greek_tick').value=String(c.tickSize);
      if(c.side==='CE'||c.side==='PE')$('greek_optionType').value=c.side;
      $('greekFetchBroker').disabled=!(c.side==='CE'||c.side==='PE');
      setText('greekBrokerStatus','Contract '+c.symbol+' selected. Fetch owner-bound Greeks if server read-only access is enabled; no orders.');
      $('angelNfoQuote').disabled=false;$('angelNfoCandles').disabled=false;$('angelNfoCsv').disabled=true;
      setText('angelNfoCandleStatus','No candles fetched yet for '+c.symbol+'.');
      setText('angelNfoPrice','Selected '+c.symbol+' · Exchange NFO · No quote fetched yet.');
      setText('angelNfoStatus','Contract selected from verified master. LTP is indicative only; click Fetch selected contract LTP.');
    });
    line.append(name,select);rows.append(line);
   }
   setText('angelNfoStatus',data.contracts.length+' current '+market+' '+side+
     ' contracts shown (earliest expiry '+data.expiry+'). Official master as of '+data.masterAsOf+
     '. Contract token/lot/tick are metadata only.');
  }catch(e){
   clearAngelMarketData('NFO Contract lookup unavailable: '+String(e.message||'Unknown')+'. No values fabricated or orders sent.');
  }finally{angelNfoLoading=false;await angelStatus();}
 }
 async function readAngelNfoLtp(){
  if(!user||!selectedAngelContract||angelQuoteLoading)return;
  const contract={...selectedAngelContract};
  angelQuoteLoading=true;$('angelNfoQuote').disabled=true;
  setText('angelNfoPrice','Reading broker LTP for '+contract.symbol+' (NO ORDER)…');
  try{
   const data=await request('/api/v7/angel/ltp?token='+encodeURIComponent(contract.token));
   if(data.broker!=='Angel'||!data.contract||
      data.contract.token!==contract.token||data.contract.symbol!==contract.symbol||
      data.contract.exchange!=='NFO'||data.liveExecutionEnabled!==false||
      data.orderExecutionEnabled!==false||data.canSubmitOrder!==false||
      data.executionPriceVerified!==false||data.quoteFreshnessVerified!==false||
      !Number.isFinite(data.ltp)||data.ltp<=0)
    throw Error('ANGEL_LTP_RESPONSE_UNTRUSTED');
   if(contract.side==='CE'||contract.side==='PE'){
     $('greek_premium').value=String(data.ltp);
     $('greekCalculate').click();
     setText('greekPlanState','Indicative option LTP loaded. Calculate PAPER research exits; no executable fill or real order.');
   }
   setText('angelNfoPrice',contract.symbol+' · LTP ₹'+
     Number(data.ltp).toLocaleString('en-IN',{minimumFractionDigits:2,maximumFractionDigits:2})+
     ' · Observed '+data.observedAt+
     ' · No exchange timestamp verification; not executable or a Paper Auto price feed.');
  }catch(e){
   setText('angelNfoPrice','LTP unavailable: '+String(e.message||'Unknown')+
     '. No synthetic price or real order.');
  }finally{
   angelQuoteLoading=false;await angelStatus();
  }
 }

 async function fetchAngelGreeks(){
  if(!user||!selectedAngelContract||!['CE','PE'].includes(selectedAngelContract.side))return;
  const contract={...selectedAngelContract},button=$('greekFetchBroker');button.disabled=true;
  setText('greekBrokerStatus','Loading authenticated Angel One Greeks from read-only server…');
  try{
   const data=await request('/api/v7/angel/greeks?token='+encodeURIComponent(contract.token));
   if(!data||data.broker!=='Angel'||data.resource!=='selectedOptionGreeks'||
      data.brokerSourceAuthenticated!==true||data.canSubmitOrder!==false||
      data.orderExecutionEnabled!==false||data.liveExecutionEnabled!==false||
      data.exchangeTimestampVerified!==false||data.executionPriceVerified!==false||
      data.contract?.token!==contract.token||data.contract?.symbol!==contract.symbol||
      data.contract?.expiry!==contract.expiry||data.contract?.side!==contract.side||
      data.contract?.lotSize!==contract.lotSize||
      data.contract?.tickSize!==contract.tickSize||!data.greeks)throw Error('BROKER_GREEKS_UNTRUSTED');
   for(const field of ['delta','gamma','theta','vega','iv']){
     const value=data.greeks[field];
     if(typeof value!=='number'||!Number.isFinite(value))throw Error('BROKER_GREEKS_INVALID');
     $('greek_'+field).value=String(value);
   }
   setText('greekBrokerStatus','Angel Greek snapshot for '+contract.symbol+' observed '+data.observedAt+
      '. Exchange timestamp and quote freshness NOT verified. No orders sent.');
   $('greekCalculate').click();
   setText('greekBrokerStatus','Greeks loaded and PAPER SL/Target recalculated if all inputs are valid. Exchange timestamp not verified; no orders.');
  }catch(e){
   setText('greekBrokerStatus','Angel Greeks disabled or unavailable: '+String(e.message||'Unknown')+
      '. Enter independently checked values manually. No real orders.');
  }finally{
   button.disabled=!(user&&selectedAngelContract&&['CE','PE'].includes(selectedAngelContract.side));
  }
 }
 async function fetchAngel15mCandles(){
  if(!user||!selectedAngelContract||angelCandleLoading)return;
  const chosen={...selectedAngelContract};
  angelCandleLoading=true;$('angelNfoCandles').disabled=true;
  selectedAngelCandles=null;$('angelNfoCsv').disabled=true;
  setText('angelNfoCandleStatus','Reading up to 3 calendar days of actual NFO 15-minute historical candles. No order…');
  try{
   const data=await request('/api/v7/angel/candles?token='+encodeURIComponent(chosen.token)+'&days=3');
   if(data.broker!=='Angel'||data.contract?.token!==chosen.token||data.contract?.symbol!==chosen.symbol||
      data.timeframe!=='15m'||data.canSubmitOrder!==false||data.liveExecutionEnabled!==false||
      data.orderExecutionEnabled!==false||data.fillPricesVerified!==false||
      !Array.isArray(data.bars)||!Number.isSafeInteger(data.barCount)||
      data.barCount!==data.bars.length||data.bars.length>700)
    throw Error('CONTRACT_15M_DATA_UNTRUSTED');
   let prev=-1;
   for(const b of data.bars){
    if(!Number.isFinite(b.time)||b.time<=prev||!Number.isFinite(b.open)||
       !Number.isFinite(b.high)||!Number.isFinite(b.low)||!Number.isFinite(b.close)||
       b.low<=0||b.high<Math.max(b.open,b.close)||b.low>Math.min(b.open,b.close)||
       !Number.isFinite(b.volume)||b.volume<0)
      throw Error('CONTRACT_15M_INVALID_BARS');
    prev=b.time;
   }
   selectedAngelCandles={contract:chosen,bars:data.bars.map(b=>({...b}))};
   $('angelNfoCsv').disabled=data.bars.length===0;
   setText('angelNfoCandleStatus',data.barCount+' verified-shape historical NFO 15m bars for '+chosen.symbol+
      ' · '+data.from+' to '+data.to+' IST. '+(data.barCount?'CSV available for research upload.':'No completed candles in window.')+
      ' Prices are not trade fills; no costs, margin or slippage are modeled.');
  }catch(e){
   selectedAngelCandles=null;$('angelNfoCsv').disabled=true;
   setText('angelNfoCandleStatus','Contract-level historical candles unavailable: '+
      String(e.message||'Unknown')+'. No synthetic bars or orders.');
  }finally{angelCandleLoading=false;await angelStatus();}
 }
 function exportAngel15mCsv(){
  if(!user||!selectedAngelCandles||!selectedAngelCandles.bars.length)return;
  const item=selectedAngelCandles;
  const lines=['time,open,high,low,close,volume',...item.bars.map(b=>
    [new Date(b.time).toISOString(),b.open,b.high,b.low,b.close,b.volume].join(','))];
  const blob=new Blob([lines.join('\n')+'\n'],{type:'text/csv;charset=utf-8'});
  const a=document.createElement('a'),url=URL.createObjectURL(blob);
  a.href=url;a.download='angel_nfo_'+item.contract.symbol+'_15m.csv';
  document.body.append(a);a.click();a.remove();
  setTimeout(()=>URL.revokeObjectURL(url),2000);
  setText('angelNfoCandleStatus',item.bars.length+' actual broker OHLC bars exported as CSV. Upload in Strategy Lab only for historical research, not live options fills.');
 }
 function clearAngelSnapshot(message='Read-only snapshot cleared. No broker orders sent.'){
  $('angelReadonlyRows').replaceChildren();
  setText('angelReadonlyStatus',message);
 }
 async function angelReadonly(resource){
  if(!user||busy)return;
  if(location.hostname!=='optionx-v7-frontend-test-staging.onrender.com'){
   clearAngelSnapshot('Personal broker snapshots are only available on the separate V7 staging website.');
   return;
  }
  if(!['positions','orderbook'].includes(resource))return;
  const btnId=resource==='positions'?'angelReadonlyPositions':'angelReadonlyOrders';
  const btn=$(btnId);btn.disabled=true;
  clearAngelSnapshot('Reading current Angel One '+(resource==='positions'?'NFO positions':'NFO order statuses')+' using GET-only endpoint…');
  try{
   const data=await request('/api/v7/angel/'+resource);
   // Fail closed with a precise, non-sensitive reason instead of conflating
   // a mismatched deployment with a broker authorization failure.
   if(!data||typeof data!=='object'||data.snapshotContract!=='OPTIONX_V7_ANGEL_READONLY_V2')
    throw Error('SNAPSHOT_VERSION_MISMATCH: Browser/backend versions differ. Hard-refresh V7 staging, then retry.');
   if(data.liveExecutionEnabled!==false||data.orderExecutionEnabled!==false)
    throw Error('SNAPSHOT_LIVE_FLAG_UNTRUSTED: Both execution safety flags must be explicitly false.');
   if(data.canSubmitOrder!==false)
    throw Error('SNAPSHOT_ORDER_FLAG_UNTRUSTED: Refusing to display unexpected order permission.');
   if(data.trustedAccount!=='OWNER_PROFILE_MATCHED')
    throw Error('SNAPSHOT_OWNER_UNVERIFIED: Broker account assertion is missing.');
   if(data.broker!=='Angel'||data.resource!==resource||!Array.isArray(data.records)
      ||!Number.isSafeInteger(data.recordCount)||data.recordCount<0
      ||data.records.length!==data.recordCount)
    throw Error('SNAPSHOT_DATA_FORMAT: Unexpected account snapshot structure. No values displayed.');
   const rows=data.records.slice(0,30),panel=$('angelReadonlyRows');
   if(!rows.length){
    clearAngelSnapshot('Broker returned no '+(resource==='positions'?'NFO positions':'NFO orders')+'. Read only; no trading was performed.');
    return;
   }
   for(const r of rows){
    if(!r||typeof r.symbol!=='string')throw Error('Unexpected broker record.');
    const line=document.createElement('div');
    line.className='delta-product';
    const label=document.createElement('strong');
    label.textContent=r.symbol.slice(0,72)+' · '+(resource==='positions'?'NFO position':'NFO order');
    const values=document.createElement('small');
    values.textContent=resource==='positions'
      ?'Net quantity: '+Number(r.net_quantity)
      :String(r.side)+' · '+String(r.status)+' · filled '+Number(r.filled_quantity)+' / '+Number(r.quantity);
    line.append(label,values);panel.append(line);
   }
   setText('angelReadonlyStatus',data.recordCount+' '+(resource==='positions'?'NFO positions':'NFO orders')
     +' received from current broker session; showing first '+rows.length+'. Read-only, no orders sent.');
  }catch(e){
   clearAngelSnapshot('Angel read-only lookup unavailable: '+String(e.message||'Unknown error')+'. This does not affect Paper mode; real orders remain blocked.');
  }finally{
   await angelStatus();
  }
 }
 // Mobile-friendly session clock. Only server expiry metadata are used.
 // No broker PIN, TOTP, JWT or API key is saved in browser storage.
 function angelSessionSummary(s){
  if(!s || s.connected !== true)return 'Not connected / session expired';
  const expires = Date.parse(s.expiresAt || '');
  if(!Number.isFinite(expires))return 'Connected, expiry unknown; recheck backend';
  const remaining = Math.max(0, Math.ceil((expires - Date.now()) / 60000));
  const local = new Date(expires).toLocaleTimeString('en-IN',{
   timeZone:'Asia/Kolkata',hour:'2-digit',minute:'2-digit',hour12:true});
  const scope = s.readOnlySessionScope === 'TRADING_DAY_READONLY'
   ? 'Day-capped read-only' : '15-minute read-only';
  return scope+' · '+remaining+' min remaining · expires '+local+' IST';
 }
 async function angelStatus(){
  if(!user)return;
  try{
   const s=await request('/api/brokers/angel/status');
   setText('angelAccountState',s.connected
    ?'Angel One profile verified · '+s.maskedClientCode+' · '+angelSessionSummary(s)+' · READ ONLY / NO AWS AUTO ORDERS'
    :'Angel not connected · enter Client Code, API Key, PIN and fresh TOTP once per session · LIVE ORDERS LOCKED');
   setText('angelAuthStatus',!s.ownerConfigured
    ?'Owner binding required on this staging backend. Login is unavailable until independently authorized.'
    :!s.ownerMatch?'This login is not authorized as the personal broker owner.'
    :s.connected?'One login is reusable while broker and local session remain valid. '+angelSessionSummary(s)+'. No PIN/TOTP stored; no real orders.'
    :'Owner verified. Enter details once, then re-authenticate on expiry. Limit: 3 attempts per 15 minutes. Broker PIN/TOTP never stored.');
   setText('liveBrokerStatus',s.connected?'Angel profile verified · NO ORDERS':'NO ACTIVE ANGEL SESSION');
   $('angelConnect').disabled=!s.ownerMatch;
   $('angelDisconnect').disabled=!s.connected;
   const canInspect=s.ownerMatch===true&&s.connected===true&&location.hostname==='optionx-v7-frontend-test-staging.onrender.com';
   $('angelReadonlyPositions').disabled=!canInspect;
   $('angelReadonlyOrders').disabled=!canInspect;
   $('angelNfoLoad').disabled=!canInspect||angelNfoLoading;
   $('angelNfoQuote').disabled=!canInspect||!selectedAngelContract||angelQuoteLoading;
   $('angelNfoCandles').disabled=!canInspect||!selectedAngelContract||angelCandleLoading;
   $('angelNfoCsv').disabled=!canInspect||!selectedAngelCandles||!selectedAngelCandles.bars.length;
   if(!s.connected){
    clearAngelSnapshot('Angel session is inactive or expired. Re-verify to request a fresh read-only snapshot.');
    clearAngelMarketData('Angel session expired. Contract selection and LTP preview cleared.');
   }
  }catch(e){setText('angelAuthStatus','Angel session status unavailable: '+e.message);$('angelConnect').disabled=true;
   $('angelReadonlyPositions').disabled=true;$('angelReadonlyOrders').disabled=true;
   clearAngelSnapshot('Broker session could not be verified. Snapshot cleared.');
   clearAngelMarketData('Broker session not verified. Market-data preview cleared.');
   $('angelNfoLoad').disabled=true;}
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
  $('angelDisconnect').disabled=true;clearAngelSnapshot('Angel session cleared. Read-only snapshot removed.');
  clearAngelMarketData('Angel session cleared. All market-data previews removed.');
  try{await request('/api/brokers/angel/disconnect',{method:'POST',headers:{'Content-Type':'application/json'},body:'{}'});setText('angelAccountState','Local Angel session cleared · no orders sent.');}
  catch(e){setText('angelAuthStatus','Could not clear local session: '+e.message);}
  await angelStatus();
 }

 async function stoxkartStatus(){
  if(!user)return;
  try{
   const st=await request('/api/brokers/stoxkart/status');
   setText('stoxkartAccountState',st.connected
     ?'Stoxkart profile verified · '+st.maskedClientCode+' · expires '+st.expiresAt+' · READ ONLY'
     :st.pendingLogin?'Stoxkart broker login started · finish the official redirect':'Stoxkart not connected · Real Money Auto Trading OFF');
   setText('stoxkartAuthStatus',!st.ownerMatch
     ?'This OptionX login is not bound as the private broker owner.'
     :st.connected?'Profile matched your Stoxkart Client ID. No order API enabled.':'Owner verified. Create a Stoxkart Superr API app and register the exact callback URL.');
   if(st.connected)setText('liveBrokerStatus','Stoxkart profile verified · NO ORDERS');
   $('stoxkartStart').disabled=!st.ownerMatch;
   $('stoxkartCheck').disabled=!st.ownerMatch;
   $('stoxkartPositions').disabled=!st.connected;
   $('stoxkartDisconnect').disabled=!st.ownerMatch||(!st.connected&&!st.pendingLogin);
  }catch(e){
   setText('stoxkartAuthStatus','Stoxkart gateway unavailable: '+e.message+' · no real orders');
   $('stoxkartStart').disabled=true;$('stoxkartPositions').disabled=true;
  }
 }
 async function stoxkartStart(){
  if(!user||location.hostname!=='optionx-v7-frontend-test-staging.onrender.com')return;
  const btn=$('stoxkartStart');btn.disabled=true;
  const body={apiKey:$('stoxkartApiKey').value.trim(),apiSecret:$('stoxkartApiSecret').value,clientCode:$('stoxkartClient').value.trim().toUpperCase()};
  for(const id of ['stoxkartApiKey','stoxkartApiSecret','stoxkartClient'])$(id).value='';
  setText('stoxkartAuthStatus','Preparing official Stoxkart login. No trading orders can be placed…');
  try{
   const result=await request('/api/brokers/stoxkart/start',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)});
   const dest=new URL(result.loginUrl);
   if(dest.origin!=='https://superrtrade.stoxkart.com'||dest.pathname!=='/login')throw Error('Unexpected broker redirect destination');
   sessionStorage.setItem('optionx_stoxkart_flow',result.flowId);
   sessionStorage.removeItem('optionx_stoxkart_callback_token');
   // Same-tab official broker login preserves flow state across redirects.
   location.assign(result.loginUrl);
  }catch(e){setText('stoxkartAuthStatus','Stoxkart login could not start: '+e.message+' · No orders sent.');}
  finally{body.apiKey=body.apiSecret=body.clientCode='';btn.disabled=false;}
 }
 async function stoxkartResume(){
  const reqToken=sessionStorage.getItem('optionx_stoxkart_callback_token');
  if(!reqToken)return;
  const flowId=sessionStorage.getItem('optionx_stoxkart_flow')||'';
  sessionStorage.removeItem('optionx_stoxkart_callback_token');
  sessionStorage.removeItem('optionx_stoxkart_flow');
  setText('stoxkartAuthStatus','Exchanging Stoxkart request token on secure backend; verifying your broker profile…');
  try{
   const payload={flowId,requestToken:reqToken};
   const result=await request('/api/brokers/stoxkart/complete',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(payload)});
   payload.flowId=payload.requestToken='';
   setText('stoxkartAuthStatus',result.connected?'Stoxkart broker account verified in RAM-only read-only session. NO real orders.':'Stoxkart login not completed.');
  }catch(e){
   setText('stoxkartAuthStatus','Stoxkart profile verification failed: '+e.message+' · Retry official broker login. No real orders.');
  }
 }
 async function stoxkartReadPositions(){
  $('stoxkartPositions').disabled=true;
  setText('stoxkartPositionsState','Reading your NFO positions using Stoxkart GET-only API…');
  try{
   const data=await request('/api/brokers/stoxkart/positions');
   const rows=Array.isArray(data.positions)?data.positions:[];
   const text=rows.length?rows.map(r=>'Token '+r.token+': '+r.netQuantity+' net qty').slice(0,8).join(' · '):'No nonzero NFO positions returned.';
   setText('stoxkartPositionsState',rows.length+' open NFO contract(s). '+text+' · READ ONLY / NO ORDERS.');
  }catch(e){setText('stoxkartPositionsState','Read-only positions unavailable: '+e.message+' · No orders sent.');}
  await stoxkartStatus();
 }
 async function stoxkartClear(){
  $('stoxkartDisconnect').disabled=true;
  sessionStorage.removeItem('optionx_stoxkart_callback_token');
  sessionStorage.removeItem('optionx_stoxkart_flow');
  try{await request('/api/brokers/stoxkart/disconnect',{method:'POST',headers:{'Content-Type':'application/json'},body:'{}'});
   setText('stoxkartAuthStatus','Temporary Stoxkart session cleared. Broker website logout is separate.');
  }catch(e){setText('stoxkartAuthStatus','Could not clear session: '+e.message);}
  await stoxkartStatus();
 }
 $('stoxkartStart').addEventListener('click',stoxkartStart);
 $('stoxkartCheck').addEventListener('click',stoxkartStatus);
 $('stoxkartPositions').addEventListener('click',stoxkartReadPositions);
 $('stoxkartDisconnect').addEventListener('click',stoxkartClear);
 $('routeNifty').addEventListener('change',()=>{if($('liveMarket').value==='NIFTY')alignMarket();});
 $('routeBankNifty').addEventListener('change',()=>{if($('liveMarket').value==='BANKNIFTY')alignMarket();});
 $('angelNfoLoad').addEventListener('click',loadAngelNfoContracts);
 $('angelNfoQuote').addEventListener('click',readAngelNfoLtp);
 $('angelNfoCandles').addEventListener('click',fetchAngel15mCandles);
 $('angelNfoCsv').addEventListener('click',exportAngel15mCsv);
 $('greekFetchBroker').addEventListener('click',fetchAngelGreeks);
 $('angelNfoClear').addEventListener('click',()=>clearAngelMarketData());
 $('angelNfoSide').addEventListener('change',()=>clearAngelMarketData('Choose Load to list contracts for selected side.'));
 $('angelNfoMarket').addEventListener('change',()=>clearAngelMarketData('Choose Load to list contracts for selected market.'));
 $('angelReadonlyPositions').addEventListener('click',()=>angelReadonly('positions'));
 $('angelReadonlyOrders').addEventListener('click',()=>angelReadonly('orderbook'));
 $('angelReadonlyClear').addEventListener('click',()=>clearAngelSnapshot());
 // On mobile, resume to a fresh status without silently re-using secrets.
 document.addEventListener('visibilitychange',()=>{
  if(!document.hidden && user) angelStatus().catch(()=>{});
 });
 setInterval(()=>{
  if(user && !document.hidden) angelStatus().catch(()=>{});
 }, 60_000);
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
 $('liveBroker').addEventListener('change',()=>{const m=$('liveMarket').value,b=$('liveBroker').value;
   if(m==='NIFTY'||m==='BANKNIFTY')$(m==='NIFTY'?'routeNifty':'routeBankNifty').value=b;
   alignMarket();
  });
 $('liveRefresh').addEventListener('click',()=>{status();v7Readiness();});
 $('liveCheck').addEventListener('click',preview);
 $('livePaper').addEventListener('click',()=>onPage('paper'));

 // Greeks research preview never calls authenticated broker APIs or order
 // endpoints. All fields are local and deliberately cleared on changes.
 const greekIDs=['strategy','optionType','orderType','duration','premium','lotSize',
    'lots','tick','maxRisk','reward','delta','gamma','theta','vega','iv',
    'spotMove','ivShock','minutes'];
 const recalcGreeks=()=>{
   const inputs=Object.fromEntries(greekIDs.map(k=>[k,$('greek_'+k).value.trim()]));
   const p=planGreekExit(inputs);
   if(p.status!=='PREVIEW_READY'){
     setText('greekPlanState','BLOCKED — '+p.code+'. Check broker contract and Greeks. No order sent.');
     for(const id of ['greekStop','greekTarget','greekRiskEstimate'])setText(id,'—');
     setText('greekScenario','No usable Greeks scenario.');
     return;
   }
   const money=v=>'₹'+v.toFixed(2);
   setText('greekStop',money(p.stopTrigger)+' (SL-LIMIT '+money(p.stopLimit)+')');
   setText('greekTarget',money(p.targetLimit)+' (SELL LIMIT DAY)');
   setText('greekRiskEstimate',money(p.estimatedLossINR)+' possible loss / '+
                                  money(p.estimatedProfitINR)+' planned profit, before fees');
   setText('greekScenario','Hypothetical Greek move: adverse '+p.greekAdverse+
          ' / favourable '+p.greekFavourable+
          (p.targetAboveScenario?' · target above scenario estimate':''));
   setText('greekPlanState','PREVIEW ONLY — Qty '+p.quantity+
     ', BUY LIMIT '+money(p.entryLimit)+', SELL SL-LIMIT '+money(p.stopTrigger)+
     ', SELL target LIMIT '+money(p.targetLimit)+
     '. Cannot place broker orders. Broker-confirmed fills, stops and stop cancellation are required; no automatic OCO.');
 };
 $('greekCalculate').addEventListener('click',recalcGreeks);
 // Every change automatically updates the *preview*, not real orders.
 // A partially typed/missing Greek fails closed without fabricating levels.
 for(const k of greekIDs){
   $('greek_'+k).addEventListener('input',recalcGreeks);
   $('greek_'+k).addEventListener('change',recalcGreeks);
 }


 // V10: Zero-manual-input ATM research autoplan. Official broker 15m index
 // candle signal chooses direction, verified NFO master chooses ATM strike.
 // We NEVER send exchange orders, assume fills or display made-up premiums.
 let autoLoading=false;
 const autoReset=()=>{
   setText('autoAtmContract','Awaiting verified 15m signal and broker ATM option');
   setText('autoAtmExits','Awaiting broker premium, Greeks and valid risk levels');
   setText('autoAtmFill','Full fill ETA unknown · 15m check is NOT a fill forecast.');
   setText('autoAtmSlots','2 entry attempts max across both indices in SHADOW policy; broker global counter unverified.');
 };
 function autoNextCheck(){
   // Fixed India UTC+05:30 timezone. Trading holidays NOT yet verified.
   const now=new Date(Date.now()+330*60000);
   let date=new Date(Date.UTC(now.getUTCFullYear(),now.getUTCMonth(),now.getUTCDate()));
   while(true){
     if(![0,6].includes(date.getUTCDay())){
       const open=date.getTime()+570*60000;
       const cutoff=date.getTime()+885*60000;
       const next=now.getTime()<open?open:open+(Math.floor((now.getTime()-open)/900000)+1)*900000;
       if(next<=cutoff){
         const d=new Date(next);
         return String(d.getUTCDate()).padStart(2,'0')+'-'+
           String(d.getUTCMonth()+1).padStart(2,'0')+'-'+d.getUTCFullYear()+' '+
           String(d.getUTCHours()).padStart(2,'0')+':'+
           String(d.getUTCMinutes()).padStart(2,'0')+' IST (provisional; NSE holidays unverified)';
       }
     }
     date=new Date(date.getTime()+86400000);
     now.setTime(date.getTime());
   }
 }
 function showAutoNext(){setText('autoAtmNext',autoNextCheck());}
 async function checkAutoATM(){
   showAutoNext();
   if(!user||autoLoading)return;
   const market=$('liveMarket').value,strategy=$('autoAtmStrategy').value;
   if(!['NIFTY','BANKNIFTY'].includes(market)){
     autoReset();setText('autoAtmStatus','Choose an Indian index in the existing market dropdown. No BTC Angel ATM plan.');return;
   }
   if(location.hostname!=='optionx-v7-frontend-test-staging.onrender.com'){
     autoReset();setText('autoAtmStatus','Owner-bound V7 staging HTTPS is required. No public broker automation.');return;
   }
   autoLoading=true;
   setText('autoAtmStatus','Checking authentic broker index 15m signal, ATM token, premium and Greeks; NO real orders…');
   try{
     const query=new URLSearchParams({market,strategy});
     const result=await request('/api/v7/angel/auto-atm?'+query);
     if(result?.broker!=='Angel'||result.market!==market||result.strategy!==strategy||
        result.canSubmitOrder!==false||result.liveOrdersEnabled!==false||
        result.dailyEntryHardCap!==2||result.dailyEntryCountVerified!==false||
        result.fillETASeconds!==null||
        !['WAITING_FOR_NEW_15M_STRATEGY_SIGNAL',
          'READONLY_ATM_PREVIEW_READY_NOT_ORDER_ELIGIBLE'].includes(result.status))
       throw Error('UNTRUSTED_BROKER_AUTO_ATM_RESPONSE');
     autoReset();
     if(typeof result.nextStrategyCheck==='string'&&result.nextStrategyCheck.length<55)
       setText('autoAtmNext',result.nextStrategyCheck+' (IST, holiday unverified)');
     if(result.status==='WAITING_FOR_NEW_15M_STRATEGY_SIGNAL'){
       setText('autoAtmStatus','No new completed 15m '+strategy+' signal. Will recheck while this signed-in tab stays open. No order.');return;
     }
     const c=result.selectedContract,p=result.exitPlan;
     if(!c||!p||p.canSubmitOrder!==false||p.liveOrdersEnabled!==false||
        c.selection!=='nearest_actual_strike_nearest_expiry'||
        !['CE','PE'].includes(c.side)||!Number.isFinite(c.premium)||
        !Number.isFinite(p.stopTrigger)||!Number.isFinite(p.stopLimit)||
        !Number.isFinite(p.targetLimit)||!Number.isFinite(p.quantity)||
        p.estimatedFillTimeSeconds!==null)
        throw Error('UNVERIFIED_OPTION_FILL_OR_EXIT');
     setText('autoAtmContract',c.symbol+' · '+c.side+' · ATM '+c.strike+
       ' · LTP ₹'+c.premium+' · 1 lot × '+c.lotSize);
     setText('autoAtmExits','SELL Stop trigger ₹'+p.stopTrigger+
       ' / stop-limit ₹'+p.stopLimit+' · Target LIMIT ₹'+p.targetLimit);
     setText('autoAtmStatus','READ-ONLY AUTO PREVIEW: '+result.signal?.signalId+
       '. Real-money orders and shared broker counter NOT connected.');
     setText('autoAtmFill','Full fill time cannot be predicted. No depth/queue/rejection evidence; LIMIT order may never fill.');
   }catch(e){
     autoReset();
     setText('autoAtmStatus','Automatic broker ATM unavailable/locked: '+
       String(e.message||'Unknown')+
       '. No fabricated premium, stop, signal or fill time; real-money locked.');
   }finally{autoLoading=false;}
 }
 $('autoAtmRefresh').addEventListener('click',checkAutoATM);
 $('autoAtmStrategy').addEventListener('change',()=>{autoReset();checkAutoATM();});
 $('liveMarket').addEventListener('change',()=>{autoReset();checkAutoATM();});
 setInterval(()=>{
   showAutoNext();
   if(user&&!document.hidden&&$('page-live').classList.contains('active'))checkAutoATM();
 },60000);
 showAutoNext();
 $('liveBrokerDocs').href=DOCS.Zerodha;alignMarket();checks([]);
 return {async setUser(u){user=u||null;
     if(!user){autoReset();setText('autoAtmStatus','Sign in and verify the private owner Angel session. No automatic live orders.');}
     else if($('page-live').classList.contains('active'))checkAutoATM();$('liveCheck').disabled=!user;$('liveRefresh').disabled=!user;$('saveBrokerRoutes').disabled=!user;$('refreshBrokerRoutes').disabled=!user;$('loadDeltaProducts').disabled=!user;if(!user){
    setText('liveGateway','Sign in required');setText('liveBrokerStatus','Not connected');setText('liveOwnerStatus','Not configured');
    setText('v7Readiness','Sign in to inspect development readiness. Real orders remain blocked.');
    setText('stoxkartAuthStatus','Sign in to OptionX before Stoxkart verification.');setText('stoxkartAccountState','Stoxkart not connected.');
    for(const id of ['stoxkartStart','stoxkartCheck','stoxkartDisconnect','stoxkartPositions'])$(id).disabled=true;
    setText('angelOwnerId','—');setText('angelAccountState','Angel not connected');setText('angelAuthStatus','Sign in to OPTIONX first');$('angelConnect').disabled=true;$('angelCheck').disabled=true;$('angelDisconnect').disabled=true;$('angelCopyOwnerId').disabled=true;
    $('angelReadonlyPositions').disabled=true;$('angelReadonlyOrders').disabled=true;clearAngelSnapshot('Sign in required. No broker snapshot is retained.');
    $('angelNfoLoad').disabled=true;clearAngelMarketData('Sign in required. No market-data selection retained.');
    setText('livePreview','No live orders; preview only.');$('brokerRoutesStatus').textContent='Sign in to save broker routing.';$('deltaProductsList').replaceChildren();checks();return;
   }setText('angelOwnerId',user.id);$('angelCopyOwnerId').disabled=false;$('angelCheck').disabled=false;await Promise.allSettled([status(),routes(),v7Readiness()]);await angelStatus();await stoxkartResume();await stoxkartStatus();},choose};
}
