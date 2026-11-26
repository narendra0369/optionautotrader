# OPTIONX V85 — actual production four-gate read-only investigation
Date: 2026-11-26 IST
Production Supabase project: yghijfzwsvmzaffllszl
Basis: authenticated live Supabase SQL read-only queries and inspected deployed SQL function definitions. No AWS direct SSH, broker session, broker API operation, migration, permission change, or trading action performed.

## Gate 1 independent worker attestation
- Existing V81 independent attestation RLS schema and promotion gate are already deployed.
- Current independent attestation rows: 0. Worker 1 PENDING, 0 VERIFIED.
- V80/V81 Ed25519 signed proofs (HTTP 200 and replay HTTP 409) were completed previously. These prove possession and anti-replay, not independent workload provenance.
- The owner/operator cannot manufacture a trustworthy reviewer, trusted hardware quote, or external signer. Do not promote identity without independently sourced review evidence bound to worker and key fingerprint, expiry and revocation.
Status: NOT CERTIFIED; external verifier and independently obtained verifiable evidence required.

## Gate 2 live-risk authorization
- Existing public.optionx_v79_review_staging_risk(text,date,numeric,integer) requires Auth AAL2, valid session ID, recently challenged verified TOTP <=5min, independently approved V65 policy <=15min old, and limits of up to two entries. It explicitly does not authorize order dispatch.
- Current active V65 risk policy rows: 0; active V65 trusted worker rows: 0; worker database role has NOLOGIN.
- No current evidence of independently risk-approved live execution budget; paper stepped risk is not a live authorization.
Status: CODE EXISTS, APPROVAL ABSENT. Do not insert fictitious attestation or risk policy.

## Gate 3 owner STOP
- Inspected actual constraint: optionx_private.engine_guard.new_entries_blocked CHECK (new_entries_blocked = true).
- Allowed state strings: STOPPED, RESET_REQUESTED, REVIEW_REQUIRED.
- Current owner engine_guard rows: 0; absent guard triggers default-deny in V69 and V82 diagnostics.
- V65 reservation requires an explicitly unblocked guard; current database schema forbids this. Do NOT delete/alter constraint or change guard in production to simulate success.
Status: STOP EFFECTIVE (ABSENT_DEFAULT_DENY), safe activation design NOT YET DEPLOYED. Needs reviewed nonprod lifecycle model, separate signed owner approval, emergency STOP dominance, race/expiry testing and broker recovery.

## Gate 4 order recovery
- Inspected actual optionx_private.v69_recovery_preflight(uuid,text) definition before invoking.
- Invoked against registered worker owner for both broker selectors Angel and Delta, live DB read-only.
- BOTH return scope V69_READ_ONLY_NO_DISPATCH, canReserve=false, canSendOrder=false, canCancelOrder=false, canIssuePermit=false, engineGuardState ABSENT_DEFAULT_DENY.
- Actual blockers for BOTH:
  ENGINE_GUARD_STOP_OR_ABSENT
  INDEPENDENT_DB_WORKER_ROLE_ABSENT
  TRUSTED_WORKER_ATTESTATION_ABSENT
  INDEPENDENT_RISK_APPROVAL_ABSENT
  ACTIVE_LEADER_FENCE_ABSENT
  FRESH_MFA_BROKER_WRITE_AND_LIFECYCLE_UNVERIFIED
- Both have unknownOutcomes=0, unresolvedIntents=0, openReservations=0 and exposureSnapshotRows=0 IN THE OPTIONX DATABASE.
- Live DB order_events, order_intents, position_protection, broker_position_snapshots, and risk reservations counts are 0.
- Zero stored broker snapshots is NOT proof of zero positions. Existing manually held Angel One position from earlier records must not be modified or treated as absent.
Status: REAL DATABASE RECOVERY PREFLIGHT EXECUTED / LIVE BROKER RECONCILIATION NOT CERTIFIED.

## Production no-go
No real BUY, SELL, CANCEL, MODIFY, order intents, risk reservations, worker promotion, credentials or guard changes.
Do not repeat completed historical tests without a regression or expiry reason.

## Precise next dependencies
1. Owner arrange actual independent external reviewer/attestation evidence. Reviewer must be outside AWS root/operator control and cannot use an invented or self-reported process_identity_verified=true.
2. Select architecture for narrowly scoped live gateway; no generic service_role on AWS and no database LOGIN bypass.
3. Work through isolated nonproduction STOP state machine design and fail-closed migration testing. Ensure explicit reset, fresh MFA, trusted worker, risk approval and emergency STOP.
4. Fresh broker-authenticated *read-only* orderbook/tradebook/positions snapshot on owner AWS or authorized broker session, with no token disclosure; distinguish owner manual holdings from OPTIONX intents, reconcile all pending entry/SL/target IDs and protective quantities. Live order lifecycle certification remains independent and must not be inferred from DB counts.
5. Only after independent sign-off and owner approval plan controlled separate broker test session, with exchange/broker compliance, order cancel/replace and partial fill scenarios.

This file documents actual inspection and read-only tests, not completed production live trading certification.
