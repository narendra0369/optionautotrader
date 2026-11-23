// Self-contained candle chart. Data are verified external OHLC only; never simulated.
export const TIMEFRAMES=['1m','5m','15m','30m','1h','4h','1d'];
export const FRAME_MS={'1m':60_000,'5m':300_000,'15m':900_000,'30m':1800_000,'1h':3600_000,'4h':14_400_000,'1d':86_400_000};
export const API_ROOT='https://optionx-market-feed.onrender.com';
const $=id=>document.getElementById(id);
const tv={NIFTY:'NSE:NIFTY',BANKNIFTY:'NSE:BANKNIFTY',BTC:'KRAKEN:XBTUSD'};
export function completeBars(bars,tf,now=Date.now()){
 if(!TIMEFRAMES.includes(tf))throw Error('Unsupported timeframe');
 // Never include a still-forming bar in a historical backtest.
 return bars.filter(b=>Number.isFinite(b.time)&&Number.isFinite(b.close)&&b.time+FRAME_MS[tf]<=now-5000);
}
function dateLabel(t,tf){return new Date(t).toLocaleString('en-IN',{month:'short',day:'2-digit',...(tf!=='1d'?{hour:'2-digit',minute:'2-digit',hour12:false}:{})});}
function symbolPrice(m,n){return (m==='BTC'?'$':'₹')+n.toLocaleString('en-IN',{maximumFractionDigits:m==='BTC'?2:2,minimumFractionDigits:2});}
export function mountCharts({onResearch}){
 let market='NIFTY',tf='15m',payload=null,seen='',busy=false,view=110,endOffset=0,hoverIndex=null,dragX=null;
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
 const setMarket=m=>{if(!tv[m])return;market=m;$('chartMarket').value=m;setLink();status('Market selected. Load candles.');};
 const setFrame=f=>{if(!TIMEFRAMES.includes(f))return;tf=f;$('chartTimeframe').value=f;setLink();};
 async function refresh(userInitiated=true){if(busy)return;busy=true;$('loadChart').disabled=true;status('Loading '+market+' '+tf+' candles from provider…');
  try{
    const url=`${API_ROOT}/api/candles?market=${encodeURIComponent(market)}&timeframe=${encodeURIComponent(tf)}`;
    const ctrl=new AbortController(),id=setTimeout(()=>ctrl.abort(),50000);
    let response;try{response=await fetch(url,{signal:ctrl.signal,mode:'cors',cache:'no-cache'});}finally{clearTimeout(id);}
    let data;try{data=await response.json();}catch{throw Error(`Feed returned HTTP ${response.status}`);}
    if(!response.ok)throw Error(data.error||'Data unavailable');
    if(data.market!==market||data.timeframe!==tf||!Array.isArray(data.bars)||data.bars.length<25)throw Error('Incomplete provider candles');
    const valid=data.bars.every((b,i)=>Number.isFinite(b.time)&&b.open>0&&b.high>=Math.max(b.open,b.close)&&b.low<=Math.min(b.open,b.close)&&(i===0||b.time>data.bars[i-1].time));
    if(!valid)throw Error('Invalid/out-of-order provider candles');
    payload=data;seen=market+'/'+tf;hoverIndex=null;endOffset=0;view=Math.min(110,data.bars.length);redraw();
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
 $('loadChart').addEventListener('click',()=>refresh());
 $('researchChart').addEventListener('click',()=>{
  if(!payload||seen!==market+'/'+tf){status('Load the selected market and timeframe first.');return;}
  const bars=completeBars(payload.bars,tf);
  if(bars.length<100){status(`Only ${bars.length} complete bars; at least 100 needed.`);return;}
  onResearch({market,timeframe:tf,bars,source:`${payload.provider} · ${market} ${tf} · ${new Date(payload.fetchedAt).toISOString()}`});
 });
 canvas.addEventListener('mousemove',e=>{const r=canvas.getBoundingClientRect();const n=Math.min(payload?.bars.length||0,Math.max(22,Math.round(view))),bw=Math.max(1,(r.width-98)/n);hoverIndex=Math.floor((e.clientX-r.left-12)/bw);if(dragX!=null){const move=Math.round((dragX-e.clientX)/bw);if(move){endOffset=Math.min(Math.max(0,(payload?.bars.length||0)-n),Math.max(0,endOffset+move));dragX=e.clientX;}}redraw();});
 canvas.addEventListener('mouseleave',()=>{hoverIndex=null;dragX=null;redraw();});canvas.addEventListener('mousedown',e=>{dragX=e.clientX;});window.addEventListener('mouseup',()=>dragX=null);
 canvas.addEventListener('wheel',e=>{if(!payload)return;e.preventDefault();view=Math.min(payload.bars.length,Math.max(22,view*(e.deltaY>0?1.17:.85)));hoverIndex=null;endOffset=0;redraw();},{passive:false});
 new ResizeObserver(redraw).observe(chart);
 setLink();redraw();
 setInterval(()=>{if($('page-markets')?.classList.contains('active')&&payload&&!busy)refresh(false);},45000);
 return {select(m){setMarket(m);},refresh,redraw};
}
