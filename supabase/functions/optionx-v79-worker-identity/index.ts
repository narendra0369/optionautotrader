// OPTIONX V79: narrow Ed25519 worker-identity handshake, NOT a trading gateway.
// Signed request only. No browser JWT or API key is a substitute.
// This endpoint has no broker routes and never issues a trade permit.
const jsonHeaders={"content-type":"application/json","cache-control":"no-store"};
function reply(status:number,data:Record<string,unknown>){
 return new Response(JSON.stringify(data),{status,headers:jsonHeaders});
}
const uuid=/^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/;
function decodeB64(text:string):Uint8Array{
 if(!/^[A-Za-z0-9+/]+={0,2}$/.test(text)||text.length>8192)throw Error("INVALID_BASE64");
 const raw=atob(text);
 return Uint8Array.from(raw,c=>c.charCodeAt(0));
}
function pemSpki(pem:string):Uint8Array{
 const m=/^-----BEGIN PUBLIC KEY-----\s*([A-Za-z0-9+/=\s]+)\s*-----END PUBLIC KEY-----\s*$/.exec(pem);
 if(!m)throw Error("INVALID_PUBLIC_KEY");
 return decodeB64(m[1].replace(/\s/g,""));
}
Deno.serve(async(req:Request)=>{
 if(req.method!=="POST")return reply(405,{error:"POST_REQUIRED",canSendOrder:false});
 if(Number(req.headers.get("content-length")||0)>4096)return reply(413,{error:"REQUEST_TOO_LARGE",canSendOrder:false});
 let body:Record<string,unknown>;
 try{
   const raw=await req.text();
   if(raw.length>4096)throw Error("REQUEST_TOO_LARGE");
   body=JSON.parse(raw);
   if(!body||Array.isArray(body)||typeof body!=="object")throw Error("INVALID_OBJECT");
 }catch(_){return reply(400,{error:"INVALID_REQUEST",canSendOrder:false});}
 const {owner_id,worker_id,nonce,issued_at,signature}=body;
 if(typeof owner_id!=="string"||!uuid.test(owner_id)||
    typeof worker_id!=="string"||!uuid.test(worker_id)||
    typeof nonce!=="string"||!uuid.test(nonce)||
    typeof issued_at!=="string"||
    typeof signature!=="string"){
   return reply(400,{error:"INVALID_IDENTITY_FIELDS",canSendOrder:false});
 }
 const issued=Date.parse(issued_at);
 if(!Number.isFinite(issued)||new Date(issued).toISOString()!==issued_at||
   Math.abs(Date.now()-issued)>60000){
   return reply(401,{error:"STALE_OR_NONCANONICAL_REQUEST",canSendOrder:false});
 }
 const url=Deno.env.get("SUPABASE_URL");
 const key=Deno.env.get("SUPABASE_SERVICE_ROLE_KEY");
 if(!url||!key)return reply(503,{error:"SERVICE_NOT_CONFIGURED",canSendOrder:false});
 const headers={
   "apikey":key,
   "authorization":"Bearer "+key,
   "content-type":"application/json",
   "accept":"application/json"
 };
 try{
   // Only independently verified and unexpired public keys are returned.
   const lookup=await fetch(url+"/rest/v1/rpc/optionx_v79_worker_verification_key",{
     method:"POST",headers,body:JSON.stringify({p_owner:owner_id,p_worker:worker_id}),
     signal:AbortSignal.timeout(4000)
   });
   if(!lookup.ok)return reply(503,{error:"IDENTITY_REGISTRY_UNAVAILABLE",canSendOrder:false});
   const keys=await lookup.json();
   if(!Array.isArray(keys)||keys.length!==1||
      typeof keys[0].public_key_pem!=="string"){
     return reply(401,{error:"WORKER_NOT_INDEPENDENTLY_APPROVED",canSendOrder:false});
   }
   const pub=await crypto.subtle.importKey("spki",pemSpki(keys[0].public_key_pem),
     {name:"Ed25519"},false,["verify"]);
   const message="OPTIONX_V79_WORKER_HANDSHAKE\n"+owner_id+"\n"+worker_id+
     "\n"+nonce+"\n"+issued_at;
   const ok=await crypto.subtle.verify("Ed25519",pub,
      decodeB64(signature),new TextEncoder().encode(message));
   if(!ok)return reply(401,{error:"INVALID_WORKER_SIGNATURE",canSendOrder:false});
   const consumed=await fetch(url+"/rest/v1/rpc/optionx_v79_consume_worker_nonce",{
     method:"POST",headers,
     body:JSON.stringify({p_owner:owner_id,p_worker:worker_id,p_nonce:nonce}),
     signal:AbortSignal.timeout(4000)
   });
   if(!consumed.ok)return reply(503,{error:"NONCE_STORE_UNAVAILABLE",canSendOrder:false});
   const accepted=await consumed.json();
   if(accepted!==true)return reply(409,{error:"DUPLICATE_OR_UNAPPROVED_WORKER_NONCE",canSendOrder:false});
   return reply(200,{
     scope:"V79_SIGNED_IDENTITY_ONLY",
     authenticatedWorker:true,
     canReserve:false,canIssuePermit:false,canSendOrder:false,canCancelOrder:false
   });
 }catch(_){
   // Do not log private signatures, raw requests, public keys or role credentials.
   return reply(401,{error:"WORKER_AUTHENTICATION_FAILED",canSendOrder:false});
 }
});
