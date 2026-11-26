-- OPTIONX V82: narrowly scoped, deny-only execution-readiness assessment.
-- No trust enrollment, no approval writes and no broker or reservation grants.
BEGIN;
CREATE OR REPLACE FUNCTION public.optionx_v82_worker_gate_status(
  p_owner uuid, p_worker uuid
) RETURNS jsonb
LANGUAGE plpgsql VOLATILE SECURITY DEFINER
SET search_path=pg_catalog,optionx_private
AS $fn$
DECLARE
 v_state text;
 v_key_attested boolean:=false;
 v_broker_review boolean:=false;
 v_guard_blocked boolean:=true;
 v_blockers text[]:=ARRAY[]::text[];
BEGIN
 IF p_owner IS NULL OR p_worker IS NULL THEN
  RETURN jsonb_build_object('scope','V82_READ_ONLY_GATE','ready',false,
    'canReserve',false,'canTrade',false,'blockers',jsonb_build_array('INVALID_WORKER_BINDING'));
 END IF;
 SELECT registration_state INTO v_state
 FROM optionx_private.v79_worker_public_identity
 WHERE owner_id=p_owner AND worker_id=p_worker;
 IF v_state IS NULL THEN
  v_blockers:=array_append(v_blockers,'WORKER_NOT_REGISTERED');
 ELSIF v_state<>'VERIFIED' THEN
  v_blockers:=array_append(v_blockers,'WORKER_NOT_INDEPENDENTLY_APPROVED');
 END IF;
 SELECT EXISTS(
  SELECT 1 FROM optionx_private.v79_worker_public_identity k
  JOIN optionx_private.v81_independent_worker_attestations a
    ON a.owner_id=k.owner_id AND a.worker_id=k.worker_id
   AND a.public_key_fingerprint_sha256=k.key_fingerprint_sha256
  WHERE k.owner_id=p_owner AND k.worker_id=p_worker
    AND k.registration_state='VERIFIED'
    AND k.approved_at<=clock_timestamp() AND k.expires_at>clock_timestamp()
    AND a.independent_reviewer_id<>k.owner_id
    AND a.process_identity_verified=true AND a.key_custody_verified=true
    AND a.observed_at BETWEEN clock_timestamp()-interval '15 minutes' AND clock_timestamp()
    AND a.expires_at>clock_timestamp()
 ) INTO v_key_attested;
 IF NOT v_key_attested THEN
  v_blockers:=array_append(v_blockers,'INDEPENDENT_ATTESTATION_MISSING_OR_EXPIRED');
 END IF;
 SELECT COALESCE(new_entries_blocked,true) INTO v_guard_blocked
 FROM optionx_private.engine_guard WHERE owner_id=p_owner;
 IF v_guard_blocked IS DISTINCT FROM false THEN
  v_blockers:=array_append(v_blockers,'OWNER_STOP_ACTIVE_OR_GUARD_MISSING');
 END IF;
 IF NOT EXISTS(
   SELECT 1 FROM optionx_private.v65_trusted_worker
   WHERE owner_id=p_owner AND worker_identity=p_worker
     AND expires_at>clock_timestamp()
     AND verified_at BETWEEN clock_timestamp()-interval '15 minutes' AND clock_timestamp()
 ) THEN
  v_blockers:=array_append(v_blockers,'V65_EXECUTION_WORKER_NOT_ATTESTED');
 END IF;
 SELECT EXISTS(
 SELECT 1 FROM optionx_private.v65_approved_risk_policy
 WHERE owner_id=p_owner
   AND day_ist=(clock_timestamp() AT TIME ZONE 'Asia/Kolkata')::date
   AND independently_verified_at BETWEEN clock_timestamp()-interval '15 minutes' AND clock_timestamp()
   AND expires_at>clock_timestamp()
 ) INTO v_broker_review;
 IF NOT v_broker_review THEN
  v_blockers:=array_append(v_blockers,'INDEPENDENT_RISK_POLICY_MISSING');
 END IF;
 -- This is a diagnostic-only gate. Even if every input has later been
 -- certified, this function MUST NOT grant permission or allow dispatch.
 RETURN jsonb_build_object(
  'scope','V82_READ_ONLY_GATE','ready',false,
  'canReserve',false,'canTrade',false,'canCancelOrder',false,
  'blockers',to_jsonb(v_blockers),
  'diagnosticOnly',true);
END
$fn$;
REVOKE ALL ON FUNCTION public.optionx_v82_worker_gate_status(uuid,uuid)
 FROM PUBLIC,anon,authenticated;
GRANT EXECUTE ON FUNCTION public.optionx_v82_worker_gate_status(uuid,uuid)
 TO service_role;
COMMIT;
