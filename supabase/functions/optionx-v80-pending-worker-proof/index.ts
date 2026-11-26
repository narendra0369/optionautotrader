// V80: pending worker Ed25519 proof of possession. NO worker approval.
// The response is not a broker credential, database login, trading permit or risk grant.
const H={"content-type":"application/json","cache-control":"no-store"};
function res(status:number,data:Record<string,unknown>){
 return new Response(JSON.stringify(data),{status,headers:H});
}
const UUID=/^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/;
function b64(input:string):Uint8Array{
 if(!/^(?:[A-Za-z0-9+/]{4})*(?:[A-Za-z0-9+/]{2}==|[A-Za-z0-9+/]{3}=)?$/.test(input)||input.length>8192)
   throw Error("BAD_BASE64");
 return Uint8Array.from(atob(input),c=>c.charCodeAt(0));
}
function spki(s:string):Uint8Array{
 const m=/^-----BEGIN PUBLIC KEY-----\s*([A-Za-z0-9+/=\s]+)\s*-----END PUBLIC KEY-----\s*$/.exec(s);
 if(!m)throw Error("BAD_PUBLIC_KEY");
 return b64(m[1].replace(/\s/g,""));
}
Deno.serve(async(req:Request)=>{
 if(req.method!=="POST")return res(405,{error:"POST_REQUIRED",approved:false});
 if(Number(req.headers.get("content-length")||0)>4096)return res(413,{error:"REQUEST_TOO_LARGE",approved:false});
 let d:Record<string,unknown>;
 try{
  const t=await req.text();if(t.length>4096)throw Error("LARGE");
  d=JSON.parse(t);
  if(!d||Array.isArray(d)||typeof d!=="object")throw Error("BAD_OBJECT");
 }catch(_){return res(400,{error:"INVALID_REQUEST",approved:false});}
 const {owner_id,worker_id,nonce,issued_at,signature}=d;
 if(typeof owner_id!=="string"||!UUID.test(owner_id)||
    typeof worker_id!=="string"||!UUID.test(worker_id)||
    typeof nonce!=="string"||!UUID.test(nonce)||
    typeof issued_at!=="string"||typeof signature!=="string")
   return res(400,{error:"INVALID_FIELDS",approved:false});
 const t=Date.parse(issued_at);
 if(!Number.isFinite(t)||new Date(t).toISOString()!==issued_at||
    Math.abs(Date.now()-t)>60000)
   return res(401,{error:"REQUEST_OUTSIDE_60_SECOND_WINDOW",approved:false});
 const root=Deno.env.get("SUPABASE_URL"),key=Deno.env.get("SUPABASE_SERVICE_ROLE_KEY");
 if(!root||!key)return res(503,{error:"SERVER_NOT_CONFIGURED",approved:false});
 const hdr={"content-type":"application/json","apikey":key,"authorization":"Bearer "+key};
 try{
   const found=await fetch(root+"/rest/v1/rpc/optionx_v80_pending_worker_key",{
    method:"POST",headers:hdr,
    body:JSON.stringify({p_owner:owner_id,p_worker:worker_id}),signal:AbortSignal.timeout(5000)});
   if(!found.ok)return res(503,{error:"REGISTRY_NOT_AVAILABLE",approved:false});
   const rows=await found.json();
   if(!Array.isArray(rows)||rows.length!==1||typeof rows[0].public_key_pem!=="string")
     return res(401,{error:"PENDING_WORKER_ID_NOT_FOUND",approved:false});
   const publicKey=await crypto.subtle.importKey("spki",spki(rows[0].public_key_pem),
      {name:"Ed25519"},false,["verify"]);
   const canonical="OPTIONX_V80_PENDING_PROOF\n"+owner_id+"\n"+worker_id+"\n"+nonce+"\n"+issued_at;
   const verified=await crypto.subtle.verify("Ed25519",publicKey,b64(signature),
       new TextEncoder().encode(canonical));
   if(!verified)return res(401,{error:"BAD_WORKER_SIGNATURE",approved:false});
   const insert=await fetch(root+"/rest/v1/rpc/optionx_v80_consume_pending_proof",{
    method:"POST",headers:hdr,
    body:JSON.stringify({p_owner:owner_id,p_worker:worker_id,p_nonce:nonce}),
    signal:AbortSignal.timeout(5000)});
   if(!insert.ok)return res(503,{error:"REPLAY_LEDGER_NOT_AVAILABLE",approved:false});
   const first=await insert.json();
   if(first!==true)return res(409,{error:"REPLAYED_OR_UNREGISTERED_NONCE",approved:false});
   return res(200,{status:"V80_PENDING_KEY_PROOF_VALID",
     signatureVerified:true,nonceAcceptedOnce:true,
     independentWorkerAttested:false,approved:false,
     canReserve:false,canIssuePermit:false,canSendOrder:false,canCancelOrder:false});
 }catch(_){
   return res(401,{error:"PENDING_PROOF_FAILED",approved:false,canSendOrder:false});
 }
});
