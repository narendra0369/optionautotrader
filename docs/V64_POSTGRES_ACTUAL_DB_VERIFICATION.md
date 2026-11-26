# OPTIONX V64 — actual PostgreSQL foundation, not production certification

Date: 2026-11-26

## Completed using Supabase connector against project yghijfzwsvmzaffllszl
- Inspected existing `optionx_private` nine-table schema.
- Verified existing unique constraint on `order_intents(owner_id,broker,trade_day_ist,idempotency_key)`.
- Verified `risk_day_snapshot` per owner/broker/day primary key.
- Verified `engine_guard.new_entries_blocked` is constrained to TRUE.
- **Applied** additive migration `optionx_v64_additive_staging_fencing_and_risk_reservations` via Supabase.
- Read-back verification: new `v64_worker_fence` and `v64_risk_reservations` tables exist with row-level security; 3 and 10 constraints respectively.
- Row counts after migration: 0 active fence, 0 risk reservations, 0 guard records.
- No broker order call, no changes to existing OptionX orders or positions, no ZELQORIS tables altered.

## Still NOT done (do not mark certified)
- No production transaction function yet simultaneously writing a real order intent and risk reservation with budget locking.
- No production hot-path worker and no independent MFA, permission or broker write attestation.
- No actual production DB concurrent transaction success/failure test (migration read-back is not this test).
- No active fencing owner; no production authorization, signing or broker order dispatch.
- V63 staging 24/24 PASS remains valid but does not certify live PostgreSQL flow.

## Next targeted work
1. Review risk budget source and trusted identity binding (not browser flags).
2. Review PostgreSQL transaction/RPC design and ensure SELECT FOR UPDATE on per-day budget and worker lease, consistent lock ordering, unique idempotency and crash-unknown handling.
3. Implement transaction function with deny-on-missing-approval, retain STOP; verify RLS and service role access.
4. Independently verify MFA, static IP whitelisting, exchange compliance, account write entitlement.
5. Broker lifecycle and protective SL certification before any dispatch capability.

## Safety
`engine_guard` deliberately stays default deny. Existing manual position is never adopted or sold. No script should flip STOP, alter existing position, enable permit mint, or call POST order endpoints.
