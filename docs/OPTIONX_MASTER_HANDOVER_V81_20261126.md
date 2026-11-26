# OPTIONX V81 WORKER ATTESTATION GATE — handover addendum (2026-11-26 IST)

**Previous handover:** `docs/OPTIONX_MASTER_HANDOVER_V80_20261126.md`, parent branch `optionx-v80-signed-pending-proof-and-master-handover-20261126`. All V80 successes retained. Do not restart/redo V80 from scratch.

## Actually APPLIED / VERIFIED in Supabase
- Migration `optionx_v81_independent_worker_attestation_gate` applied successfully.
- `optionx_private.v81_independent_worker_attestations` is a deny-by-default RLS table with NO direct INSERT for browser authenticated or service_role. It requires separate reviewer ID from owner, verified process+key custody, matching key fingerprint and 15-minute expiration. **0 attestations inserted**; do not fake the reviewer. A table row from a database admin still requires independent evidentiary verification; don't call it certified based only on a flag.
- Promotion trigger `v81_independent_worker_promotion_gate` rejects change from PENDING to VERIFIED without fresh matching reviewed attestation. Actual negative test executed: PENDING→VERIFIED correctly rejected and status remained PENDING.
- V79 VERIFIED worker key lookup and nonce consume functions now independently verify current V81 attestation on EVERY call, not solely status='VERIFIED'. V80 PENDING signed proof endpoint unchanged.
- Actual audit: 1 promotion trigger, 0 independent attestations, 1 PENDING key, 0 VERIFIED keys, 1 historical V80 proof, 0 order intents, 0 reservations, worker DB role NOLOGIN. browser/service_role cannot directly insert attestation.

## GitHub V81 host scripts (NOT YET RUN ON AWS)
- `scripts/optionx_v81_unprivileged_systemd_signed_proof.py` runs under non-root `optionx-executor`, requires a private signing key mounted via systemd `LoadCredential` plus root-controlled nonsecret owner UUID credential, creates new V80 pending-key proof and checks 200 first / 409 replay. It never sees broker credentials or requests trading APIs. The V78 service remains PrivateNetwork=yes.
- `scripts/run_optionx_v81_systemd_worker_proof.sh` is a non-invasive one-shot systemd-run harness that validates existing six services are active, creates only /etc/optionx-v81 root owner-binding file and /opt/optionx-v81 proof script, uses transient network-enabled process with NoNewPrivileges/ProtectSystem/etc. It **does not alter, enable, disable or restart** the six existing services and never changes the Postgres worker NOLOGIN flag.
- Source branch `optionx-v81-independent-attestation-gate-20261126`, private repo `narendra0369/optionautotrader`. It is NOT merged to main and NOT automatically deployed to AWS. Run from authenticated checkout or provide user a self-contained verified script, NEVER request GitHub credential, private Ed25519 key, or JWT in chat.

## What successful V81 host test proves — and what it does not
If a signed request from a systemd-run transient with User=optionx-executor succeeds, that proves credential hand-off to nonroot process and server-side key-ownership against registered key, with replay rejection. It DOES NOT provide cryptographic remote workload attestation, measured boot, hardware root of trust, independent reviewer approval or trade authorization. Root on the host could still impersonate the worker. Treat `process_identity_verified` as FALSE absent independent verifier evidence; leave table empty and worker PENDING.

## Next after host test
1. Obtain independent external workload/host provenance review that is truly distinct from owner and is bound to worker UUID + public key fingerprint. Establish expiry and revocation. Do not self-approve.
2. Design scoped Edge gateway and actual server-side authorized action binding; V79/V81 identity proof is not an order execution permit.
3. Review default-STOP state machine and V65 structural guard constraint in a separate non-prod environment; retain emergency STOP and owner explicit activation.
4. Controlled fills, SL-LIMIT, partial fills, cancel/replace, reconciliation and broker compliance tests only after separate approval; keep live BUY/SELL/CANCEL OFF.
5. Keep 15-min ATM option strategy, globally max 2 entries/day and user paper stepped risk tier; do not confuse paper risk with independent live policy.

## New chat starter
`Continue OPTIONX V81 using docs/OPTIONX_MASTER_HANDOVER_V81_20261126.md (this file) on branch optionx-v81-independent-attestation-gate-20261126. V80 AWS↔Supabase HTTP 200/409 completed; V81 database independent attestation promotion/read gate deployed; worker remains PENDING, 0 independent attestations and real orders OFF. Next run V81 temporary systemd LoadCredential signed proof AS optionx-executor, then independently review workload custody, no self-approval. Check current DB and original AWS services. Never request secrets.`

## V81 AWS first run blocker and safe fix (2026-11-26)
- Owner ran the exact previous V81 GitHub commit `f3f985ee44b382e4d36c11d87f2aae6d570c0f01` on AWS, git fetch/commit verification passed, transient unit ran as `optionx-executor`, but exited before signing with `V81_BLOCK: RuntimeError PRIVATE_CREDENTIAL_NOT_SCOPED_TO_EXECUTOR`.
- Root cause: Python script was over-strict about `LoadCredential` file owner and mode: systemd credential file ownership/mode may vary by systemd release and are subject to private credential mount directory, not identical to original root-only source file. No evidence of key compromise; actual mode is not verified. Do NOT chmod original AWS private key or switch executor to root.
- Revised Python proof checks `CREDENTIALS_DIRECTORY` under `/run/credentials/`, non-root executor euid, files with no symlinks, and effective read permission. The existing shell script checks original key root:0600, Ed25519 fingerprint and six services active. It runs a one-shot signed proof and replay check. GitHub source updated on V81 branch (look up HEAD after this handover update). FIRST V81 workload proof still PENDING; previous command did not reach HTTP 200/409.
- Do not put `set -e` at top-level of the interactive SSH session; wrap verification in a subshell `( set -e; ... )` so failure does not terminate the login shell.
