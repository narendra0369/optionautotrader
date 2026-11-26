# OPTIONX V77 — Real MFA evidence and worker certification blockers
2026-11-26

## Proven in actual Supabase (read-only)
- 1 verified TOTP factor and 1 active AAL2 session.
- JOIN across auth.sessions + auth.mfa_factors + auth.users confirmed exactly one active AAL2 session references its owner's verified factor; this is **real** MFA enrollment, not a front-end badge.
- Dedicated Postgres principal optionx_execution_worker created in V70 but still NOLOGIN (zero worker login roles); keep NOLOGIN.
- In optionx_private: 0 engine_guard rows, 0 order_intents, 0 v64_risk_reservations. Absent engine guard = STOP/default-deny.
- V65 positive reservation still blocked by engine_guard constraint requiring new_entries_blocked=TRUE while function requires FALSE. This conflict must be resolved in formally reviewed authorization design, not by disabling guard.
- V72 MFA session validator requires a fresh AAL2 challenge and remains ungranted to public user roles; production API authorization integration not completed.

## V77 AWS audit runner
`scripts/optionx_v77_aws_identity_preflight.sh` is a **read-only** Linux/systemd identity and STS instance-role evidence collector. It never reads environment values, credentials, tokens or protected files; does not contact any broker or database; no service restart.
Host verification has not run in this turn.

## Independent requirements before actual real orders
1. AWS identity with independently verified workload-specific attestation; existing Lightsail assumed instance IAM role alone identifies the machine, not the individual optionx process.
2. Secure short-lived/rotated database authentication mapped to a narrowly scoped principal, with server-side admission policy. No plaintext secrets in repository or ChatGPT; never grant generic DB write or LOGIN just for test success.
3. Verified owner identity / fresh MFA and explicit action-bound approval at the actual server execution endpoint, not a single historical AAL2 badge.
4. Atomic guard redesign, validated in separate authorized QA environment; preserve Owner STOP, 2 trades/day cap, risk reservations and manual position exclusion.
5. Production restart, controlled DB failure/uncertain broker outcome reconciliation, broker order permission/static-IP/exchange approval and native protective stop monitoring.
6. Explicit user-confirmed final live activation only after certification.
Current: **STOP active, no live BUY/SELL/CANCEL, manual position untouched.**
