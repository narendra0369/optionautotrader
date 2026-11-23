import {TOTAL,parseCSV} from './engine.mjs';
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
const headings={dashboard:'Trading research workspace',lab:'200K strategy factory',results:'Strategy rankings & validation',account:'My account'};
function page(name){
 if(!headings[name])return;
 document.querySelectorAll('.page').forEach(x=>x.classList.toggle('active',x.id==='page-'+name));
 document.querySelectorAll('.nav').forEach(x=>x.classList.toggle('active',x.dataset.page===name));
 setText('pageHeading',headings[name]);setText('breadcrumb',({dashboard:'Overview',lab:'Strategy Lab',results:'Results',account:'Account'})[name]);
 location.hash=name;
}
document.querySelectorAll('[data-page]').forEach(x=>x.addEventListener('click',()=>page(x.dataset.page)));
document.querySelectorAll('[data-goto]').forEach(x=>x.addEventListener('click',()=>{if(x.dataset.market)selectMarket(x.dataset.market);page(x.dataset.goto);}));
byId('userButton').addEventListener('click',()=>page('account'));
function selectMarket(m){activeMarket=m;byId('market').value=m;updateDataInfo();}
byId('market').addEventListener('change',e=>selectMarket(e.target.value));
function updateDataInfo(){const d=uploads[activeMarket];setText('dataInfo',d?`${d.name} · ${d.bars.length.toLocaleString('en-IN')} validated 15-minute candles · ${niceDate(d.bars[0].time)} to ${niceDate(d.bars.at(-1).time)} · stored in this tab only`:'Upload ascending 15-minute OHLC candles with headers: time, open, high, low, close. Market CSV stays in your browser and is not uploaded to Supabase.');byId('scanBtn').disabled=!d||!!worker;}
byId('csvFile').addEventListener('change',async e=>{
 const file=e.target.files?.[0];if(!file)return;
 try{
  if(file.size>50_000_000)throw Error('Maximum file size is 50 MB');
  const bars=parseCSV(await file.text());
  const intervals=[];for(let k=1;k<bars.length;k++)if(bars[k].time>bars[k-1].time)intervals.push(bars[k].time-bars[k-1].time);
  intervals.sort((a,b)=>a-b);const median=intervals[Math.floor(intervals.length/2)];
  if(Math.abs(median-900000)>90000)throw Error(`Data appears to be ${Math.round(median/60000)}-minute candles, not 15-minute. Please provide 15-minute OHLC CSV.`);
  uploads[activeMarket]={bars,name:file.name};
  setText('state-'+activeMarket,`${bars.length.toLocaleString('en-IN')} BARS READY`);
  setText('dataCount',Object.values(uploads).filter(Boolean).length+' / 3');updateDataInfo();setText('scanStatus','Ready to backtest '+activeMarket+'.');
 }catch(err){setText('scanStatus','Invalid CSV: '+(err.message||err));e.target.value='';}
});
function stopWorker(note='Scan stopped. No partial results are ranked.'){
 if(worker){worker.terminate();worker=null;}byId('scanBtn').disabled=!uploads[activeMarket];byId('stopBtn').disabled=true;setText('scanStatus',note);
}
byId('stopBtn').addEventListener('click',()=>stopWorker());
byId('scanBtn').addEventListener('click',()=>{
 if(worker)return;const d=uploads[activeMarket];if(!d){setText('scanStatus','Upload a CSV first.');return;}
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
     const run={market:r.market,source:r.source,bars:set.length,screened:r.done,viable:r.viable,elapsed:r.elapsed,trainingBars:r.trainBars,testBars:r.testBars,splitTime:r.splitTime,costBps:r.feesBps,depth:r.depth,top:r.top,createdAt:new Date().toISOString()};
     lastRun=run;displayRun(run);page('results');setText('scanStatus',`Completed ${r.done.toLocaleString('en-IN')} configurations in ${short(r.elapsed,1)}s. Candidate selection used training data only.`);
     if(sessionUser)await saveRun(run);
   }
 };
 worker.onerror=e=>stopWorker('Worker failed: '+(e.message||'Please run from an HTTP web server.'));
 worker.postMessage({type:'scan',bars:set,market,limit,feesBps,depth,source:d.name});
});
function configName(c){return `${['SMA cross','EMA cross','RSI reverse','Donchian','Bollinger'][c.signal]} · ${['No filter','Trend','RSI','Volatility','Momentum'][c.filter]} · ${['Fixed','Trailing','Breakeven','Timed'][c.exit]} · ${c.period}p · ${c.stop}×ATR · ${c.rr}R · ${c.buffer}bps`;}
function displayRun(run){lastRun=run;setText('resultMarket',run.market);setText('screened',run.screened.toLocaleString('en-IN'));setText('viable',run.viable.toLocaleString('en-IN'));setText('splitDate',niceDate(run.splitTime));
 const body=byId('rankingRows');body.replaceChildren();
 if(!run.top?.length){const tr=document.createElement('tr');const td=document.createElement('td');td.colSpan=9;td.className='empty';td.textContent='No candidates met the training criteria (positive R and at least 8 training trades). Try more history or different costs.';tr.append(td);body.append(tr);return;}
 for(let i=0;i<run.top.length;i++){
  const row=run.top[i],tr=document.createElement('tr');const c=row.config,t=row.train,v=row.test;
  const data=[`#${i+1}`,configName(c),String(t.trades),t.winRate===null?'—':short(t.winRate,1)+'%',short(t.netR,2)+' R',String(v.trades),v.winRate===null?'—':short(v.winRate,1)+'%'+(v.trades<5?' *':''),short(v.netR,2)+' R',short(v.maxDrawdownR,2)+' R'];
  data.forEach((val,j)=>{const td=document.createElement('td');td.textContent=val;if((j===4&&t.netR<0)||(j===7&&v.netR<0))td.className='negative';else if(j===7&&v.netR>0)td.className='positive';tr.append(td);});body.append(tr);
 }
}
function exportBlob(name,mime,contents){const blob=new Blob([contents],{type:mime}),url=URL.createObjectURL(blob);const a=document.createElement('a');a.href=url;a.download=name;a.click();setTimeout(()=>URL.revokeObjectURL(url),1000);}
byId('downloadJson').addEventListener('click',()=>{if(!lastRun){alert('Run a backtest first.');return;}exportBlob(`optionx_${lastRun.market}_${Date.now()}.json`,'application/json',JSON.stringify(lastRun,null,2));});
byId('downloadCsv').addEventListener('click',()=>{if(!lastRun){alert('Run a backtest first.');return;}const h=['rank','market','strategy_id','signal','filter','exit','period','atr_stop','reward_R','entry_buffer_bps','train_trades','train_win_pct','train_net_R','train_profit_factor','oos_trades','oos_win_pct','oos_net_R','oos_max_drawdown_R'];const lines=[h.join(',')];lastRun.top.forEach(({config:c,train:t,test:v},i)=>lines.push([i+1,lastRun.market,c.id,c.signal,c.filter,c.exit,c.period,c.stop,c.rr,c.buffer,t.trades,t.winRate,t.netR,t.profitFactor,v.trades,v.winRate,v.netR,v.maxDrawdownR].map(x=>x??'').join(',')));exportBlob(`optionx_rankings_${lastRun.market}.csv`,'text/csv',lines.join('\n'));});
async function saveRun(run){
 try{const payload={user_id:sessionUser.id,market:run.market,source:run.source,bars:run.bars,screened:run.screened,viable:run.viable,split_time:new Date(run.splitTime).toISOString(),training_bars:run.trainingBars,test_bars:run.testBars,cost_bps:run.costBps,results:run.top};const {error}=await client.from('optionx_backtest_runs').insert(payload);if(error)throw error;await loadSaved();}
 catch(err){setText('scanStatus',`Backtest completed locally. Cloud save unavailable: ${err.message}. Export results as CSV/JSON.`);}
}
async function loadSaved(){if(!client||!sessionUser)return;const {data,error}=await client.from('optionx_backtest_runs').select('id,market,source,bars,screened,viable,split_time,training_bars,test_bars,cost_bps,results,created_at').order('created_at',{ascending:false}).limit(20);if(error){setText('savedRuns','Cloud history unavailable: '+error.message);return;}saved=data||[];const root=byId('savedRuns');root.replaceChildren();if(!saved.length){root.textContent='No saved runs yet.';return;}
 for(const run of saved){const node=document.createElement('div');node.className='run-row';const text=document.createElement('div');const title=document.createElement('strong');title.textContent=run.market+' · '+Number(run.screened).toLocaleString('en-IN')+' screened';const detail=document.createElement('span');detail.textContent=' · '+niceDate(run.created_at)+' · '+run.source; text.append(title,detail);const btn=document.createElement('button');btn.className='outline';btn.textContent='View';btn.addEventListener('click',()=>{displayRun({market:run.market,source:run.source,bars:run.bars,screened:run.screened,viable:run.viable,splitTime:run.split_time,trainingBars:run.training_bars,testBars:run.test_bars,costBps:run.cost_bps,top:run.results});page('results');});node.append(text,btn);root.append(node);}
}
byId('refreshRuns').addEventListener('click',loadSaved);
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
function setUser(user){sessionUser=user||null;gate.hidden=!!user;setText('userButton',user?user.email?.split('@')[0]||'Account':'Sign in');setText('accountEmail',user?.email||'Not signed in');if(user)loadSaved();}
if(!client){authMsg('Authentication unavailable: could not load Supabase client. Check internet and refresh.');}
else{client.auth.onAuthStateChange((_event,session)=>setUser(session?.user));const {data,error}=await client.auth.getSession();if(error)authMsg(error.message);else setUser(data.session?.user);}
selectMarket('NIFTY');if(headings[location.hash.substring(1)])page(location.hash.substring(1));
