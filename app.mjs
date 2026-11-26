import {TOTAL,parseCSV} from './engine.mjs';
import {mountPaper} from './paper_ui.mjs';
import {mountLive} from './live_ui.mjs';
// BEGIN EMBEDDED CANDLE VIEWER (bundled because Render static build copies only app.mjs)
// Self-contained candle chart. Data are verified external OHLC only; never simulated.
const TIMEFRAMES=['1m','5m','15m','30m','1h','4h','1d'];
const FRAME_MS={'1m':60_000,'5m':300_000,'15m':900_000,'30m':1800_000,'1h':3600_000,'4h':14_400_000,'1d':86_400_000};
const API_ROOT='https://optionx-market-feed.onrender.com';
const $=id=>document.getElementById(id);
const tv={NIFTY:'NSE:NIFTY',BANKNIFTY:'NSE:BANKNIFTY',BTC:'KRAKEN:XBTUSD'};
function completeBars(bars,tf,now=Date.now()){
 if(!TIMEFRAMES.includes(tf))throw Error('Unsupported timeframe');
 // Never include a still-forming bar in a historical backtest.
 return bars.filter(b=>Number.isFinite(b.time)&&Number.isFinite(b.close)&&b.time+FRAME_MS[tf]<=now-5000);
}
function dateLabel(t,tf){return new Date(t).toLocaleString('en-IN',{month:'short',day:'2-digit',...(tf!=='1d'?{hour:'2-digit',minute:'2-digit',hour12:false}:{})});}
function symbolPrice(m,n){return (m==='BTC'?'$':'₹')+n.toLocaleString('en-IN',{maximumFractionDigits:m==='BTC'?2:2,minimumFractionDigits:2});}
function mountCharts({onResearch}){
 let market='NIFTY',tf='15m',source='Kraken',payload=null,seen='',busy=false,view=110,endOffset=0,hoverIndex=null,dragX=null;
 const canvas=$('priceCanvas'),ctx=canvas.getContext('2d');
 const chart=$('chartArea');
 const status=(t)=>{$('chartStatus').textContent=t;};
 const setLink=()=>{$('tvLink').href='https://www.tradingview.com/chart/?symbol='+encodeURIComponent(tv[market])+'&interval='+encodeURIComponent(tf==='1d'?'D':tf==='1h'?'60':tf==='4h'?'240':tf.slice(0,-1));};
 const nowLabel=()=>new Date().toLocaleTimeString('en-IN',{timeZone:'Asia/Kolkata',hour:'2-digit',minute:'2-digit'});
 const redraw=()=>{
  const dpr=Math.min(2,window.devicePixelRatio||1),w=Math.max(250,chart.clientWidth),h=Math.max(290,chart.clientHeight);
  if(canvas.width!==Math.round(w*dpr)||canvas.height!==Math.round(h*dpr)){canvas.width=Math.round(w*dpr);canvas.height=Math.round(h*dpr);canvas.style.width=w+'px';canvas.style.height=h+'px';}
  ctx.setTransform(dpr,0,0,dpr,0,0);ctx.clearRect(0,0,w,h);ctx.fillStyle='#0d1422';ctx.fillRect(0,0,w,h);
  const all=payload?.bars||[];if(!all.length){ctx.fillStyle='#a7b3c7';ctx.font='14px system-ui';ctx.textAlign='center';ctx.fillText('Choose a market & timeframe, then load candles',w/2,h/2);return;}
  const left=12,top=20,right=86,bottom=36,priceH=h-105,paneBottom=top+priceH;
  const visible=Math.min(all.length,Math.min(350,Math.max(22,Math.round(view))));
  const end=Math.min(all.length,Math.max(visible,all.length-endOffset)),start=Math.max(0,end-visible),bars=all.slice(start,end);
  if(!bars.length)return;
  const lo=Math.min(...bars.map(x=>x.low)),hi=Math.max(...bars.map(x=>x.high)),pad=Math.max(.0001,(hi-lo)*.08),vmin=lo-pad,vmax=hi+pad;
  const plotW=w-right-left,bw=plotW/bars.length,priceY=p=>top+((vmax-p)/(vmax-vmin))*priceH;
  ctx.strokeStyle='#273348';ctx.lineWidth=1;ctx.font='11px system-ui';ctx.fillStyle='#94a4bd';ctx.textAlign='left';
  for(let j=0;j<=5;j++){const py=top+priceH*j/5;ctx.beginPath();ctx.moveTo(left,py);ctx.lineTo(w-right+3,py);ctx.stroke();ctx.fillText((vmax-(vmax-vmin)*j/5).toFixed(market==='BTC'?0:1),w-right+9,py+4);}
  const vmaxVol=Math.max(1,...bars.map(b=>b.volume||0));
  for(let i=0;i<bars.length;i++){
   const b=bars[i],x=left+(i+.5)*bw,color=b.close>=b.open?'#36b993':'#d46b75';
   ctx.strokeStyle=color;ctx.fillStyle=color;ctx.lineWidth=Math.max(1,Math.min(2,bw*.14));ctx.beginPath();ctx.moveTo(x,priceY(b.high));ctx.lineTo(x,priceY(b.low));ctx.stroke();
   const bodyY=Math.min(priceY(b.open),priceY(b.close)),bodyH=Math.max(1,Math.abs(priceY(b.close)-priceY(b.open)));
   ctx.fillRect(x-Math.max(1,bw*.31),bodyY,Math.max(2,bw*.62),bodyH);
   if(b.volume>0)ctx.globalAlpha=.30,ctx.fillRect(x-bw*.3,paneBottom+6,Math.max(2,bw*.6),Math.max(1,(b.volume/vmaxVol)*42)),ctx.globalAlpha=1;
  }
  ctx.fillStyle='#9caabe';ctx.font='11px system-ui';ctx.textAlign='center';
  const tickCount=Math.min(6,Math.max(2,Math.floor(w/150)));
  for(let j=0;j<tickCount;j++){const i=Math.round(j*(bars.length-1)/(tickCount-1));ctx.fillText(dateLabel(bars[i].time,tf),left+(i+.5)*bw,paneBottom+65);}
  const last=bars.at(-1),p=priceY(last.close);
  ctx.strokeStyle=last.close>=last.open?'#36b993':'#d46b75';ctx.setLineDash([4,5]);ctx.beginPath();ctx.moveTo(left,p);ctx.lineTo(w-right,p);ctx.stroke();ctx.setLineDash([]);
  if(hoverIndex!=null){const i=Math.min(bars.length-1,Math.max(0,hoverIndex));const b=bars[i];
   const x=left+(i+.5)*bw;ctx.strokeStyle='#8fa0b9';ctx.setLineDash([3,4]);ctx.beginPath();ctx.moveTo(x,top);ctx.lineTo(x,paneBottom);ctx.stroke();ctx.setLineDash([]);
   ctx.fillStyle='#0b1321';ctx.fillRect(left+8,top+5,Math.min(plotW-16,400),25);ctx.fillStyle='#e6ecf4';ctx.font='12px system-ui';ctx.textAlign='left';
   ctx.fillText(`${dateLabel(b.time,tf)}    O ${b.open.toFixed(2)}  H ${b.high.toFixed(2)}  L ${b.low.toFixed(2)}  C ${b.close.toFixed(2)}`,left+16,top+23);
  }
 };
 const setMarket=m=>{if(!tv[m])return;market=m;$('chartMarket').value=m;$('chartBTCSource').disabled=m!=='BTC';setLink();status('Market selected. Load candles.');};
 const setFrame=f=>{if(!TIMEFRAMES.includes(f))return;tf=f;$('chartTimeframe').value=f;setLink();};
 async function refresh(userInitiated=true){if(busy)return;busy=true;$('loadChart').disabled=true;status('Loading '+market+' '+tf+' candles from provider…');
  try{
    const url=market==='BTC'&&source==='Delta'
      ?`${API_ROOT}/api/brokers/delta/candles?symbol=BTCUSD&timeframe=${encodeURIComponent(tf)}`
      :`${API_ROOT}/api/candles?market=${encodeURIComponent(market)}&timeframe=${encodeURIComponent(tf)}`;
    const ctrl=new AbortController(),id=setTimeout(()=>ctrl.abort(),50000);
    let response;try{response=await fetch(url,{signal:ctrl.signal,mode:'cors',cache:'no-cache'});}finally{clearTimeout(id);}
    let data;try{data=await response.json();}catch{throw Error(`Feed returned HTTP ${response.status}`);}
    if(!response.ok)throw Error(data.error||'Data unavailable');
    if(data.market!==market||data.timeframe!==tf||!Array.isArray(data.bars)||data.bars.length<25)throw Error('Incomplete provider candles');
    const valid=data.bars.every((b,i)=>Number.isFinite(b.time)&&b.open>0&&b.high>=Math.max(b.open,b.close)&&b.low<=Math.min(b.open,b.close)&&(i===0||b.time>data.bars[i-1].time));
    if(!valid)throw Error('Invalid/out-of-order provider candles');
    payload=data;seen=market+'/'+tf+'/'+source;hoverIndex=null;endOffset=0;view=Math.min(110,data.bars.length);redraw();
    const c=data.bars.at(-1),prev=data.bars.at(-2),chg=prev?(c.close-prev.close)/prev.close*100:0;
    $('chartPrice').textContent=symbolPrice(market,c.close);$('chartChange').textContent=(chg>=0?'+':'')+chg.toFixed(2)+'% vs previous candle';
    $('chartChange').className=chg>=0?'positive':'negative';$('chartFeed').textContent=data.provider;
    $('chartStamp').textContent='Latest candle '+dateLabel(c.time,tf)+' · checked '+nowLabel()+' IST';
    $('chartNotice').textContent=data.notice+' Candle limits depend on source. Chart updates are polled, not tick-by-tick.';
    const done=completeBars(data.bars,tf);$('chartBars').textContent=`${done.length} complete / ${data.bars.length} displayed`;
    $('researchChart').disabled=done.length<100;
    status(`${data.bars.length} real provider candles loaded · ${market} ${tf} · ${(data.cacheAgeSeconds||0)>0?'cached':'fresh request'}.`);
  }catch(e){if(userInitiated){payload=null;seen='';redraw();}status('Feed unavailable: '+e.message+'. Upload CSV in Strategy Lab or use TradingView chart.');$('chartNotice').textContent='No prices invented. Index feeds can be delayed, blocked or unavailable; reload later or upload OHLC.';}
  finally{busy=false;$('loadChart').disabled=false;}
 }
 $('chartMarket').addEventListener('change',e=>{setMarket(e.target.value);refresh();});
 $('chartTimeframe').addEventListener('change',e=>{setFrame(e.target.value);refresh();});
 $('chartBTCSource').addEventListener('change',e=>{source=e.target.value==='Delta'?'Delta':'Kraken';refresh();});
 $('loadChart').addEventListener('click',()=>refresh());
 $('researchChart').addEventListener('click',()=>{
  if(!payload||seen!==market+'/'+tf+'/'+source){status('Load the selected market and timeframe first.');return;}
  const bars=completeBars(payload.bars,tf);
  if(bars.length<100){status(`Only ${bars.length} complete bars; at least 100 needed.`);return;}
  onResearch({market,timeframe:tf,bars,source:`${payload.provider} · ${market} ${tf} · ${new Date(payload.fetchedAt).toISOString()}`});
 });
 canvas.addEventListener('mousemove',e=>{const r=canvas.getBoundingClientRect();const n=Math.min(payload?.bars.length||0,Math.max(22,Math.round(view))),bw=Math.max(1,(r.width-98)/n);hoverIndex=Math.floor((e.clientX-r.left-12)/bw);if(dragX!=null){const move=Math.round((dragX-e.clientX)/bw);if(move){endOffset=Math.min(Math.max(0,(payload?.bars.length||0)-n),Math.max(0,endOffset+move));dragX=e.clientX;}}redraw();});
 canvas.addEventListener('mouseleave',()=>{hoverIndex=null;dragX=null;redraw();});canvas.addEventListener('mousedown',e=>{dragX=e.clientX;});window.addEventListener('mouseup',()=>dragX=null);
 canvas.addEventListener('wheel',e=>{if(!payload)return;e.preventDefault();view=Math.min(payload.bars.length,Math.max(22,view*(e.deltaY>0?1.17:.85)));hoverIndex=null;endOffset=0;redraw();},{passive:false});
 new ResizeObserver(redraw).observe(chart);
 $('chartBTCSource').disabled=true;setLink();redraw();
 setInterval(()=>{if($('page-markets')?.classList.contains('active')&&payload&&!busy)refresh(false);},45000);
 return {select(m){setMarket(m);},refresh,redraw};
}
// END EMBEDDED CANDLE VIEWER
// Publishable Supabase key only. NEVER place a secret or service-role key in frontend code.
const SUPABASE_URL='https://yghijfzwsvmzaffllszl.supabase.co';
const SUPABASE_PUBLISHABLE='sb_publishable_4MUEQ2Nj1siLELHYIlEJ6g_7L4QVEsr';
const byId=id=>document.getElementById(id);
const setText=(id,t)=>{byId(id).textContent=t;};
const uploads={NIFTY:null,BANKNIFTY:null,BTC:null};
let activeMarket='NIFTY',sessionUser=null,worker=null,lastRun=null,authMode='signup',saved=[];
const client=window.supabase?.createClient?.(SUPABASE_URL,SUPABASE_PUBLISHABLE,{auth:{autoRefreshToken:true,persistSession:true,detectSessionInUrl:true}});
const txt=(s)=>String(s??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const short=(n,d=2)=>n==null||!Number.isFinite(n)?'—':Number(n).toFixed(d);
const niceDate=t=>t?new Date(t).toLocaleString('en-IN',{dateStyle:'medium',timeStyle:'short'}):'—';
const headings={dashboard:'Trading research workspace',markets:'Market charts & candle explorer',paper:'Paper Auto',live:'Live Broker Setup · Locked',lab:'200K strategy factory',results:'Strategy rankings & validation',account:'My account'};
function page(name){
 if(!headings[name])return;
 document.querySelectorAll('.page').forEach(x=>x.classList.toggle('active',x.id==='page-'+name));
 document.querySelectorAll('.nav').forEach(x=>x.classList.toggle('active',x.dataset.page===name));
 setText('pageHeading',headings[name]);setText('breadcrumb',({dashboard:'Overview',markets:'Market Charts',paper:'Paper Auto',lab:'Strategy Lab',results:'Results',account:'Account'})[name]);
 location.hash=name;
}
document.querySelectorAll('[data-page]').forEach(x=>x.addEventListener('click',()=>page(x.dataset.page)));
document.querySelectorAll('[data-goto]').forEach(x=>x.addEventListener('click',()=>{if(x.dataset.market){selectMarket(x.dataset.market);if(x.dataset.goto==='markets'){chartController.select(x.dataset.market);chartController.refresh();}}page(x.dataset.goto);}));
byId('userButton').addEventListener('click',()=>page('account'));
function selectMarket(m){activeMarket=m;byId('market').value=m;const d=uploads[m];if(d)byId('labTimeframe').value=d.timeframe;updateDataInfo();}
byId('market').addEventListener('change',e=>selectMarket(e.target.value));
byId('labTimeframe').addEventListener('change',()=>updateDataInfo());
function updateDataInfo(){const d=uploads[activeMarket],tf=byId('labTimeframe').value;const matched=!!d&&d.timeframe===tf;setText('dataInfo',d?`${d.name} · ${d.bars.length.toLocaleString('en-IN')} ${d.timeframe} candles · ${niceDate(d.bars[0].time)} to ${niceDate(d.bars.at(-1).time)} · stored in this tab only${matched?'':' · choose '+d.timeframe+' timeframe to backtest loaded data'}`:'Load real candles in Live Charts, or upload CSV with headers: time, open, high, low, close. Market data stays in your browser, not Supabase.');byId('scanBtn').disabled=!matched||!!worker;}
byId('csvFile').addEventListener('change',async e=>{
 const file=e.target.files?.[0];if(!file)return;
 try{
  if(file.size>50_000_000)throw Error('Maximum file size is 50 MB');
  const bars=parseCSV(await file.text());
  const intervals=[];for(let k=1;k<bars.length;k++)if(bars[k].time>bars[k-1].time)intervals.push(bars[k].time-bars[k-1].time);
  intervals.sort((a,b)=>a-b);const median=intervals[Math.floor(intervals.length/2)];
  const tf=byId('labTimeframe').value,expected=FRAME_MS[tf];
    if(Math.abs(median-expected)>Math.max(120000,expected*.07))throw Error(`Data appears to be ${Math.round(median/60000)}-minute candles, not ${tf}. Change the timeframe selection or provide matching OHLC CSV.`);
  uploads[activeMarket]={bars,name:file.name,timeframe:byId('labTimeframe').value};
  setText('state-'+activeMarket,`${bars.length.toLocaleString('en-IN')} BARS READY`);
  setText('dataCount',Object.values(uploads).filter(Boolean).length+' / 3');updateDataInfo();setText('scanStatus','Ready to backtest '+activeMarket+' '+byId('labTimeframe').value+'.');
 }catch(err){setText('scanStatus','Invalid CSV: '+(err.message||err));e.target.value='';}
});
function stopWorker(note='Scan stopped. No partial results are ranked.'){
 if(worker){worker.terminate();worker=null;}updateDataInfo();byId('stopBtn').disabled=true;setText('scanStatus',note);
}
byId('stopBtn').addEventListener('click',()=>stopWorker());
byId('scanBtn').addEventListener('click',()=>{
 if(worker)return;const d=uploads[activeMarket];if(!d||d.timeframe!==byId('labTimeframe').value){setText('scanStatus','Load chart candles or upload CSV matching selected timeframe first.');return;}
 const feesBps=Number(byId('fees').value),limit=Number(byId('scanSize').value),depth=Number(byId('depth').value);
 if(!Number.isFinite(feesBps)||feesBps<0||feesBps>500){setText('scanStatus','Cost must be 0–500 basis points.');return;}
 if(!Number.isInteger(limit)||limit<1||limit>TOTAL)return;
 worker=new Worker('./engine.worker.mjs',{type:'module'});byId('scanBtn').disabled=true;byId('stopBtn').disabled=false;byId('progressWrap').hidden=false;byId('progressBar').style.width='0%';
 const market=activeMarket,set=d.bars;
 setText('scanStatus','Scanning '+limit.toLocaleString('en-IN')+' configurations on '+market+'...');
 worker.onmessage=async ({data:r})=>{
   if(r.type==='progress'){const pct=Math.round(r.done/r.limit*100);byId('progressBar').style.width=pct+'%';setText('progressText',`${pct}% · ${r.done.toLocaleString('en-IN')} / ${r.limit.toLocaleString('en-IN')} · ${r.viable.toLocaleString('en-IN')} positive training candidates · ${short(r.elapsed,0)}s`);}
   if(r.type==='error'){stopWorker('Backtest error: '+r.message);return;}
   if(r.type==='complete'){
     worker.terminate();worker=null;byId('stopBtn').disabled=true;byId('scanBtn').disabled=false;byId('progressBar').style.width='100%';
     const run={market:r.market,timeframe:d.timeframe,source:r.source,bars:set.length,screened:r.done,viable:r.viable,elapsed:r.elapsed,trainingBars:r.trainBars,testBars:r.testBars,splitTime:r.splitTime,costBps:r.feesBps,depth:r.depth,top:r.top,createdAt:new Date().toISOString()};
     lastRun=run;displayRun(run);page('results');setText('scanStatus',`Completed ${r.done.toLocaleString('en-IN')} configurations in ${short(r.elapsed,1)}s. Candidate selection used training data only.`);
     if(sessionUser)await saveRun(run);
   }
 };
 worker.onerror=e=>stopWorker('Worker failed: '+(e.message||'Please run from an HTTP web server.'));
 worker.postMessage({type:'scan',bars:set,market,limit,feesBps,depth,source:d.name});
});
function configName(c){return `${['SMA cross','EMA cross','RSI reverse','Donchian','Bollinger'][c.signal]} · ${['No filter','Trend','RSI','Volatility','Momentum'][c.filter]} · ${['Fixed','Trailing','Breakeven','Timed'][c.exit]} · ${c.period}p · ${c.stop}×ATR · ${c.rr}R · ${c.buffer}bps`;}
function displayRun(run){lastRun=run;setText('resultMarket',run.market+(run.timeframe?' · '+run.timeframe:''));setText('screened',run.screened.toLocaleString('en-IN'));setText('viable',run.viable.toLocaleString('en-IN'));setText('splitDate',niceDate(run.splitTime));
 const body=byId('rankingRows');body.replaceChildren();
 if(!run.top?.length){const tr=document.createElement('tr');const td=document.createElement('td');td.colSpan=10;td.className='empty';td.textContent='No candidates met the training criteria (positive R and at least 8 training trades). Try more history or different costs.';tr.append(td);body.append(tr);return;}
 for(let i=0;i<run.top.length;i++){
  const row=run.top[i],tr=document.createElement('tr');const c=row.config,t=row.train,v=row.test;
  const data=[`#${i+1}`,configName(c),String(t.trades),t.winRate===null?'—':short(t.winRate,1)+'%',short(t.netR,2)+' R',String(v.trades),v.winRate===null?'—':short(v.winRate,1)+'%'+(v.trades<5?' *':''),short(v.netR,2)+' R',short(v.maxDrawdownR,2)+' R'];
  data.forEach((val,j)=>{const td=document.createElement('td');td.textContent=val;if((j===4&&t.netR<0)||(j===7&&v.netR<0))td.className='negative';else if(j===7&&v.netR>0)td.className='positive';tr.append(td);});const td=document.createElement('td'),use=document.createElement('button');use.className='outline';use.textContent='Paper →';use.addEventListener('click',()=>paperController.choose(run.market,run.timeframe||'15m',c.id));td.append(use);const live=document.createElement('button');live.className='outline';live.textContent='Live prep →';live.addEventListener('click',()=>liveController.choose(run.market,c.id));td.append(live);tr.append(td);body.append(tr);
 }
}
function exportBlob(name,mime,contents){const blob=new Blob([contents],{type:mime}),url=URL.createObjectURL(blob);const a=document.createElement('a');a.href=url;a.download=name;a.click();setTimeout(()=>URL.revokeObjectURL(url),1000);}
byId('downloadJson').addEventListener('click',()=>{if(!lastRun){alert('Run a backtest first.');return;}exportBlob(`optionx_${lastRun.market}_${Date.now()}.json`,'application/json',JSON.stringify(lastRun,null,2));});
byId('downloadCsv').addEventListener('click',()=>{if(!lastRun){alert('Run a backtest first.');return;}const h=['rank','market','timeframe','strategy_id','signal','filter','exit','period','atr_stop','reward_R','entry_buffer_bps','train_trades','train_win_pct','train_net_R','train_profit_factor','oos_trades','oos_win_pct','oos_net_R','oos_max_drawdown_R'];const lines=[h.join(',')];lastRun.top.forEach(({config:c,train:t,test:v},i)=>lines.push([i+1,lastRun.market,lastRun.timeframe||'',c.id,c.signal,c.filter,c.exit,c.period,c.stop,c.rr,c.buffer,t.trades,t.winRate,t.netR,t.profitFactor,v.trades,v.winRate,v.netR,v.maxDrawdownR].map(x=>x??'').join(',')));exportBlob(`optionx_rankings_${lastRun.market}.csv`,'text/csv',lines.join('\n'));});
async function saveRun(run){
 try{const payload={user_id:sessionUser.id,market:run.market,timeframe:run.timeframe||'15m',source:run.source,bars:run.bars,screened:run.screened,viable:run.viable,split_time:new Date(run.splitTime).toISOString(),training_bars:run.trainingBars,test_bars:run.testBars,cost_bps:run.costBps,results:run.top};const {error}=await client.from('optionx_backtest_runs').insert(payload);if(error)throw error;await loadSaved();}
 catch(err){setText('scanStatus',`Backtest completed locally. Cloud save unavailable: ${err.message}. Export results as CSV/JSON.`);}
}
async function loadSaved(){if(!client||!sessionUser)return;const {data,error}=await client.from('optionx_backtest_runs').select('id,market,timeframe,source,bars,screened,viable,split_time,training_bars,test_bars,cost_bps,results,created_at').order('created_at',{ascending:false}).limit(20);if(error){setText('savedRuns','Cloud history unavailable: '+error.message);return;}saved=data||[];const root=byId('savedRuns');root.replaceChildren();if(!saved.length){root.textContent='No saved runs yet.';return;}
 for(const run of saved){const node=document.createElement('div');node.className='run-row';const text=document.createElement('div');const title=document.createElement('strong');title.textContent=run.market+' · '+(run.timeframe||'15m')+' · '+Number(run.screened).toLocaleString('en-IN')+' screened';const detail=document.createElement('span');detail.textContent=' · '+niceDate(run.created_at)+' · '+run.source; text.append(title,detail);const btn=document.createElement('button');btn.className='outline';btn.textContent='View';btn.addEventListener('click',()=>{displayRun({market:run.market,timeframe:run.timeframe,source:run.source,bars:run.bars,screened:run.screened,viable:run.viable,splitTime:run.split_time,trainingBars:run.training_bars,testBars:run.test_bars,costBps:run.cost_bps,top:run.results});page('results');});node.append(text,btn);root.append(node);}
}
byId('refreshRuns').addEventListener('click',loadSaved);
const paperController=mountPaper({client,onPage:page});
const liveController=mountLive({client,onPage:page});
const ownerMfaState={factorId:null,pendingEnrollment:false,busy:false,userId:null};
initOwnerMfa();
const gate=byId('authGate');function authMsg(t){setText('authStatus',t);}
function mode(m){authMode=m;byId('modeSignup').classList.toggle('selected',m==='signup');byId('modeSignin').classList.toggle('selected',m==='signin');setText('authSubmit',m==='signup'?'Create account':'Sign in');authMsg('Secure login · Paper research only');}
byId('modeSignup').addEventListener('click',()=>mode('signup'));
byId('modeSignin').addEventListener('click',()=>mode('signin'));
byId('authForm').addEventListener('submit',async e=>{
 e.preventDefault();if(!client){authMsg('Authentication library unavailable. Check internet connection and reload.');return;}
 const email=byId('email').value.trim(),password=byId('password').value;
 byId('authSubmit').disabled=true;authMsg('Connecting securely...');
 try{let result;if(authMode==='signup')result=await client.auth.signUp({email,password,options:{emailRedirectTo:location.origin+'/'}});else result=await client.auth.signInWithPassword({email,password});if(result.error)throw result.error;
  if(authMode==='signup'&&!result.data.session)authMsg('Account created. Check your email to confirm, then return here and sign in.');else authMsg('Signed in successfully.');
 }catch(err){authMsg(err.message||'Authentication failed.');}finally{byId('authSubmit').disabled=false;}
});
byId('signOut').addEventListener('click',async()=>{if(client)await client.auth.signOut();sessionUser=null;gate.hidden=false;page('dashboard');});
function setUser(user){sessionUser=user||null;paperController.setUser(sessionUser).catch(e=>setText('paperStatus','Account sync error: '+e.message));liveController.setUser(sessionUser).catch(e=>setText('liveStatus','Gateway status error: '+e.message));gate.hidden=!!user;setText('userButton',user?user.email?.split('@')[0]||'Account':'Sign in');setText('accountEmail',user?.email||'Not signed in');if(user)loadSaved();refreshOwnerMfa(user).catch(()=>mfaStatus('MFA status unavailable. Sign in again and retry.'));}
if(!client){authMsg('Authentication unavailable: could not load Supabase client. Check internet and refresh.');}
else{client.auth.onAuthStateChange((_event,session)=>setUser(session?.user));const {data,error}=await client.auth.getSession();if(error)authMsg(error.message);else setUser(data.session?.user);}
const chartController=mountCharts({onResearch:({market,timeframe,bars,source})=>{
 if(worker)stopWorker('Previous scan stopped because chart data changed.');
 uploads[market]={bars,name:source,timeframe};selectMarket(market);byId('labTimeframe').value=timeframe;
 setText('state-'+market,`${bars.length.toLocaleString('en-IN')} BARS READY`);
 setText('dataCount',Object.values(uploads).filter(Boolean).length+' / 3');
 updateDataInfo();setText('scanStatus',`Real ${market} ${timeframe} candles loaded · ${bars.length} complete bars · select scan size then Run backtest.`);page('lab');
 }});
selectMarket('NIFTY');if(headings[location.hash.substring(1)])page(location.hash.substring(1));
if(location.hash.substring(1)==='markets')chartController.refresh();


// V73 OPTIONX Google Authenticator TOTP enrollment and fresh session step-up.
// Supabase Auth owns enrollment secrets, QR and TOTP verification. Never sends
// secrets or OTP codes to OptionX trading APIs. Does not issue order permits.
function mfaStatus(message){byId('ownerMfaStatus').textContent=message;}
function ownerMfaClear(){
 ownerMfaState.factorId=null;ownerMfaState.pendingEnrollment=false;
 byId('ownerMfaQr').removeAttribute('src');
 byId('ownerMfaSetupKey').value='';
 byId('ownerMfaManual').hidden=true;
 byId('ownerMfaCode').value='';
 byId('ownerMfaSetup').hidden=true;
 byId('ownerMfaVerifyForm').hidden=true;
 byId('ownerMfaChallenge').hidden=true;
 byId('ownerMfaEnroll').disabled=true;
 byId('ownerMfaChallenge').disabled=true;
}
function mfaBusy(isBusy){
 ownerMfaState.busy=!!isBusy;
 byId('ownerMfaEnroll').disabled=!!isBusy || !sessionUser || !!ownerMfaState.factorId;
 byId('ownerMfaChallenge').disabled=!!isBusy || !sessionUser;
 byId('ownerMfaVerifyButton').disabled=!!isBusy;
 byId('ownerMfaRefresh').disabled=!!isBusy || !sessionUser;
}
async function refreshOwnerMfa(user){
 if(!client || !user){
   ownerMfaState.userId=null;ownerMfaClear();
   mfaStatus('Sign in to configure Google Authenticator.');
   return;
 }
 if(ownerMfaState.userId!==user.id){
   ownerMfaClear();ownerMfaState.userId=user.id;
 }
 if(ownerMfaState.pendingEnrollment)return;
 const result=await client.auth.mfa.listFactors();
 if(result.error)throw result.error;
 if(!sessionUser || sessionUser.id!==user.id)return;
 const verified=(result.data?.totp||[]).find(f=>f.status==='verified');
 if(!verified){
   // Supabase listFactors().totp may exclude unverified enrollments.
   // Pick the newest unfinished factor from .all for owners who have
   // already saved their secret key in Google Authenticator.
   const unverified=(result.data?.all||[])
     .filter(f=>f.factor_type==='totp' && f.status==='unverified')
     .sort((a,b)=>String(b.created_at||'').localeCompare(String(a.created_at||'')));
   const pending=(unverified.find(f=>f.id===ownerMfaState.factorId)||unverified[0]);
   ownerMfaState.factorId=pending?.id||null;
   byId('ownerMfaEnroll').disabled=false;
   byId('ownerMfaChallenge').hidden=!pending;
   byId('ownerMfaChallenge').disabled=!pending;
   byId('ownerMfaVerifyForm').hidden=!pending;
   if(pending){
     mfaStatus('Authenticator setup is pending, not yet verified. If you saved the latest setup key, enter the 6-digit code below. Otherwise press Enable to create a new setup key.');
   } else {
     byId('ownerMfaVerifyForm').hidden=true;
     mfaStatus('Google Authenticator is not enabled. Select Enable to get a private setup key.');
   }
   return;
 }
 ownerMfaState.factorId=verified.id;
 byId('ownerMfaEnroll').disabled=true;
 byId('ownerMfaChallenge').hidden=false;
 byId('ownerMfaChallenge').disabled=false;
 const aal=await client.auth.mfa.getAuthenticatorAssuranceLevel();
 if(aal.error)throw aal.error;
 if(!sessionUser || sessionUser.id!==user.id)return;
 if(aal.data?.currentLevel==='aal2'){
   byId('ownerMfaVerifyForm').hidden=true;
   byId('ownerMfaSetup').hidden=true;
   byId('ownerMfaQr').removeAttribute('src');
   mfaStatus('Google Authenticator enabled · current login MFA verified (AAL2). Live orders remain OFF.');
 } else {
   mfaStatus('Google Authenticator enabled. Verify this login with your 6-digit code.');
   byId('ownerMfaVerifyForm').hidden=false;
 }
}
function ownerQrSrc(value){
 if(typeof value!=='string'||value.length>300000)return null;
 const raw=value.trim().replace(/^\uFEFF/,'');
 if(/^data:image\/(?:svg\+xml|png);/i.test(raw))return raw;
 if((raw.startsWith('<svg')||raw.startsWith('<?xml')) && /<svg(?:\s|>)/i.test(raw) && raw.includes('</svg>'))
   return 'data:image/svg+xml;charset=utf-8,'+encodeURIComponent(raw);
 return null;
}

function initOwnerMfa(){
 byId('ownerMfaEnroll').addEventListener('click',async()=>{
   if(!client||!sessionUser||ownerMfaState.busy)return;
   mfaBusy(true);mfaStatus('Requesting a private enrollment QR from Supabase Auth…');
   try{
     const f=await client.auth.mfa.listFactors();
     if(f.error)throw f.error;
     if((f.data?.totp||[]).some(x=>x.status==='verified'))
       throw Error('Authenticator already enabled. Refresh status to verify the current login.');
     // Each new attempt must have a unique name. A previous unfinished
     // factor may exist, but its private QR secret cannot be recovered.
     // Never unenroll or replace an existing verified factor automatically.
     const attemptTag = (typeof crypto !== 'undefined' && crypto.randomUUID)
       ? crypto.randomUUID().slice(0, 12)
       : String(Date.now()) + '-' + String(Math.floor(Math.random()*1000000));
     const enrolled=await client.auth.mfa.enroll({
       factorType:'totp',
       friendlyName:'OptionX Authenticator ' + attemptTag
     });
     if(enrolled.error)throw enrolled.error;
     const factor=enrolled.data;
     if(!factor?.id || (!factor.totp?.qr_code && !factor.totp?.secret))
       throw Error('Supabase returned no authenticator enrollment details.');
     ownerMfaState.factorId=factor.id;
     ownerMfaState.pendingEnrollment=true;
     const image=ownerQrSrc(factor.totp?.qr_code);
     const secret=typeof factor.totp?.secret==='string' ? factor.totp.secret : '';
     const qrElement=byId('ownerMfaQr');
     const manual=byId('ownerMfaManual');
     const setupKey=byId('ownerMfaSetupKey');
     setupKey.value=secret;
     manual.hidden=!secret;
     qrElement.hidden=!image;
     qrElement.onerror=()=>{qrElement.hidden=true;manual.hidden=!secret;};
     if(image)qrElement.src=image;else qrElement.removeAttribute('src');
     byId('ownerMfaSetup').hidden=false;
     byId('ownerMfaVerifyForm').hidden=false;
     byId('ownerMfaChallenge').hidden=true;
     mfaStatus('Scan QR in Google Authenticator, then enter the 6-digit code to complete enrollment.');
     byId('ownerMfaCode').focus();
   }catch(err){mfaStatus('MFA setup: '+(err.message||'Unable to enroll.')); }
   finally{mfaBusy(false);}
 });
 byId('ownerMfaChallenge').addEventListener('click',async()=>{
   if(!sessionUser||!ownerMfaState.factorId||ownerMfaState.busy)return;
   byId('ownerMfaVerifyForm').hidden=false;
   mfaStatus('Enter your current Google Authenticator code for this login.');
   byId('ownerMfaCode').focus();
 });
 byId('ownerMfaVerifyForm').addEventListener('submit',async(event)=>{
   event.preventDefault();
   if(!client||!sessionUser||ownerMfaState.busy)return;
   if(!ownerMfaState.factorId){mfaStatus('No pending factor selected. Press Refresh MFA Status.');return;}
   const code=byId('ownerMfaCode').value.trim();
   if(!/^[0-9]{6}$/.test(code)){mfaStatus('Enter exactly six digits.');return;}
   mfaBusy(true);
   try{
     const confirmed=await client.auth.mfa.challengeAndVerify({
       factorId:ownerMfaState.factorId,code:code
     });
     if(confirmed.error)throw confirmed.error;
     ownerMfaState.pendingEnrollment=false;
     byId('ownerMfaCode').value='';
     byId('ownerMfaQr').removeAttribute('src');
     byId('ownerMfaSetupKey').value='';
     byId('ownerMfaManual').hidden=true;
     byId('ownerMfaSetup').hidden=true;
     mfaStatus('Code verified. Checking Supabase Auth assurance level…');
     await refreshOwnerMfa(sessionUser);
   }catch(err){
     byId('ownerMfaCode').value='';
     mfaStatus('Verification failed: '+(err.message||'Try the latest 6-digit code.'));
   }finally{mfaBusy(false);}
 });
 byId('ownerMfaRefresh').addEventListener('click',async()=>{
   if(!sessionUser||ownerMfaState.busy)return;
   mfaBusy(true);
   try{
     // Refresh factor list without discarding the pending enrollment.
     // A previously saved setup key remains usable for verification.
     await refreshOwnerMfa(sessionUser);
   }catch(err){mfaStatus('Unable to refresh MFA status: '+(err.message||'try again'));}
   finally{mfaBusy(false);}
 });
}
