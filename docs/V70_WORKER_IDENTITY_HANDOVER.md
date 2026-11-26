# OptionX V70 — dedicated worker identity staged, NOT MFA verified

Date: 2026-11-26

## Applied to actual Supabase PostgreSQL
Project `yghijfzwsvmzaffllszl`, schema `optionx_private`.
Migration: `optionx_v70_staged_nologin_worker_identity`.
Created role `optionx_execution_worker` with NOLOGIN, NOINHERIT, NOSUPERUSER, NOCREATEROLE, NOCREATEDB, NOREPLICATION; revoked schema/table/function rights. Database readback:
- role exists; canLogin=false, super=false, canCreateRole=false, canCreateDb=false, canReplicate=false.
- schema usage=false, V65 execute=false, V69 execute=false, order_intents insert=false.
- No password, JWT, TOTP, MFA evidence, credentials, network rights, risk reservations, order dispatch, or STOP changes.

## Important
The existence of a PostgreSQL role does not authenticate an AWS workload. Do NOT set LOGIN or GRANT execute until an independently verified AWS workload identity and secure secret-delivery / rotation / audit plan are approved. Keep session_user checking but do not treat it alone as workload attestation. Supabase owner MFA must be server-verified fresh AAL2 and bound to exact owner/session/action; an arbitrary UI flag is NOT evidence. Do not print or upload secrets.

## Next steps (not yet complete)
1. AWS local read-only check: service account `optionx` and all five systemd unit User=, Group=, ExecStart=; identify a separate non-networking dedicated issuer worker. Never restart existing live services merely for this audit.
2. Independent per-workload identity using trusted instance/IAM attestation (or short-lived managed credentials), audited, with least privilege and no public order routes. Bind identity to DB principal through reviewed auth broker.
3. Separate owner MFA challenge verified against trusted Supabase Auth session (AAL2 with recent auth_time), replay protection and audited owner intent. Do not enable real permits on MFA alone.
4. Independently verified broker write entitlement, IP whitelist and risk approval; keep `engine_guard` default deny until production design independently reviewed.
5. Safe isolated QA positive transaction and operational restart/outage tests. V66–V68 prior QA tests already PASS, do not repeat blindly.

## Current certification
V70 principal scaffold PASS; AWS identity bound = NO; MFA independently verified = NO; V65 positive production reservation = NO; real orders = OFF.
