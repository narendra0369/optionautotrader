#!/usr/bin/env python3
"""OPTIONX V80 real AWS -> Supabase Ed25519 pending proof (NO trading).
Run with sudo python3 ... on original OPTIONX Lightsail host.
Reads identity privately from existing local protected files.
No DB credentials, OTP, broker tokens or BUY/SELL/CANCEL calls.
"""
from __future__ import annotations

import base64
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import tempfile
from datetime import datetime, timezone
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen
from uuid import UUID, uuid4

URL = "https://yghijfzwsvmzaffllszl.supabase.co/functions/v1/optionx-v80-pending-worker-proof"
EXPECTED_WORKER = "7cfbebfe-b3d3-406e-9766-e176d8f49272"
EXPECTED_PUBLIC_FINGERPRINT = "94fc2e18d81cd126b34a21261d542b06c918649f388cb553c1e051f4dcf1a4d6"
ROOT = Path("/etc/optionx-v79")
PRIVATE = ROOT / "worker_ed25519.key"
PUBLIC = ROOT / "worker_ed25519.public.pem"
WORKER_ID = ROOT / "worker_id"
OWNER_CONFIG = Path("/etc/optionx-v52/receiver.env")


def check_file(path: Path) -> None:
    if path.is_symlink() or not path.is_file():
        raise RuntimeError("MISSING_OR_UNSAFE_IDENTITY_FILE")
    if path.stat().st_uid != 0:
        raise RuntimeError("WORKER_IDENTITY_FILE_NOT_ROOT_OWNED")


def owner_uuid() -> str:
    check_file(OWNER_CONFIG)
    lines = OWNER_CONFIG.read_text(encoding="utf-8").splitlines()
    matches = [
        line.partition("=")[2].strip().strip('"').strip("'")
        for line in lines if line.startswith("OPTIONX_OWNER_USER_ID=")
    ]
    if len(matches) != 1:
        raise RuntimeError("OWNER_BOUND_CONFIGURATION_NOT_FOUND")
    return str(UUID(matches[0]))


def invoke(*args: str, output: Path | None = None) -> bytes:
    command = list(args)
    if output is not None:
        command.extend(("-out", str(output)))
    result = subprocess.run(command, stdout=subprocess.PIPE,
                            stderr=subprocess.DEVNULL, check=False, timeout=12)
    if result.returncode != 0:
        raise RuntimeError("OPENSSL_SIGNATURE_OPERATION_FAILED")
    return result.stdout


def send(payload: bytes) -> tuple[int, dict]:
    request = Request(URL, data=payload, method="POST",
        headers={"Content-Type": "application/json", "Accept": "application/json"})
    try:
        with urlopen(request, timeout=12) as response:
            status = response.status
            response_text = response.read(4096)
    except HTTPError as err:
        status = err.code
        response_text = err.read(4096)
    except URLError:
        raise RuntimeError("HTTPS_CONNECTION_FAILED") from None
    try:
        result = json.loads(response_text)
        if not isinstance(result, dict):
            raise ValueError()
    except ValueError:
        raise RuntimeError("NON_JSON_SERVER_RESPONSE") from None
    return status, result


def run() -> None:
    print("=== OPTIONX V80 REAL AWS SIGNED CHALLENGE ===", flush=True)
    if os.geteuid() != 0:
        raise RuntimeError("ROOT_REQUIRED_TO_READ_SYSTEMD_CREDENTIAL_SOURCE")
    for path in (PRIVATE, PUBLIC, WORKER_ID):
        check_file(path)
    if PRIVATE.stat().st_mode & 0o077:
        raise RuntimeError("PRIVATE_KEY_PERMISSIONS_TOO_BROAD")
    worker_id = str(UUID(WORKER_ID.read_text(encoding="ascii").strip()))
    if worker_id != EXPECTED_WORKER:
        raise RuntimeError("REGISTERED_WORKER_ID_MISMATCH")
    public_der = invoke("openssl", "pkey", "-pubin", "-in",
                        str(PUBLIC), "-outform", "DER")
    fingerprint = hashlib.sha256(public_der).hexdigest()
    if fingerprint != EXPECTED_PUBLIC_FINGERPRINT:
        raise RuntimeError("PUBLIC_KEY_FINGERPRINT_MISMATCH")
    print("PASS: REGISTERED_AWS_PUBLIC_KEY_MATCHES")
    owner_id = owner_uuid()
    nonce = str(uuid4())
    issued = datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")
    canonical = f"OPTIONX_V80_PENDING_PROOF\n{owner_id}\n{worker_id}\n{nonce}\n{issued}"
    with tempfile.TemporaryDirectory(prefix="optionx-v80-") as d:
        folder = Path(d)
        message = folder / "message"
        signature_file = folder / "signature"
        message.write_bytes(canonical.encode("utf-8"))
        invoke("openssl", "pkeyutl", "-sign", "-rawin",
               "-inkey", str(PRIVATE), "-in", str(message), output=signature_file)
        sig = base64.b64encode(signature_file.read_bytes()).decode("ascii")

    payload = json.dumps({"owner_id": owner_id, "worker_id": worker_id,
                          "nonce": nonce, "issued_at": issued, "signature": sig},
                         separators=(",", ":")).encode("utf-8")
    first_status, first = send(payload)
    print("FIRST_HTTP_STATUS:", first_status)
    print("FIRST_RESULT:", first.get("status", first.get("error", "UNKNOWN")))
    if not (first_status == 200 and first.get("signatureVerified") is True
            and first.get("nonceAcceptedOnce") is True
            and first.get("approved") is False
            and first.get("canSendOrder") is False):
        raise RuntimeError("REAL_SUPABASE_PENDING_SIGNATURE_PROOF_FAILED")
    print("PASS: REAL_ED25519_SIGNATURE_VERIFIED_BY_SUPABASE")
    second_status, second = send(payload)
    print("REPLAY_HTTP_STATUS:", second_status)
    print("REPLAY_RESULT:", second.get("error", "UNKNOWN"))
    if not (second_status == 409 and
            second.get("error") == "REPLAYED_OR_UNREGISTERED_NONCE"):
        raise RuntimeError("REAL_REPLAY_PROTECTION_FAILED")
    print("PASS: REPLAYED_NONCE_REJECTED")
    print("NO_PRIVATE_KEY_PRINTED; NO_DB_LOGIN; NO_BROKER_ORDER")
    print("WORKER_APPROVAL_PENDING; OWNER_STOP_REMAINS")
    print("V80_REAL_AWS_SUPABASE_SIGNED_PROOF_COMPLETE")


if __name__ == "__main__":
    try:
        run()
    except Exception as exc:
        print("V80_BLOCK:", str(exc))
        raise SystemExit(1) from None
