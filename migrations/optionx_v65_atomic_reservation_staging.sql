-- OPTIONX V65: fail-closed PostgreSQL atomic staging reservation
-- No production execution entitlement. Never returns an order permit.
-- All evidence tables are created EMPTY. DO NOT seed with fake attestations.
CREATE TABLE IF NOT EXISTS optionx_private.v65_approved_risk_policy (
 owner_id uuid NOT NULL REFERENCES auth.users(id),
 broker text NOT NULL CHECK(broker IN ('Angel','Delta')),
 day_ist date NOT NULL,
 max_reserved_loss numeric NOT NULL CHECK(max_reserved_loss > 0),
 attestation_reference text NOT NULL CHECK(length(attestation_reference)>=16),
 independently_verified_at timestamptz NOT NULL,
 expires_at timestamptz NOT NULL,
 PRIMARY KEY(owner_id,broker,day_ist)
);
CREATE TABLE IF NOT EXISTS optionx_private.v65_trusted_worker (
 owner_id uuid NOT NULL REFERENCES auth.users(id),
 worker_identity uuid NOT NULL,
 approved_db_role name NOT NULL,
 attestation_reference text NOT NULL CHECK(length(attestation_reference)>=16),
 verified_at timestamptz NOT NULL,
 expires_at timestamptz NOT NULL,
 PRIMARY KEY(owner_id,worker_identity)
);
CREATE TABLE IF NOT EXISTS optionx_private.v65_reserved_day (
 owner_id uuid NOT NULL REFERENCES auth.users(id),
 broker text NOT NULL CHECK(broker IN ('Angel','Delta')),
 day_ist date NOT NULL,
 reserved_entries integer NOT NULL DEFAULT 0 CHECK (reserved_entries BETWEEN 0 AND 2),
 reserved_loss numeric NOT NULL DEFAULT 0 CHECK(reserved_loss >= 0),
 PRIMARY KEY(owner_id,broker,day_ist)
);
ALTER TABLE optionx_private.v65_approved_risk_policy ENABLE ROW LEVEL SECURITY;
ALTER TABLE optionx_private.v65_trusted_worker ENABLE ROW LEVEL SECURITY;
ALTER TABLE optionx_private.v65_reserved_day ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON optionx_private.v65_approved_risk_policy FROM PUBLIC, anon, authenticated;
REVOKE ALL ON optionx_private.v65_trusted_worker FROM PUBLIC, anon, authenticated;
REVOKE ALL ON optionx_private.v65_reserved_day FROM PUBLIC, anon, authenticated;

CREATE OR REPLACE FUNCTION optionx_private.v65_atomic_reserve_staging(
 p_owner uuid, p_worker uuid, p_epoch bigint, p_broker text, p_day date,
 p_key text, p_market text, p_token text, p_symbol text, p_kind text,
 p_quantity bigint, p_entry numeric, p_stop numeric, p_target numeric, p_risk numeric
) RETURNS jsonb
LANGUAGE plpgsql SECURITY INVOKER
SET search_path = pg_catalog, optionx_private
AS $function$
DECLARE
 v_role name := session_user;
 v_guard boolean;
 v_fence record;
 v_policy record;
 v_counter record;
 v_existing uuid;
 v_intent uuid;
BEGIN
 -- Hard gate: intended isolated worker database principal has NOT been
 -- provisioned. JWT claims, caller-provided flags and service_role are
 -- NOT valid substitutes for the database principal.
 IF v_role <> 'optionx_execution_worker' THEN
   RAISE EXCEPTION 'WORKER_DB_ROLE_NOT_ATTESTED' USING ERRCODE='42501';
 END IF;
 IF p_owner IS NULL OR p_worker IS NULL OR p_epoch IS NULL OR p_epoch <= 0
    OR p_broker NOT IN ('Angel','Delta') OR p_broker IS NULL
    OR p_day IS DISTINCT FROM (now() AT TIME ZONE 'Asia/Kolkata')::date
    OR p_key IS NULL OR p_key !~ '^[A-Za-z0-9_-]{8,96}$'
    OR p_market NOT IN ('NIFTY','BANKNIFTY','BTC')
    OR p_market IS NULL OR coalesce(length(p_token),0)=0
    OR coalesce(length(p_symbol),0)=0 OR coalesce(length(p_kind),0)=0
    OR p_quantity IS NULL OR p_quantity <= 0
    OR p_entry IS NULL OR p_entry <= 0 OR p_stop IS NULL OR p_stop <= 0
    OR p_target IS NULL OR p_target <= 0 OR p_risk IS NULL OR p_risk <= 0 THEN
   RAISE EXCEPTION 'INVALID_RESERVATION_INPUT' USING ERRCODE='22023';
 END IF;
 -- Serialize all entry budget changes per owner/broker/day.
 PERFORM pg_advisory_xact_lock(hashtextextended(
   p_owner::text || ':' || p_broker || ':' || p_day::text, 0));
 SELECT new_entries_blocked INTO v_guard
 FROM optionx_private.engine_guard WHERE owner_id=p_owner FOR UPDATE;
 IF v_guard IS DISTINCT FROM false THEN
   RAISE EXCEPTION 'OWNER_ENGINE_STOP_OR_GUARD_MISSING' USING ERRCODE='42501';
 END IF;
 SELECT * INTO v_fence FROM optionx_private.v64_worker_fence
 WHERE owner_id=p_owner FOR UPDATE;
 IF NOT FOUND OR v_fence.worker_identity IS DISTINCT FROM p_worker
   OR v_fence.fencing_epoch IS DISTINCT FROM p_epoch
   OR v_fence.lease_expires_at <= clock_timestamp() THEN
   RAISE EXCEPTION 'STALE_OR_UNVERIFIED_LEADER' USING ERRCODE='42501';
 END IF;
 IF NOT EXISTS(
    SELECT 1 FROM optionx_private.v65_trusted_worker w
    WHERE w.owner_id=p_owner AND w.worker_identity=p_worker
    AND w.approved_db_role=v_role AND w.expires_at>clock_timestamp()
    AND w.verified_at>=clock_timestamp()-interval '15 minutes'
 ) THEN
   RAISE EXCEPTION 'INDEPENDENT_WORKER_ATTESTATION_MISSING' USING ERRCODE='42501';
 END IF;
 SELECT * INTO v_policy FROM optionx_private.v65_approved_risk_policy
 WHERE owner_id=p_owner AND broker=p_broker AND day_ist=p_day FOR UPDATE;
 IF NOT FOUND OR v_policy.expires_at<=clock_timestamp()
   OR v_policy.independently_verified_at<clock_timestamp()-interval '15 minutes' THEN
   RAISE EXCEPTION 'INDEPENDENT_RISK_APPROVAL_MISSING' USING ERRCODE='42501';
 END IF;
 IF NOT EXISTS(
    SELECT 1 FROM optionx_private.risk_day_snapshot s
    WHERE s.owner_id=p_owner AND s.broker=p_broker AND s.day_ist=p_day
       AND s.number_of_entries < 2
       AND s.verified_at >= clock_timestamp()-interval '30 seconds'
 ) THEN
   RAISE EXCEPTION 'FRESH_VERIFIED_RISK_SNAPSHOT_MISSING' USING ERRCODE='42501';
 END IF;
 -- Unknown/absent/manual-position snapshot always blocks automated entry.
 IF NOT EXISTS(
    SELECT 1 FROM optionx_private.broker_position_snapshots s
    WHERE s.owner_id=p_owner AND s.broker=p_broker
      AND s.authenticated_source=true
      AND s.snapshot_at>=clock_timestamp()-interval '30 seconds'
 ) OR EXISTS(
    SELECT 1 FROM optionx_private.broker_position_snapshots s
    WHERE s.owner_id=p_owner AND s.broker=p_broker
       AND s.net_quantity<>0
 ) THEN
   RAISE EXCEPTION 'POSITION_RECONCILIATION_UNVERIFIED_OR_EXPOSED' USING ERRCODE='42501';
 END IF;
 -- Existing intent is rejected, never automatically retried or dispatched.
 SELECT id INTO v_existing FROM optionx_private.order_intents
 WHERE owner_id=p_owner AND broker=p_broker AND trade_day_ist=p_day
   AND idempotency_key=p_key FOR UPDATE;
 IF FOUND THEN
   RAISE EXCEPTION 'DUPLICATE_INTENT_NO_RETRY' USING ERRCODE='23505';
 END IF;
 INSERT INTO optionx_private.v65_reserved_day(owner_id,broker,day_ist,reserved_entries,reserved_loss)
 VALUES(p_owner,p_broker,p_day,0,0)
 ON CONFLICT (owner_id,broker,day_ist) DO NOTHING;
 SELECT * INTO v_counter FROM optionx_private.v65_reserved_day
 WHERE owner_id=p_owner AND broker=p_broker AND day_ist=p_day FOR UPDATE;
 IF v_counter.reserved_entries >= 2
   OR v_counter.reserved_loss + p_risk > v_policy.max_reserved_loss THEN
   RAISE EXCEPTION 'TWO_TRADE_OR_RISK_BUDGET_EXCEEDED' USING ERRCODE='42501';
 END IF;
 INSERT INTO optionx_private.order_intents(
   owner_id,trade_day_ist,idempotency_key,broker,market,
   instrument_token,contract_symbol,contract_kind,side,
   quantity,planned_entry,planned_stop,planned_target,estimated_max_loss,state
 ) VALUES (
   p_owner,p_day,p_key,p_broker,p_market,p_token,p_symbol,p_kind,'ENTRY_BUY',
   p_quantity,p_entry,p_stop,p_target,p_risk,'PREPARED'
 ) RETURNING id INTO v_intent;
 INSERT INTO optionx_private.v64_risk_reservations(
   owner_id,broker,trade_day_ist,intent_id,idempotency_key,
   worker_identity,fencing_epoch,reserved_max_loss
 ) VALUES (
   p_owner,p_broker,p_day,v_intent,p_key,p_worker,p_epoch,p_risk
 );
 UPDATE optionx_private.v65_reserved_day
 SET reserved_entries=reserved_entries+1,reserved_loss=reserved_loss+p_risk
 WHERE owner_id=p_owner AND broker=p_broker AND day_ist=p_day;
 -- Under PostgreSQL statement atomicity all three writes succeed or none.
 -- Return only a staging reference, never a transport permit.
 RETURN jsonb_build_object('state','STAGING_PREPARED_ONLY',
   'intent_id',v_intent,'canIssuePermit',false,'canSendBrokerOrder',false);
END
$function$;
REVOKE ALL ON FUNCTION optionx_private.v65_atomic_reserve_staging(
 uuid,uuid,bigint,text,date,text,text,text,text,text,bigint,numeric,numeric,numeric,numeric)
 FROM PUBLIC, anon, authenticated, service_role;
-- NO GRANT to an executor: principal not provisioned; real call remains blocked.
COMMENT ON FUNCTION optionx_private.v65_atomic_reserve_staging(
 uuid,uuid,bigint,text,date,text,text,text,text,text,bigint,numeric,numeric,numeric,numeric)
 IS 'STAGING ONLY; fail closed until independently certified DB worker, STOP, risk and position evidence; no signing/dispatch.';
