#!/usr/bin/env python3
"""Local signed owner emergency STOP verification, prints no secret."""
from __future__ import annotations
from datetime import datetime, timezone
import json, os, secrets, urllib.request
from pathlib import Path
from uuid import UUID
from live_v7.signed_owner_commands_v48 import sign_from_trusted_gateway

def main():
    owner_file=Path("/etc/optionx-v52/receiver.env")
    key_file=Path("/etc/optionx-v52/owner-relay-hmac.key")
    env=dict(line.strip().split("=",1) for line in owner_file.read_text().splitlines() if "=" in line)
    owner=str(UUID(env["OPTIONX_OWNER_USER_ID"]))
    key=key_file.read_bytes().strip()
    envelope={"v":1,"owner":owner,"action":"EMERGENCY_STOP",
              "nonce":secrets.token_urlsafe(24),
              "issued_at":int(datetime.now(timezone.utc).timestamp())}
    sig=sign_from_trusted_gateway(envelope,key=key,owner_verified=True)
    req=urllib.request.Request("http://127.0.0.1:8766/v48/owner/control",
          data=json.dumps(envelope,sort_keys=True,separators=(",",":")).encode(),
          headers={"Content-Type":"application/json","X-OptionX-Signature":sig},
          method="POST")
    with urllib.request.urlopen(req,timeout=5) as r:
        result=json.load(r)
    if not (result.get("commandAccepted") is True and
            result.get("mode")=="STOPPED" and
            result.get("liveOrdersEnabled") is False):
        raise RuntimeError("OWNER_STOP_COMMAND_NOT_ACKNOWLEDGED")
    print("PASS: signed STOP accepted and persisted")
    print("PASS: liveOrdersEnabled=False")
    print("SIGNING_SECRET_NOT_PRINTED")
if __name__=="__main__":
    main()
