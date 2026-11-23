import {TOTAL,configAt,prepare,runBacktest,score} from './engine.mjs';
self.onmessage=async ({data})=>{
 if(data.type!=='scan')return;
 try{
  const {bars,limit,feesBps,depth}=data;
  const prep=prepare(bars),split=Math.floor(bars.length*.7);
  const trainStart=depth===0?0:Math.max(0,split-depth);
  let top=[],bestScore=-Infinity,viable=0;
  const started=performance.now();
  // 104729 is coprime to 200000, hence scanning all IDs visits all configurations once.
  for(let k=0;k<limit;k++){
   const id=(k*104729)%TOTAL,cfg=configAt(id);
   const metrics=runBacktest(bars,prep,cfg,trainStart,split,feesBps),val=score(metrics);
   if(val>-1e9){viable++;if(top.length<40||val>bestScore){top.push({config:cfg,train:metrics,score:val});top.sort((a,b)=>b.score-a.score);if(top.length>40)top.pop();bestScore=top.at(-1)?.score??-Infinity;}}
   if((k+1)%200===0||k+1===limit){self.postMessage({type:'progress',done:k+1,limit,viable,elapsed:(performance.now()-started)/1000});await new Promise(resolve=>setTimeout(resolve,0));}
  }
  top=top.map(v=>({...v,test:runBacktest(bars,prep,v.config,split,bars.length,feesBps)}));
  self.postMessage({type:'complete',top,done:limit,viable,elapsed:(performance.now()-started)/1000,trainBars:split-trainStart,testBars:bars.length-split,splitTime:bars[split]?.time||null,market:data.market,feesBps,depth,source:data.source});
 }catch(err){self.postMessage({type:'error',message:String(err?.message||err)});}
};
