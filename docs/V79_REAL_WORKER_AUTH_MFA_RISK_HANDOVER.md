# OPTIONX V79 actual deployment 2026-11-26

## Deployed to actual Supabase project yghijfzwsvmzaffllszl

- V79 worker public-key registry, all browser direct writes and direct service-role registration revoked. No trusted keys registered.
- V79 reservation trigger on v65_reserved_day. Every positive increment must be by optionx_execution_worker DB principal, have owner guard explicitly unblocked (currently structurally impossible because of STOP CHECK), a fresh independent broker/day approved risk budget, and not exceed budget.
- V79B serializes per owner/day and limits reserved entries to **two TOTAL across both Angel and Delta**. Previously V65 had only per-broker limits.
- V79B replay nonce table, with service-role-only nonce-consumption RPC.
- V79C service-role-only verified public-key lookup.
- V79D owner-authenticated explicit staging risk review RPC, real Supabase AAL2 session/factor and <=5min verified challenge check; independently approved budget is mandatory; no action grants, no live order permits.
- V79E reservation trigger also requires fresh owner review **and** still-fresh matching auth.sessions/auth.mfa_factors AAL2 proof at the point of reservation.
- Edge Function optionx-v79-worker-identity deployed ACTIVE, JWT off intentionally to use its independent signed Ed25519 request body, only approved keys allowed, one-minute time window and anti-replay nonce, returns canReserve/canIssuePermit/canSendOrder/canCancelOrder=false.
- At verification: 1 verified factor; 1 active AAL2; zero public-worker identities, nonces, approved risk policies, owner risk reviews, trusted worker attestations, order intents, reservations; optionx_execution_worker rolcanlogin=false.

## AWS action PENDING
- Existing V78 service optionx-v78-executor-staging running as optionx-executor. V79 installer scripts/install_optionx_v79_aws_worker_identity.sh creates a private Ed25519 key (root 0600, never outputs private key), public PEM and stable UUID, uses transient systemd LoadCredential service as optionx-executor to sign and verify without network or real broker. It checks five existing production services remain active.
- User must run installer directly on original Ubuntu AWS host from a trusted branch or use an equivalent audited copy-paste script. No direct AWS SSH connection is available through these tools. Never request private key, OTP, session or broker secrets.
- Next: owner public key/worker_id registration PENDING, independent signature challenge proof, authorize VERIFIED only after verified identity mapping and secure bootstrapping, configure scoped egress, replace DB NOLOGIN direct access with strictly authenticated Edge gateway and scoped audited DB calls, complete STOP redesign and controlled broker lifecycle certification.
- V79 is REAL enforcement infrastructure but NOT live execution ready. Do not disable guard constraints, grant broad roles, start BUY/SELL/CANCEL or alter manual broker position.
