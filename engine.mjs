// OPTIONX 200K deterministic OHLC signal-research engine. No broker connections.
export const SIGNALS=['SMA crossover','EMA crossover','RSI reversal','Donchian breakout','Bollinger rebound'];
export const FILTERS=['None','Trend direction','RSI regime','Volatility gate','4-bar momentum'];
export const EXITS=['Fixed SL + TP','Trailing after 1R','Breakeven after 1R','Timed exit'];
export const STOPS=[1,1.5,2,2.5];
export const REWARDS=[1,1.5,2,2.5,3];
export const PERIODS=[8,13,21,34,55];
export const BUFFERS=Array.from({length:20},(_,i)=>i);
export const TOTAL=SIGNALS.length*FILTERS.length*EXITS.length*STOPS.length*REWARDS.length*PERIODS.length*BUFFERS.length;
export function configAt(id){
  if(!Number.isInteger(id)||id<0||id>=TOTAL)throw Error('Strategy ID out of range');
  let n=id;const take=(a)=>{const v=n%a.length;n=Math.floor(n/a.length);return v;};
  const b=take(BUFFERS),p=take(PERIODS),r=take(REWARDS),s=take(STOPS),x=take(EXITS),f=take(FILTERS),g=take(SIGNALS);
  return {id:id+1,signal:g,filter:f,exit:x,stop:STOPS[s],rr:REWARDS[r],period:PERIODS[p],buffer:BUFFERS[b]};
}
export function parseCSV(raw){
  if(typeof raw!=='string'||raw.length>50_000_000)throw Error('CSV must be smaller than 50 MB');
  const lines=raw.replace(/^\uFEFF/,'').split(/\r?\n/).filter(x=>x.trim());
  if(lines.length<110)throw Error('At least 100 OHLC candles plus header are required');
  const delim=lines[0].includes('\t')?'\t':lines[0].includes(';')&&!lines[0].includes(',')?';':',';
  function split(line){const out=[];let v='',quote=false;for(let i=0;i<line.length;i++){const c=line[i];if(c==='"'){if(quote&&line[i+1]==='"'){v+='"';i++;}else quote=!quote;}else if(c===delim&&!quote){out.push(v.trim());v='';}else v+=c;}out.push(v.trim());return out;}
  const headers=split(lines[0]).map(s=>s.toLowerCase().replace(/[^a-z0-9]/g,''));
  const col=(names)=>headers.findIndex(v=>names.includes(v));
  const idx={time:col(['time','date','datetime','timestamp','tradetime','opentime']),open:col(['open','o']),high:col(['high','h']),low:col(['low','l']),close:col(['close','c']),volume:col(['volume','vol','v'])};
  if([idx.time,idx.open,idx.high,idx.low,idx.close].some(v=>v<0))throw Error('CSV headers must include time/date, open, high, low, close');
  const bars=[];let prev=-Infinity,invalid=0;
  for(let k=1;k<lines.length;k++){
    const a=split(lines[k]);const rawTime=a[idx.time];let t=/^\d{10,13}$/.test(rawTime)?Number(rawTime)*(rawTime.length===10?1000:1):Date.parse(rawTime);
    const o=Number(a[idx.open]),h=Number(a[idx.high]),l=Number(a[idx.low]),c=Number(a[idx.close]);
    if(!Number.isFinite(t)||![o,h,l,c].every(x=>Number.isFinite(x)&&x>0)||h<Math.max(o,c)||l>Math.min(o,c)||t<=prev){invalid++;continue;}
    bars.push({time:t,open:o,high:h,low:l,close:c,volume:idx.volume>=0?Number(a[idx.volume])||0:0});prev=t;
    if(bars.length>120000)throw Error('Maximum 120,000 bars per upload');
  }
  if(invalid)throw Error(`${invalid} invalid, duplicate or out-of-order OHLC rows. Please sort ascending and correct them.`);
  if(bars.length<100)throw Error('At least 100 valid candles are required');
  return bars;
}
function sma(v,n){const a=new Float64Array(v.length);a.fill(NaN);let sum=0;for(let i=0;i<v.length;i++){sum+=v[i];if(i>=n)sum-=v[i-n];if(i>=n-1)a[i]=sum/n;}return a;}
function ema(v,n){const a=new Float64Array(v.length);a.fill(NaN);let x=0;for(let i=0;i<v.length;i++){if(i===n-1){for(let j=0;j<n;j++)x+=v[j];x/=n;a[i]=x;}else if(i>=n){x+=(v[i]-x)*2/(n+1);a[i]=x;}}return a;}
function rsi(v,n){const a=new Float64Array(v.length);a.fill(NaN);let up=0,dn=0;for(let i=1;i<v.length;i++){const d=v[i]-v[i-1],u=Math.max(d,0),q=Math.max(-d,0);if(i<=n){up+=u;dn+=q;if(i===n){up/=n;dn/=n;a[i]=dn===0?100:100-100/(1+up/dn);}}else{up=(up*(n-1)+u)/n;dn=(dn*(n-1)+q)/n;a[i]=dn===0?100:100-100/(1+up/dn);}}return a;}
function atr(bars,n){const a=new Float64Array(bars.length);a.fill(NaN);let v=0;for(let i=1;i<bars.length;i++){const b=bars[i],tr=Math.max(b.high-b.low,Math.abs(b.high-bars[i-1].close),Math.abs(b.low-bars[i-1].close));if(i<=n){v+=tr;if(i===n){v/=n;a[i]=v;}}else{v=(v*(n-1)+tr)/n;a[i]=v;}}return a;}
export function prepare(bars){
  const c=Float64Array.from(bars,b=>b.close),features={};
  for(const p of PERIODS){
    const sFast=sma(c,p),sSlow=sma(c,2*p),eFast=ema(c,p),eSlow=ema(c,2*p),rs=rsi(c,p),at=atr(bars,p);
    const hi=new Float64Array(bars.length),lo=new Float64Array(bars.length),bu=new Float64Array(bars.length),bl=new Float64Array(bars.length);hi.fill(NaN);lo.fill(NaN);bu.fill(NaN);bl.fill(NaN);
    let sum=0,sum2=0;
    for(let i=0;i<bars.length;i++){
      const v=c[i];sum+=v;sum2+=v*v;if(i>=p){sum-=c[i-p];sum2-=c[i-p]*c[i-p];}
      if(i>=p-1){const m=sum/p,sd=Math.sqrt(Math.max(0,sum2/p-m*m));bu[i]=m+2*sd;bl[i]=m-2*sd;}
      if(i>=p){let h=-Infinity,l=Infinity;for(let j=i-p;j<i;j++){h=Math.max(h,bars[j].high);l=Math.min(l,bars[j].low);}hi[i]=h;lo[i]=l;}
    }
    features[p]={sFast,sSlow,eFast,eSlow,rs,at,hi,lo,bu,bl};
  }
  return features;
}
export function signalFor(bars,f,c,i){
  const v=bars[i].close,prev=bars[i-1].close;let dir=0;
  switch(c.signal){
    case 0: if(f.sFast[i-1]<=f.sSlow[i-1]&&f.sFast[i]>f.sSlow[i])dir=1;else if(f.sFast[i-1]>=f.sSlow[i-1]&&f.sFast[i]<f.sSlow[i])dir=-1;break;
    case 1: if(f.eFast[i-1]<=f.eSlow[i-1]&&f.eFast[i]>f.eSlow[i])dir=1;else if(f.eFast[i-1]>=f.eSlow[i-1]&&f.eFast[i]<f.eSlow[i])dir=-1;break;
    case 2: if(f.rs[i-1]<30&&f.rs[i]>=30)dir=1;else if(f.rs[i-1]>70&&f.rs[i]<=70)dir=-1;break;
    case 3: if(v>f.hi[i])dir=1;else if(v<f.lo[i])dir=-1;break;
    case 4: if(prev<f.bl[i-1]&&v>=f.bl[i])dir=1;else if(prev>f.bu[i-1]&&v<=f.bu[i])dir=-1;break;
  }
  if(!dir||Math.abs((v-prev)/prev)*10000<c.buffer)return 0;
  if(c.filter===1&&dir*(v-f.sSlow[i])<=0)return 0;
  if(c.filter===2&&dir*(f.rs[i]-50)<=0)return 0;
  if(c.filter===3&&f.at[i]/v<0.001)return 0;
  if(c.filter===4&&dir*(v-bars[i-4].close)<=0)return 0;
  return dir;
}
// Signalled only after bar i close, entered at next bar open; same-bar SL/TP collision assumes SL first.
export function runBacktest(bars,prepared,cfg,start,end,feesBps=4){
  if(!Number.isFinite(feesBps)||feesBps<0||feesBps>500)throw Error('Fees must be between 0 and 500 bps');
  const f=prepared[cfg.period];if(!f)throw Error('Missing indicator period');
  const from=Math.max(start,cfg.period*2+5),to=Math.min(end,bars.length);
  let pending=null,pos=null,net=0,peak=0,maxDD=0,trades=0,wins=0,winR=0,lossR=0,first=null,last=null;
  const finish=(price,idx)=>{
    const gross=(price-pos.entry)*pos.dir/pos.risk;
    const cost=((Math.abs(pos.entry)+Math.abs(price))*feesBps/10000)/pos.risk;
    const R=gross-cost;net+=R;trades++;if(R>0){wins++;winR+=R;}else lossR-=R;
    peak=Math.max(peak,net);maxDD=Math.max(maxDD,peak-net);
    if(first===null)first=bars[pos.i].time;last=bars[idx].time;pos=null;
  };
  for(let i=from;i<to;i++){
    const b=bars[i];let closed=false;
    if(pending){const dir=pending.dir,entry=b.open,at=pending.atr;pending=null;
      if(Number.isFinite(at)&&at>0&&entry>0){const risk=at*cfg.stop;pos={entry,dir,risk,stop:entry-dir*risk,target:entry+dir*risk*cfg.rr,i};}
    }
    if(pos){
      const s=pos.stop,t=pos.target,dir=pos.dir;
      const stopHit=dir>0?b.low<=s:b.high>=s;
      const targetHit=dir>0?b.high>=t:b.low<=t;
      if(stopHit){const gap=dir>0?Math.min(s,b.open):Math.max(s,b.open);finish(gap,i);closed=true;}
      else if(targetHit){finish(t,i);closed=true;}
      else if(cfg.exit===3&&i-pos.i+1>=cfg.period){finish(b.close,i);closed=true;}
      else if(i===to-1){finish(b.close,i);closed=true;}
      else if(cfg.exit===1||cfg.exit===2){
        const excursion=dir>0?b.high-pos.entry:pos.entry-b.low;
        if(excursion>=pos.risk){
          const newStop=cfg.exit===2?pos.entry:pos.entry+dir*Math.max(0,(excursion-pos.risk*.5));
          pos.stop=dir>0?Math.max(pos.stop,newStop):Math.min(pos.stop,newStop);
        }
      }
    }
    if(closed||pos||i>=to-2||!Number.isFinite(f.at[i])||!Number.isFinite(f.sSlow[i])||!Number.isFinite(f.sSlow[i-1])||!Number.isFinite(f.rs[i])||!Number.isFinite(f.rs[i-1]))continue;
    const dir=signalFor(bars,f,cfg,i);if(dir)pending={dir,atr:f.at[i]};
  }
  return {trades,wins,winRate:trades?wins*100/trades:null,netR:net,maxDrawdownR:maxDD,profitFactor:lossR===0?(winR>0?null:0):winR/lossR,first,last};
}
export function score(m){return m.trades<8||m.netR<=0?-1e9:(m.netR-0.75*m.maxDrawdownR)*Math.min(1,m.trades/25);}
