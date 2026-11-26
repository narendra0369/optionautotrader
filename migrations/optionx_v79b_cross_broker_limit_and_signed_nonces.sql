-- OPTIONX V79B: Cross-broker two-entry limit and worker signature replay protection.
-- No live order grants, no database login granted to isolated worker.
BEGIN;
CREATE OR REPLACE FUNCTION optionx_private.v79_enforce_reserved_risk()
RETURNS trigger
LANGUAGE plpgsql SECURITY DEFINER
SET search_path = pg_catalog, optionx_private
AS $fn$
DECLARE
  v_approved_loss numeric;
  v_guard boolean;
  v_other_entries bigint;
BEGIN
  IF NEW.reserved_entries < 0 OR NEW.reserved_entries > 2 OR NEW.reserved_loss < 0 THEN
    RAISE EXCEPTION 'V79_TWO_TRADE_OR_RISK_NEGATIVE' USING ERRCODE='23514';
  END IF;
  IF TG_OP='INSERT' THEN
    IF NEW.reserved_entries=0 AND NEW.reserved_loss=0 THEN RETURN NEW; END IF;
  ELSIF NEW.reserved_entries<=OLD.reserved_entries
    AND NEW.reserved_loss<=OLD.reserved_loss THEN RETURN NEW;
  END IF;
  IF session_user <> 'optionx_execution_worker' THEN
    RAISE EXCEPTION 'V79_SCOPED_WORKER_PRINCIPAL_REQUIRED' USING ERRCODE='42501';
  END IF;
  SELECT new_entries_blocked INTO v_guard
    FROM optionx_private.engine_guard WHERE owner_id=NEW.owner_id FOR SHARE;
  IF v_guard IS DISTINCT FROM false THEN
    RAISE EXCEPTION 'V79_OWNER_STOP_OR_GUARD_MISSING' USING ERRCODE='42501';
  END IF;
  SELECT max_reserved_loss INTO v_approved_loss
    FROM optionx_private.v65_approved_risk_policy
    WHERE owner_id=NEW.owner_id AND broker=NEW.broker AND day_ist=NEW.day_ist
      AND independently_verified_at>=clock_timestamp()-interval '15 minutes'
      AND independently_verified_at<=clock_timestamp()
      AND expires_at>clock_timestamp()
    FOR SHARE;
  IF v_approved_loss IS NULL OR NEW.reserved_loss>v_approved_loss THEN
    RAISE EXCEPTION 'V79_INDEPENDENT_DAILY_BUDGET_REQUIRED' USING ERRCODE='42501';
  END IF;

  -- Global, cross-broker owner/day serialization. Zero budget rows can
  -- coexist, but positive increments are serialized and strictly capped.
  PERFORM pg_advisory_xact_lock(hashtextextended(
    'OPTIONX_V79_OWNER_DAY:'||NEW.owner_id::text||':'||NEW.day_ist::text, 0));
  SELECT coalesce(sum(reserved_entries),0) INTO v_other_entries
    FROM optionx_private.v65_reserved_day
    WHERE owner_id=NEW.owner_id AND day_ist=NEW.day_ist
      AND broker<>NEW.broker;
  IF v_other_entries + NEW.reserved_entries > 2 THEN
    RAISE EXCEPTION 'V79_GLOBAL_TWO_TRADES_PER_DAY_EXCEEDED' USING ERRCODE='42501';
  END IF;
  RETURN NEW;
END
$fn$;

CREATE TABLE IF NOT EXISTS optionx_private.v79_worker_signed_nonces (
  owner_id uuid NOT NULL,
  worker_id uuid NOT NULL,
  nonce uuid NOT NULL,
  accepted_at timestamptz NOT NULL DEFAULT clock_timestamp(),
  PRIMARY KEY(owner_id,worker_id,nonce),
  FOREIGN KEY(owner_id,worker_id) REFERENCES optionx_private.v79_worker_public_identity(owner_id,worker_id)
);
ALTER TABLE optionx_private.v79_worker_signed_nonces ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON optionx_private.v79_worker_signed_nonces FROM PUBLIC, anon, authenticated, service_role;

-- Only Supabase server's service_role may submit a NONCE AFTER the Edge
-- function independently verifies Ed25519 signature and short timestamp.
-- Even this RPC only consumes a nonce; it cannot reserve or send orders.
CREATE OR REPLACE FUNCTION public.optionx_v79_consume_worker_nonce(
 p_owner uuid, p_worker uuid, p_nonce uuid
) RETURNS boolean
LANGUAGE plpgsql SECURITY DEFINER
SET search_path = pg_catalog, optionx_private
AS $fn$
DECLARE v_inserted bigint:=0;
BEGIN
 IF p_owner IS NULL OR p_worker IS NULL OR p_nonce IS NULL THEN RETURN false; END IF;
 IF NOT EXISTS(
   SELECT 1 FROM optionx_private.v79_worker_public_identity w
   WHERE w.owner_id=p_owner AND w.worker_id=p_worker
     AND w.registration_state='VERIFIED'
     AND w.approved_at<=clock_timestamp()
     AND w.expires_at>clock_timestamp()
 ) THEN RETURN false; END IF;
 INSERT INTO optionx_private.v79_worker_signed_nonces(owner_id,worker_id,nonce)
 VALUES(p_owner,p_worker,p_nonce)
 ON CONFLICT DO NOTHING;
 GET DIAGNOSTICS v_inserted=ROW_COUNT;
 RETURN v_inserted=1;
END
$fn$;
REVOKE ALL ON FUNCTION public.optionx_v79_consume_worker_nonce(uuid,uuid,uuid)
 FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION public.optionx_v79_consume_worker_nonce(uuid,uuid,uuid)
 TO service_role;
-- Service role can only read public-key registrations, not add its own key.
GRANT SELECT ON optionx_private.v79_worker_public_identity TO service_role;
-- No authenticated user, anon, or service_role may directly insert trusted keys.
COMMIT;
