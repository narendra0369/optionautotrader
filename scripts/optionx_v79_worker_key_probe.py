#!/usr/bin/env python3
"""Proof of isolated worker-owned systemd credential. Never prints secrets."""
import os
import subprocess
import tempfile
from pathlib import Path

cred_dir = os.environ.get("CREDENTIALS_DIRECTORY", "")
if not cred_dir:
    raise SystemExit("BLOCK: SYSTEMD_CREDENTIALS_DIRECTORY_MISSING")
private_key = Path(cred_dir) / "worker_ed25519"
public_key = Path("/etc/optionx-v79/worker_ed25519.public.pem")
if not private_key.is_file() or not public_key.is_file():
    raise SystemExit("BLOCK: ATTESTATION_KEY_MISSING")
if os.geteuid() == 0:
    raise SystemExit("BLOCK: MUST_RUN_AS_UNPRIVILEGED_WORKER")
with tempfile.TemporaryDirectory(prefix="optionx-v79-") as d:
    challenge = Path(d)/"challenge"
    signature = Path(d)/"signature"
    challenge.write_bytes(os.urandom(32))
    sign = subprocess.run(["/usr/bin/openssl","pkeyutl","-sign","-rawin",
                           "-inkey",str(private_key),"-in",str(challenge),
                           "-out",str(signature)],
                          capture_output=True,check=False)
    if sign.returncode:
        raise SystemExit("BLOCK: CREDENTIAL_SIGNING_FAILED")
    verify = subprocess.run(["/usr/bin/openssl","pkeyutl","-verify","-rawin",
                             "-pubin","-inkey",str(public_key),
                             "-in",str(challenge),"-sigfile",str(signature)],
                            capture_output=True,check=False)
    if verify.returncode:
        raise SystemExit("BLOCK: CREDENTIAL_SIGNATURE_VERIFICATION_FAILED")
print("PASS: V79_ISOLATED_WORKER_ED25519_SIGN_VERIFY")
print("NO_PRIVATE_KEY_EXPORTED")
print("NO_DB_CONNECTION_NO_BROKER_ORDERS")
