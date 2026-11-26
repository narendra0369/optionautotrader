# OPTIONX V72 — actual Supabase Auth MFA diagnostic, no live authorization
Date: 2026-11-26

## Actual Supabase project
Project `yghijfzwsvmzaffllszl`, optionx_private schema.

### Completed and independently queried
- Auth inspection: 1 non-deleted auth user, **0 verified MFA factors**, **0 aal2 sessions**. No real owner MFA evidence exists to certify.
- Added `v72_mfa_session_evidence()` with actual Supabase Auth UID/JWT AAL2 check, JWT session UUID, `auth.sessions` user/aal/factor association, verified `auth.mfa_factors` within 5 minutes. SECURE DEFINER with explicit pg_catalog/auth references, no input parameters, no trading permission.
- Actual SQL unauthenticated call returned `mfaSessionVerified:false`, blocker `AUTHENTICATED_OWNER_SESSION_REQUIRED`, all `canReserve/canDispatch/canIssuePermit:false`.
- Actual grant check: `anon`, `authenticated`, `service_role` EXECUTE all false. Function is NOT exposed as an app RPC until owner session route and privilege review.
- Existing `optionx_execution_worker` from V70 remains NOLOGIN with no schema privileges. This is NOT bound to AWS IAM, and not proof of AWS workload identity.
- No broker calls, signing, permit minting, risk reservations, ZELQORIS changes, or manual position modifications.

### Remaining prerequisites for real execution
1. User enrolls and challenges verified MFA factor in their supported OptionX Supabase Auth owner login; evidence must be bound to same active owner and signed session. Do not collect TOTP, refresh tokens, or passwords in ChatGPT.
2. Review the real OptionX owner-auth web/backend route; make authenticated API verify Supabase JWT signatures and session against trusted Auth service; then narrow grant for read-only MFA diagnostic if appropriate. It must NEVER itself authorize orders.
3. AWS workload identity: current Lightsail instance STS role proves instance only, not dedicated `optionx` process identity. Provision separate workload-to-DB scoped auth through managed secrets/short-lived exchange and audited IAM; *do not* enable generic `optionx_execution_worker` LOGIN or V65 execution merely to pass tests.
4. V65 positive production reservation still intentionally blocked by STOP and engine_guard database constraint requiring new_entries_blocked TRUE. Need independently reviewed STOP-aware transactional design in isolated QA, no live bypass.
5. Broker write entitlement, static IP whitelist, exchange compliance, protective SL/filled reconciliation and production restart/outage verification.

### Status
V72 MFA diagnostic deployed and fails closed on no authenticated session: PASS.
Real owner MFA: NOT CONFIGURED (zero verified factors).
AWS worker IAM-to-DB binding: NOT CERTIFIED.
Live execution: OFF.
