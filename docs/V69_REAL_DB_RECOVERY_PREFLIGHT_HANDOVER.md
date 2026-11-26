# OPTIONX V69 — actual PostgreSQL recovery preflight, not live certification
Date: 2026-11-26

## Done with actual Supabase
- Applied migration `optionx_v69_readonly_recovery_preflight` to `optionx_private` of project `yghijfzwsvmzaffllszl`.
- Function `v69_recovery_preflight(uuid,text)` reads: STOP/engine guard, trusted DB worker role and evidence, independent risk approval, active leader lease, unresolved broker intent, unknown broker outcome, outstanding risk reservations and existing position snapshots.
- Does NOT write data, issue permits, call broker APIs, or authorize entries. Returns all `canReserve/canIssuePermit/canSendOrder/canCancelOrder=false`.
- Actual SQL readback on an isolated nonexistent UUID returned blockers: engine guard absent, DB worker absent, worker attestation absent, risk approval absent, fence absent, fresh MFA/broker lifecycle unverified.
- Function is SECURITY INVOKER, execute not granted to anon, authenticated or service_role.
- Confirmed 0 current `engine_guard`, `order_intents`, and `v64_risk_reservations` rows in schema.
- The existing `engine_guard` DB constraint requires `new_entries_blocked=true`. V65 tries to require false, so its positive path is structurally impossible under current intended STOP. We did not relax constraints or seed fake approvals.

## Verified previously (do not repeat)
V66 real PostgreSQL two-client advisory serialization and client reconnect PASS; V67 isolated PostgreSQL TEMP table positive atomic test PASS and AWS ephemeral process crash/reconnect PASS; V68 ephemeral systemd QA restart PASS.

## Not done / independent evidence required
1. AWS-to-database dedicated production worker authentication (not just OS `optionx` user or setting `session_user` in SQL); no dedicated principal provisioned.
2. Independently verified fresh owner MFA, broker entitlement, compliant IP whitelist, and trusted risk authorization. Zero attestation records.
3. Reviewed production STOP-aware design and independently authorized positive V65 or replacement transaction in isolated separate QA environment, with two-client concurrency. No guard bypass in real owner DB.
4. Production worker actual service restart and meaningful outage/reconnection/unknown-order outcome recovery, with broker reconciliation. V68 only restarted disposable isolated QA worker.
5. Broker order/fill/SL lifecycle certification and separate explicit owner permission before live trading.

Owner STOP active, live orders OFF; owner manual positions excluded. ZELQORIS Marketplace tables unchanged.
