# OPTIONX V82 — independent provenance review and read-only authorization design
Date: 2026-11-26 IST
Status: DESIGN ONLY / NO PRODUCTION DEPLOYMENT / NO TRADING AUTHORIZATION
Parent: optionx-v81-independent-attestation-gate-20261126

## Verified starting point
- V81 AWS one-shot systemd LoadCredential signed proof succeeded as non-root optionx-executor: HTTP 200, identical nonce replay HTTP 409.
- Six original services remained active. Real BUY/SELL/CANCEL OFF.
- V81 recorded 0 independent attestations, 1 PENDING key, 0 VERIFIED keys, 0 order intents and 0 reservations; worker DB role NOLOGIN.
- V81 proves credential handoff and key possession, not cryptographic remote process identity, host trust, independent human review, or broker authorization.
- Do not rerun completed V80/V81 proof simply to progress.

## Stop/go invariants
1. All real-money order placements, cancellations, modifications, and order intents remain blocked (default STOP) until separately authorized, tested, compliant, and owner-enabled. This branch cannot authorize trades.
2. Existing six services and AWS systemd units must not be restarted, stopped, or modified by V82 preparation.
3. No bypass of V65 structural guards, V81 attestation expiry, RLS, key status, owner separation, or 15-minute freshness.
4. Reviewer must be genuinely independent of owner, operator and host root; a database row or boolean cannot prove independence.
5. No secret values, Ed25519 private keys, broker credentials, access tokens, or personal identifying information in repository, CI logs or chat.
6. Preserve 15-minute ATM strategy, global maximum two entries per day and the existing stepped PAPER risk tier; no equivalence to live-order authorization.

## Threat model
- AWS root or host admin can impersonate local process, read ordinary mounted credentials, alter scripts, and falsify self-reported process metadata. A transient systemd-run proof alone does NOT attest remote image or boot state.
- A stolen signing key can produce signatures until revoked/expired; reject stale signatures/nonces and rotate keys under documented custody.
- Owner/operator self-approval or service_role SQL insertion is not independent attestation.
- Replayed request, mismatched worker UUID, public-key fingerprint, time window or reviewer identity must fail closed.
- Network errors, missing reviewer evidence, revocation lookup errors, clock drift, or ambiguous policy => STOP.

## Independent verification evidence bundle (never store secrets)
External verifier should obtain evidence outside operator-controlled claims:
- Verifier organization, named accountable reviewer, separation-of-duties record and conflict declaration.
- Worker UUID, public-key fingerprint, AWS account/instance identity, AMI/image digest, deployment source commit and verified build artifact digest.
- Hardware-backed or independently validated workload provenance, measurement chain and trust anchor where available. If not available, explicitly mark process_identity_verified=false.
- Evidence acquisition time, nonce/challenge, trusted verifier signature, issuer key identifier, expiry <= 15 minutes where V81 expects it, and revocation URL/mechanism.
- Verification report signed by reviewer, reproducible check commands, hashes and tamper-evident evidence pointers, not a manually set TRUE.
- Independent out-of-band authorization of reviewer enrollment and revocation (two-person control).

## Proposed read-only scoped gateway contract (DESIGN, NOT DEPLOYED)
- POST /v82/read-only/worker-status: owner-authenticated caller; returns minimum worker status and attestation freshness; no private key details.
- POST /v82/read-only/policy-check: accepted action scopes ONLY status.read and diagnostics.read; reject order.*, broker.*, risk.write, credential.write, stop.clear.
- Use authenticated owner identity plus independent worker binding, active nonce, short TTL (<= 60 seconds) and mandatory server-side policy check on EVERY call.
- Require server-side STOP gate. Emergency STOP overrides ALL scopes; no implied permission from key possession or an approved proof alone.
- Rate limit and structured audit events with request_id, actor_id hash, scope, decision, reason and time; no access tokens or credentials.
- CORS allowlist only; reject wildcard origin for authenticated data; HTTP 403 for denied scope and 503 if required evidence unavailable.
- A gateway must never call broker endpoints, modify DB worker state, or create an order intent in V82.

## Acceptance tests (nonproduction, deny-first)
- status.read while STOP active: allow only explicitly safe diagnostics if owner authenticated and policy permits.
- order.place, order.cancel, broker.call, stop.clear, key.promote: always DENY.
- Unknown scope, null/missing owner, expired proof, stale attestation, revoked reviewer, mismatched key fingerprint, owner==reviewer: DENY.
- Duplicate nonce: DENY; expiry and clock-skew boundary: DENY.
- Broker credentials missing: no crash and no fallback.
- Network/DB outage: DENY and return sanitized error.
- Verify no live API route or database order intent was called in the entire suite.

## V82 operational sequence
1. Validate branch commit and source diffs without deployment.
2. Arrange an actual independent external reviewer and provenance mechanism; capture report separately from AWS operator and source repo.
3. Re-check original AWS six services and read-only database state using authorized project access. Never paste secrets.
4. Develop gateway on a separate non-production target with mock data and unit tests, then peer review.
5. Only after independent evidence and explicit separate authorization should a later version consider production read-only deploy.
6. Real-money trading is OUT OF SCOPE.

## Known blocker
The connected Supabase listing in this ChatGPT session did not identify the OPTIONX project (only unrelated projects were shown). Do not use any unrelated database, infer an OPTIONX project ID, or assert current database state from historical handover. Current AWS state likewise cannot be claimed without an authorized AWS verification.

## Rollback
Nothing in this V82 document changes AWS, Supabase, deployed Edge Functions, order routes, credentials or broker state. Delete this development branch to discard this design if not accepted.
