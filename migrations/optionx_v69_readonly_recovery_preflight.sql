-- V69: Read-only recovery / authorization evidence inventory.
-- No changes to existing guard, no order submission and no live permits.
CREATE OR REPLACE FUNCTION optionx_private.v69_recovery_preflight(
 p_owner uuid, p_broker text
) RETURNS jsonb
LANGUAGE plpgsql VOLATILE SECURITY INVOKER
SET search_path = pg_catalog, optionx_private
AS $fn$
DECLARE
 v_guard_state text;
 v_stopped boolean;
 v_role_present boolean;
 v_attested_worker_count bigint;
 v_risk_approval_count bigint;
 v_unresolved bigint;
 v_unknown bigint;
 v_manual_or_open bigint;
 v_reservations bigint;
 v_lease_count bigint;
 v_reasons text[] := ARRAY[]::text[];
BEGIN
 IF p_owner IS NULL OR p_broker IS NULL OR p_broker NOT IN ('Angel','Delta') THEN
   RAISE EXCEPTION 'INVALID_PREFLIGHT_SELECTOR' USING ERRCODE='22023';
 END IF;
 SELECT g.state,g.new_entries_blocked
 INTO v_guard_state,v_stopped
 FROM optionx_private.engine_guard g WHERE g.owner_id=p_owner;
 IF v_guard_state IS NULL OR v_stopped IS DISTINCT FROM false THEN
   v_reasons:=array_append(v_reasons,'ENGINE_GUARD_STOP_OR_ABSENT');
 END IF;
 SELECT EXISTS(SELECT 1 FROM pg_roles WHERE rolname='optionx_execution_worker' AND rolcanlogin)
 INTO v_role_present;
 IF NOT v_role_present THEN
   v_reasons:=array_append(v_reasons,'INDEPENDENT_DB_WORKER_ROLE_ABSENT');
 END IF;
 SELECT count(*) INTO v_attested_worker_count
 FROM optionx_private.v65_trusted_worker w
 WHERE w.owner_id=p_owner AND w.expires_at>clock_timestamp();
 IF v_attested_worker_count=0 THEN
   v_reasons:=array_append(v_reasons,'TRUSTED_WORKER_ATTESTATION_ABSENT');
 END IF;
 SELECT count(*) INTO v_risk_approval_count
 FROM optionx_private.v65_approved_risk_policy r
 WHERE r.owner_id=p_owner AND r.broker=p_broker
 AND r.day_ist=(clock_timestamp() AT TIME ZONE 'Asia/Kolkata')::date
 AND r.expires_at>clock_timestamp();
 IF v_risk_approval_count=0 THEN
   v_reasons:=array_append(v_reasons,'INDEPENDENT_RISK_APPROVAL_ABSENT');
 END IF;
 SELECT count(*) INTO v_lease_count
 FROM optionx_private.v64_worker_fence f
 WHERE f.owner_id=p_owner AND f.lease_expires_at>clock_timestamp();
 IF v_lease_count=0 THEN
   v_reasons:=array_append(v_reasons,'ACTIVE_LEADER_FENCE_ABSENT');
 END IF;
 SELECT count(*) INTO v_unresolved
 FROM optionx_private.order_intents i
 WHERE i.owner_id=p_owner AND i.broker=p_broker
 AND i.state IN ('AWAITING_BROKER_ACK','BROKER_ACCEPTED','PARTIALLY_FILLED',
                 'CANCEL_REQUESTED','UNKNOWN_BROKER_OUTCOME','MANUAL_REVIEW');
 SELECT count(*) INTO v_unknown
 FROM optionx_private.order_intents i
 WHERE i.owner_id=p_owner AND i.broker=p_broker
 AND i.state IN ('UNKNOWN_BROKER_OUTCOME','MANUAL_REVIEW');
 IF v_unresolved<>0 THEN
   v_reasons:=array_append(v_reasons,'UNRESOLVED_BROKER_INTENTS');
 END IF;
 SELECT count(*) INTO v_reservations
 FROM optionx_private.v64_risk_reservations x
 WHERE x.owner_id=p_owner AND x.broker=p_broker
 AND x.state IN ('STAGING_HELD','STAGING_UNCERTAIN');
 IF v_reservations<>0 THEN
   v_reasons:=array_append(v_reasons,'OPEN_RISK_RESERVATIONS_REQUIRE_RECONCILIATION');
 END IF;
 SELECT count(*) INTO v_manual_or_open
 FROM optionx_private.broker_position_snapshots s
 WHERE s.owner_id=p_owner AND s.broker=p_broker AND s.net_quantity<>0;
 IF v_manual_or_open<>0 THEN
   v_reasons:=array_append(v_reasons,'BROKER_EXPOSURE_REQUIRES_OWNER_RECONCILIATION');
 END IF;
 -- No fresh broker book snapshot / owner MFA / write entitlement has been independently attested here.
 v_reasons:=array_append(v_reasons,'FRESH_MFA_BROKER_WRITE_AND_LIFECYCLE_UNVERIFIED');
 RETURN jsonb_build_object(
   'scope','V69_READ_ONLY_NO_DISPATCH',
   'engineGuardState',coalesce(v_guard_state,'ABSENT_DEFAULT_DENY'),
   'unresolvedIntents',v_unresolved,
   'unknownOutcomes',v_unknown,
   'openReservations',v_reservations,
   'exposureSnapshotRows',v_manual_or_open,
   'blockers',to_jsonb(v_reasons),
   'canReserve',false,'canIssuePermit',false,
   'canSendOrder',false,'canCancelOrder',false,
   'manualPositionsTouched',false
 );
END
$fn$;
REVOKE ALL ON FUNCTION optionx_private.v69_recovery_preflight(uuid,text)
 FROM PUBLIC,anon,authenticated,service_role;
COMMENT ON FUNCTION optionx_private.v69_recovery_preflight(uuid,text) IS
 'V69 diagnostic only; does not authorize production trading; always fail closed.';
