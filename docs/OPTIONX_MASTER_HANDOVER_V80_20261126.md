# OPTIONX MASTER HANDOVER — V80 (2026-11-26 IST)

**PROJECT:** OPTIONX AI Trader / OPTIONX Strategy Lab (owner-only system), NIFTY, BANKNIFTY 15-minute ATM options, BTC/Delta planned. User wants Android+Windows, 200,000 strategy research, paper auto, future real broker auto execution; strict daily two-trade and loss controls.

**PRIMARY INVARIANT:** Owner STOP / no new real order permits; broker BUY/SELL/CANCEL DISABLED. NEVER alter manually purchased broker position. Never ask for/share private signing key, passwords, TOTP, Supabase service-role key or AWS secrets. No ZELQORIS marketplace changes. Do not present a GitHub PR as deployed production code.

## READ THIS FIRST IN A NEW CHAT
Do not rebuild/reinstall from scratch. Look up:
- This file: `docs/OPTIONX_MASTER_HANDOVER_V80_20261126.md` on GitHub branch `optionx-v80-signed-pending-proof-and-master-handover-20261126`.
- GitHub repository **private**: `narendra0369/optionautotrader`, default branch `main` (do NOT assume it contains V79 or V80). Earlier V79 draft PR #64; V80 new branch/PR. Branches are chained; many PRs unmerged.
- Supabase project `yghijfzwsvmzaffllszl` (schema `optionx_private`). Work only inside OPTIONX schema or narrowly named `public.optionx_vxx` RPCs.
- Render workspace `tea-dc0kcqss728c73ahvigg`. V7 frontend staging `https://optionx-v7-frontend-test-staging.onrender.com/` on branch `optionx-live-prep-v7-20261124`, autoDeploy OFF.
- AWS Lightsail Ubuntu host: original account `ubuntu`, hostname `ip-172-26-11-85`, working code base `/opt/optionx-v52`. IP known from past session: `43.204.246.235`; do not assume it has remained unchanged. There is NO direct AWS SSH connector in ChatGPT: operator pastes Ubuntu scripts and shares output. AWS account numeric ID must not be exposed unnecessarily.
- Project-specific `optionx` OS user uid 999 and separate `optionx-executor` uid 995. AWS Lightsail instance-role identity verified in V71, but this alone is not independent workload-specific attestation.

## CURRENT LIVE, ACTUALLY VERIFIED (not hypothetical)
1. Supabase Auth owner setup: **1 verified Google Authenticator TOTP factor**, **1 active AAL2 session** as of 2026-11-26 verification. User's website displayed `current login MFA verified (AAL2)`. This historical session is NOT automatically a fresh five-minute approval for a future trade.
2. Five original systemd services were active on AWS at V77/V78/V79 user-supplied terminal audits, each as `optionx` with PrivateTmp=yes, ProtectSystem=strict, NoNewPrivileges=yes:
   `optionx-market-api`, `optionx-owner-receiver`, `optionx-paper-health-watchdog`, `optionx-v54-paper-worker`, `optionx-v58-recovery-observer`. They were NOT restarted by V78 or V79 scripts.
3. V78 isolated account `optionx-executor` (uid 995, gid 986) and `optionx-v78-executor-staging` service ACTIVE on AWS as reported; PrivateNetwork=yes, IPAddressDeny=all, strict filesystem, no new privileges. This service is deliberately deny-only and has NO broker or database connection; not a live execution engine.
4. V79 AWS Ed25519 key generated at `/etc/optionx-v79/worker_ed25519.key` (private, root 0600; never export), corresponding public PEM `/etc/optionx-v79/worker_ed25519.public.pem`. Stable public worker ID `7cfbebfe-b3d3-406e-9766-e176d8f49272`; DER public key fingerprint SHA256 `94fc2e18d81cd126b34a21261d542b06c918649f388cb553c1e051f4dcf1a4d6`. User's AWS V79 output: `Signature Verified Successfully`, `PASS: V79_WORKER_ED25519_SIGNATURE`, `PASS: FIVE_EXISTING_SERVICES_ACTIVE`. The secret key was NOT sent to ChatGPT.
5. The AWS public key is **actually inserted** in Supabase `optionx_private.v79_worker_public_identity` for exactly one owner with a verified AAL2 session, state **PENDING**. Approved/VERIFIED worker count is 0. This is registration, NOT independent workload approval.
6. Actual Supabase applied migrations confirmed through Supabase list_migrations:
   `optionx_v64_additive_staging_fencing_and_risk_reservations`,
   `optionx_v65_atomic_reservation_staging`,
   `optionx_v69_readonly_recovery_preflight`,
   `optionx_v70_staged_nologin_worker_identity`,
   `optionx_v72_auth_mfa_diagnostic`,
   `optionx_v79_worker_key_registry_and_risk_guard`,
   `optionx_v79b_cross_broker_limit_and_signed_nonces`,
   `optionx_v79c_service_only_worker_pubkey_lookup`,
   `optionx_v79d_fresh_owner_mfa_risk_review`,
   `optionx_v79e_strict_mfa_guard_for_risk_increase`,
   `optionx_v80_pending_signed_challenge_proof` (confirm latest before acting).
7. V79 enforcement: on `v65_reserved_day` positive increments, dedicated DB principal check, owner STOP/guard, fresh independently approved risk budget, owner MFA-reviewed budget + recent real Auth TOTP session, global 2 reserved entries/day **across brokers** under advisory lock. Specific V65 base function still has own per-broker cap. Owner-reviewed risk RPC does NOT issue permits. Revoked direct browser/service_role worker identity writes and only allowed narrowly scoped server-only lookup/nonce RPCs.
8. V79 `optionx-v79-worker-identity` Supabase Edge Function ACTIVE; checks independently VERIFIED keys only, Ed25519 signature, <=60 sec timestamp and nonce once, returns canReserve/canIssuePermit/canSendOrder/canCancelOrder=false. Since registration PENDING, this route correctly denies access.
9. V80 `optionx-v80-pending-worker-proof` Supabase Edge Function ACTIVE with verify_jwt=false intentionally because it authenticates independently using signed body. It looks up only the registered PENDING public key, verifies Ed25519 signature over a strict canonical message, checks timestamp within 60 sec, consumes unique nonce via service_role-only RPC, returns `signatureVerified=true`, `nonceAcceptedOnce=true`, `approved=false`, and ALL order permissions FALSE. It does NOT promote registration. V80 migration applied.
10. Database last read-only audit at V80: 1 pending worker key; 0 approved; **0 successful pending proofs** (AWS handshake not run yet), 0 approved nonces; 0 order intents, 0 risk reservations; `optionx_execution_worker` Postgres role still NOLOGIN; 1 verified MFA factor; browser cannot invoke private nonce consumption.
11. Render OptionX services:
   - `optionx-v7-frontend-test-staging`, branch `optionx-live-prep-v7-20261124`, auto-deploy OFF. Owner Google Authenticator was added and user successfully completed AAL2. Earlier accidental inline QR JS leak was corrected by deploying a hotfix, do not reintroduce inline QR vendor JS or expose keys; existing MFA setup must not be repeated.
   - `optionx-v8-mobile-paper-staging`, branch `optionx-angel-aws-pilot-20261124`, auto-deploy OFF.
   - `optionx-v7-offline-test-staging`, branch `optionx-live-prep-v7-20261124`, auto-deploy OFF.
   - `optionx-market-feed` and `optionx-200k-strategy-lab` remain on `optionx-200k-strategy-lab-20261123`, auto-deploy ON; may differ from V79/V80 draft branch. DO NOT treat all services as having V80 source.

## CURRENT TASK — DO THIS NEXT, NO NEED TO ASK USER TO EXPLAIN HISTORY
**Complete real V80 AWS -> Supabase pending-key signed proof.** Script stored in same GitHub branch:
`scripts/optionx_v80_real_aws_supabase_signed_proof.py`.
Expected environment: original AWS Ubuntu, `sudo python3`, private/public identity files in `/etc/optionx-v79/`, owner-bound UUID read privately from `/etc/optionx-v52/receiver.env` (do not echo it).
The script signs:
`OPTIONX_V80_PENDING_PROOF\\n{owner_uuid}\\n{worker_uuid}\\n{nonce_uuid}\\n{issued_at_ISO8601_millis_Z}`
using Ed25519 private key kept on AWS. It POSTs JSON to:
`https://yghijfzwsvmzaffllszl.supabase.co/functions/v1/optionx-v80-pending-worker-proof`.
Expected first request HTTP 200 and `V80_PENDING_KEY_PROOF_VALID`, repeat identical signed JSON HTTP 409 and `REPLAYED_OR_UNREGISTERED_NONCE`.
Server records nonce ONLY on successful signature. Absolutely NO order, risk approval or worker promotion.
Since repository is PRIVATE, anonymous `curl raw.githubusercontent.com` for the script will NOT work. Give user a complete self-contained pasteable Ubuntu heredoc, or use an approved authenticated GitHub checkout. Do not ask user to paste private key/TOTP/token.

## BLOCKERS AFTER V80 SIGNED PROOF
1. Workload-specific identity proof beyond possession of key: machine role alone does not attest to `optionx-executor`; require independent process/host trust, key custody/rotation, approval, short-lived credentials.
2. Independently controlled registration approval from PENDING -> VERIFIED only after audited proof; do not self-promote to pass.
3. DB `optionx_execution_worker` is NOLOGIN and ungranted; choose a genuinely scoped, server-to-DB model (Edge gateway with limited RPCs or independent short-lived principal). Do not grant unrestricted LOGIN, service role access or direct table INSERT merely to satisfy test.
4. **Structural STOP design conflict:** engine_guard has CHECK(`new_entries_blocked=true`) and states STOPPED/RESET_REQUESTED/REVIEW_REQUIRED; V65 requires `new_entries_blocked=false` to reserve. Do not drop guard constraint casually. Plan owner-approved lifecycle transitions in a separate audited migration with a hard emergency STOP and state machine tests.
5. Approved risk policy and trusted-worker attestations 0; no fresh owner action review; broker position/risk snapshot not recent. New V79 real MFA + cross-broker day limit checks are deployed, but authorized positive path not certified.
6. Market and broker integration: Angel One read-only authentication tested earlier; official algo/static IP compliance, executable option quotes, broker order idempotency/fills/partial fills, protective SL-LIMIT, stop/target cancellation and recovery unverified. Delta and Stoxkart user wishes are future capabilities, not certified production order adapters.
7. Failure injection: isolated AWS transient restart QA V68 passed; NOT a genuine production outage or worker crash lifecycle certification. Manual broker position (historical NIFTY 29DEC26 CE, 65 qty in V29 output) was owner-managed and must never be modified by automated recovery.
8. Explicit final human approval after passing certification; real BUY/SELL/CANCEL remain OFF.
9. Preserve 15m strategy focus, default RR 1:3 for strategy research, 2 trades/day, user-specific stepped paper risk tier (start ₹30k, +1 lot per ₹40k, ₹300/lot risk, ₹600/lot target/daily loss), existing approved minimal premium UI; do not confuse virtual paper risk with actual real-money risk policy.

## PROOF VS CLAIM RULES
- `GitHub file created` != `merged to main` != `Render deployed` != `AWS installed` != `production certified`.
- Supabase migrations above ARE actually applied; V80 pending endpoint IS ACTIVE.
- AWS V79 signing proof is based on user-pasted terminal output, not our own SSH.
- V80 signed AWS -> Supabase roundtrip is NOT YET COMPLETED. Do not claim PASS before corresponding HTTP 200+409 and DB nonce evidence.
- Edge function "verify_jwt=false" does NOT grant auth; request authentication is Ed25519 signature and pending registry key lookup.
- Everything is owner only; never modify ZELQORIS marketplace or unrelated schemas.

## HANDOFF TO THE NEXT CHAT, COPY-PASTE STARTER
`Continue OPTIONX from docs/OPTIONX_MASTER_HANDOVER_V80_20261126.md in private GitHub repo narendra0369/optionautotrader on branch optionx-v80-signed-pending-proof-and-master-handover-20261126. First finish V80 real AWS→Supabase Ed25519 pending worker challenge-response (HTTP 200 then replay HTTP 409) using the stored AWS key; never request secrets, never permit live orders, preserve Owner STOP and manual position. Then plan independent worker attestation, scoped DB access and guarded STOP redesign. Check current Supabase actual state before taking actions.`
