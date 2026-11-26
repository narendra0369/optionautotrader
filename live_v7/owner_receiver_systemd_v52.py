"""Dedicated systemd entry point for OptionX owner control receiver.

Only loopback control-plane commands, never Angel broker orders.
The shared HMAC credential is injected privately by systemd LoadCredential.
"""
from __future__ import annotations

import os
from pathlib import Path
from uuid import UUID

from live_v7.aws_control_receiver_v48 import serve_local

def main() -> None:
    credentials=os.environ.get("CREDENTIALS_DIRECTORY")
    if not credentials:
        raise RuntimeError("SYSTEMD_CREDENTIALS_DIRECTORY_REQUIRED")
    key_file=Path(credentials)/"relay_key"
    if key_file.is_symlink() or not key_file.is_file():
        raise RuntimeError("RELAY_KEY_CREDENTIAL_REQUIRED")
    key=key_file.read_bytes().strip()
    if len(key)<32:
        raise RuntimeError("RELAY_KEY_TOO_SHORT")
    owner=str(UUID(os.environ["OPTIONX_OWNER_USER_ID"]))
    state=Path("/var/lib/optionx-v52-control")
    if state.is_symlink() or not state.is_dir():
        raise RuntimeError("CONTROL_PRIVATE_STATE_DIRECTORY_REQUIRED")
    serve_local(db_path=state/"owner-control.sqlite",
                activation_db_path=state/"activation.sqlite",
                owner_id=owner,key=key,port=8766)

if __name__=="__main__":
    main()
