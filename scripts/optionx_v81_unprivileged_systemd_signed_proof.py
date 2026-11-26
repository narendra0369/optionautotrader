#!/usr/bin/env python3
"""V81 real one-shot unprivileged systemd LoadCredential -> Supabase proof.

A valid V81 proof demonstrates systemd ran this sign/POST as optionx-executor
with short-lived mounted key access, but DOES NOT independently attest
the Lightsail image/process or authorize broker execution.
"""
import base64
from datetime import datetime,timezone
import hashlib
import json
import os
from pathlib import Path
import subprocess
import tempfile
from urllib.request import Request,urlopen
from urllib.error import HTTPError
from uuid import UUID,uuid4

ENDPOINT="https://yghijfzwsvmzaffllszl.supabase.co/functions/v1/optionx-v80-pending-worker-proof"
EXPECTED_WORKER="7cfbebfe-b3d3-406e-9766-e176d8f49272"
EXPECTED_FINGERPRINT="94fc2e18d81cd126b34a21261d542b06c918649f388cb553c1e051f4dcf1a4d6"

def post(data):
 req=Request(ENDPOINT,data=data,method="POST",headers={"Content-Type":"application/json"})
 try:
  with urlopen(req,timeout=12) as r: return r.status,json.loads(r.read(4096))
 except HTTPError as e: return e.code,json.loads(e.read(4096))

def main():
 print("=== OPTIONX V81 UNPRIVILEGED SYSTEMD WORKLOAD SIGNED PROOF ===",flush=True)
 if os.geteuid()==0 or os.geteuid()!=int(os.environ.get("OPTIONX_EXPECTED_EXECUTOR_UID","-1")):
  raise RuntimeError("WRONG_PROCESS_IDENTITY")
 credentials=Path(os.environ.get("CREDENTIALS_DIRECTORY",""))
 if not credentials.is_dir() or not str(credentials).startswith("/run/credentials/"):
  raise RuntimeError("SYSTEMD_LOADCREDENTIAL_REQUIRED")
 private=credentials/"worker_ed25519"
 owner_file=credentials/"owner_uuid"
 worker_file=Path("/etc/optionx-v79/worker_id")
 pub=Path("/etc/optionx-v79/worker_ed25519.public.pem")
 for p in (private,owner_file,worker_file,pub):
  if p.is_symlink() or not p.is_file(): raise RuntimeError("MISSING_OR_UNSAFE_CREDENTIAL")
 if private.stat().st_uid!=os.geteuid() or (private.stat().st_mode&0o077):
  raise RuntimeError("PRIVATE_CREDENTIAL_NOT_SCOPED_TO_EXECUTOR")
 owner=str(UUID(owner_file.read_text(encoding="ascii").strip()))
 worker=str(UUID(worker_file.read_text(encoding="ascii").strip()))
 if worker!=EXPECTED_WORKER: raise RuntimeError("WORKER_ID_MISMATCH")
 der=subprocess.run(["/usr/bin/openssl","pkey","-pubin","-in",str(pub),"-outform","DER"],capture_output=True,check=True).stdout
 if hashlib.sha256(der).hexdigest()!=EXPECTED_FINGERPRINT:
  raise RuntimeError("PUBLIC_KEY_FINGERPRINT_CHANGED")
 print("PASS: UNPRIVILEGED_EXECUTOR_CREDENTIAL_MOUNTED")
 issued=datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00","Z")
 nonce=str(uuid4())
 message=f"OPTIONX_V80_PENDING_PROOF\n{owner}\n{worker}\n{nonce}\n{issued}".encode()
 with tempfile.TemporaryDirectory(prefix="optionx-v81-") as folder:
  m=Path(folder)/"message";sig=Path(folder)/"signature"
  m.write_bytes(message)
  subprocess.run(["/usr/bin/openssl","pkeyutl","-sign","-rawin","-inkey",
    str(private),"-in",str(m),"-out",str(sig)],
    stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,check=True)
  sig_b64=base64.b64encode(sig.read_bytes()).decode("ascii")
 payload=json.dumps({"owner_id":owner,"worker_id":worker,"nonce":nonce,
   "issued_at":issued,"signature":sig_b64},separators=(",",":")).encode()
 first,r=post(payload)
 print("SIGNED_REQUEST_HTTP:",first)
 print("SIGNED_REQUEST_STATUS:",r.get("status",r.get("error","UNKNOWN")))
 if first!=200 or r.get("signatureVerified") is not True or r.get("approved") is not False or r.get("canSendOrder") is not False:
  raise RuntimeError("SIGNED_WORKLOAD_PROOF_FAILED")
 print("PASS: SYSTEMD_EXECUTOR_SIGNED_REQUEST_ACCEPTED")
 replay,rr=post(payload)
 print("REPLAY_HTTP:",replay)
 if replay!=409 or rr.get("error")!="REPLAYED_OR_UNREGISTERED_NONCE":
  raise RuntimeError("SYSTEMD_EXECUTOR_REPLAY_GUARD_FAILED")
 print("PASS: SYSTEMD_EXECUTOR_NONCE_REPLAY_REJECTED")
 print("V81_SYSTEMD_WORKLOAD_PROOF_COMPLETE")
 print("INDEPENDENT_ATTESTATION_PENDING; WORKER_APPROVAL_PENDING; LIVE_ORDERS_OFF")

if __name__=="__main__":
 try:main()
 except Exception as exc:
  print("V81_BLOCK:",type(exc).__name__,str(exc))
  raise SystemExit(1) from None
