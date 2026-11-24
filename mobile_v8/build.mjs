import fs from 'node:fs';
import path from 'node:path';
import zlib from 'node:zlib';
import {fileURLToPath} from 'node:url';
const base=path.dirname(fileURLToPath(import.meta.url));
const dist=path.join(base,'dist');
fs.mkdirSync(dist,{recursive:true});
for(const f of ['index.html','styles.css','app.js','manifest.webmanifest','service-worker.js']){
  fs.copyFileSync(path.join(base,f),path.join(dist,f));
}
fs.mkdirSync(path.join(dist,'icons'),{recursive:true});
const crcTable=new Uint32Array(256);
for(let n=0;n<256;n++){let x=n;for(let k=0;k<8;k++)x=(x&1)?0xedb88320^(x>>>1):(x>>>1);crcTable[n]=x>>>0;}
function crc32(buf){let x=0xffffffff;for(const byte of buf)x=crcTable[(x^byte)&255]^(x>>>8);return (x^0xffffffff)>>>0;}
function chunk(tag,data){
  const size=Buffer.alloc(4);size.writeUInt32BE(data.length);
  const type=Buffer.from(tag,'ascii');const tail=Buffer.alloc(4);
  tail.writeUInt32BE(crc32(Buffer.concat([type,data])));
  return Buffer.concat([size,type,data,tail]);
}
function icon(n){
  const buffer=Buffer.alloc((n*4+1)*n);
  const navy=[11,17,27,255],slate=[27,38,54,255],gold=[216,189,134,255];
  for(let y=0;y<n;y++){
    buffer[y*(n*4+1)]=0;
    for(let x=0;x<n;x++){
      const u=x/n,v=y/n;
      let col=navy;
      const a=Math.abs(u-.5),b=Math.abs(v-.5);
      if(a<.37&&b<.37)col=slate;
      if(a<.37&&b<.37&&(a>.341||b>.341))col=gold;
      if(u>.29&&u<.71&&v>.29&&v<.71&&(Math.abs(u-v)<.044||Math.abs(u+v-1)<.044))col=gold;
      const loc=y*(n*4+1)+1+x*4;
      for(let i=0;i<4;i++)buffer[loc+i]=col[i];
    }
  }
  const ihdr=Buffer.alloc(13);ihdr.writeUInt32BE(n,0);ihdr.writeUInt32BE(n,4);ihdr[8]=8;ihdr[9]=6;
  return Buffer.concat([Buffer.from([137,80,78,71,13,10,26,10]),
    chunk('IHDR',ihdr),chunk('IDAT',zlib.deflateSync(buffer,{level:9})),chunk('IEND',Buffer.alloc(0))]);
}
for(const n of [192,512])fs.writeFileSync(path.join(dist,'icons','icon-'+n+'.png'),icon(n));
console.log('OPTIONX_PUBLIC_PWA_BUILD_PASS: 8 mobile screens, public HTTPS research feeds, icons and offline shell');
