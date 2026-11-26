-- V79E: enforce REAL fresh owner MFA approval on every reserved-risk increment.
-- Preserves global two-trade/day limit, independently reviewed policy, and STOP.
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
  v_owner_session uuid;
  v_owner_mfa_limit numeric;
  v_owner_max_entries integer;
  v_recent_factor boolean:=false;
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

  -- Independent owner action review MUST be backed by fresh Supabase
  -- Auth MFA factor/session, not a browser flag or unverified account badge.
  SELECT owner_session_id,max_reserved_loss,max_entries
    INTO v_owner_session,v_owner_mfa_limit,v_owner_max_entries
  FROM optionx_private.v79_owner_mfa_risk_reviews
  WHERE owner_id=NEW.owner_id AND broker=NEW.broker
    AND day_ist=NEW.day_ist
    AND reviewed_at>=clock_timestamp()-interval '5 minutes'
    AND expires_at>clock_timestamp();
  IF v_owner_session IS NULL
     OR v_owner_mfa_limit < NEW.reserved_loss
     OR v_owner_max_entries < NEW.reserved_entries THEN
    RAISE EXCEPTION 'V79_FRESH_OWNER_MFA_RISK_APPROVAL_REQUIRED'
      USING ERRCODE='42501';
  END IF;
  SELECT EXISTS(
    SELECT 1
    FROM auth.sessions ss
    JOIN auth.mfa_factors ff ON ff.id=ss.factor_id AND ff.user_id=ss.user_id
    JOIN auth.users uu ON uu.id=ss.user_id
    WHERE ss.id=v_owner_session AND ss.user_id=NEW.owner_id
      AND ss.aal::text='aal2'
      AND (ss.not_after IS NULL OR ss.not_after>clock_timestamp())
      AND uu.deleted_at IS NULL AND ff.status::text='verified'
      AND ff.last_challenged_at >=clock_timestamp()-interval '5 minutes'
      AND ff.last_challenged_at<=clock_timestamp()
  ) INTO v_recent_factor;
  IF NOT v_recent_factor THEN
    RAISE EXCEPTION 'V79_FRESH_MFA_FACTOR_SESSION_REQUIRED'
      USING ERRCODE='42501';
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
REVOKE ALL ON FUNCTION optionx_private.v79_enforce_reserved_risk()
 FROM PUBLIC, anon, authenticated, service_role;
COMMIT;
