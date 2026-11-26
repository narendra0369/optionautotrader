# OPTIONX V65 — Real PostgreSQL gated atomic reservation handover
Date: 2026-11-26

## Verified on actual Supabase project
Project `yghijfzwsvmzaffllszl`, schema `optionx_private`.

Migration `optionx_v65_atomic_reservation_staging` successfully applied.
- Created `v65_approved_risk_policy`, `v65_trusted_worker`, `v65_reserved_day`. All RLS-enabled, unseeded, and not available to anon/authenticated browser roles.
- Created `v65_atomic_reserve_staging`, SECURITY INVOKER, not granted to anon, authenticated, or service_role.
- Procedure is designed to lock per-owner/broker/day, confirm worker DB role, live lease, guard, independent worker attestation and risk policy, fresh risk and position data, prevent duplicate intent, enforce 2 entries and approved risk budget, then atomically persist `order_intents`, `v64_risk_reservations`, and `v65_reserved_day` in a single PostgreSQL transaction.
- It cannot sign, mint a permit, dispatch orders, or cancel positions.
- **Critically, required worker database principal is NOT provisioned. `engine_guard` schema enforces `new_entries_blocked=true` and is empty: all reservations are intentionally denied. Do not work around this.**
- Actual Supabase call under untrusted `postgres` session: `WORKER_DB_ROLE_NOT_ATTESTED`, rejected.
- Real PostgreSQL rollback test using exception subtransaction: PASS, no mutation.
- Function permission readback: anon=false, authenticated=false, service_role=false, postgres=true.
- Readback following negative probes: owner guard 0, worker attestations 0, approved risk policies 0, day counters 0, intents 0, risk reservations 0.

## NOT YET VERIFIED OR CERTIFIED
- No successfully committed positive-path atomic reservation through an independently authenticated execution worker. Code is **not** certified for production use.
- No real two-client concurrent transaction race/load test, DB outage/restart or AWS reconnect/recovery test (negative-path rollback only).
- No independently authenticated worker principal/workload-to-DB identity bound to AWS.
- No real independent MFA, whitelisting, broker WRITE entitlement or algo approval.
- Existing `engine_guard` is intentionally default deny; manual broker position must remain untouched.
- No broker POST calls, no production permit minting, realOrdersEnabled=false.

## Next incremental tests
1. Independently establish AWS worker identity and non-browser managed DB principal, with scoped GRANT and least privilege. Do not use generic service_role or manually set a text flag.
2. Independently verified risk budget, MFA, compliant write entitlement and reconciliation evidence.
3. Use a dedicated isolated QA owner/account and explicitly approved scenario for successful transaction and racing clients; keep actual owner's STOP and live trading OFF.
4. Controlled DB failure/restart testing on AWS QA worker, then real broker lifecycle certification.
5. Source review and targeted tests affected by each change; do not repeat V43-V63 wholesale.
