-- OPTIONX V79: actual DB-enforced risk admission and independent worker key registry.
-- No permits, no broker execution, no worker LOGIN/GRANT.
BEGIN;
CREATE TABLE IF NOT EXISTS optionx_private.v79_worker_public_identity (
  owner_id uuid NOT NULL REFERENCES auth.users(id),
  worker_id uuid NOT NULL,
  key_fingerprint_sha256 text NOT NULL CHECK (key_fingerprint_sha256 ~ '^[0-9a-f]{64}$'),
  public_key_pem text NOT NULL CHECK (
    length(public_key_pem) BETWEEN 100 AND 3000
    AND public_key_pem LIKE '-----BEGIN PUBLIC KEY-----%'
    AND public_key_pem LIKE '%-----END PUBLIC KEY-----'
  ),
  registration_state text NOT NULL DEFAULT 'PENDING'
    CHECK (registration_state IN ('PENDING','REVOKED','VERIFIED')),
  attestation_reference text,
  approved_at timestamptz,
  expires_at timestamptz,
  created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
  PRIMARY KEY (owner_id, worker_id),
  UNIQUE(key_fingerprint_sha256),
  CONSTRAINT v79_worker_verified_requires_independent_approval CHECK(
    registration_state <> 'VERIFIED' OR
    (attestation_reference IS NOT NULL AND length(attestation_reference)>10
     AND approved_at IS NOT NULL AND expires_at > approved_at)
  )
);
ALTER TABLE optionx_private.v79_worker_public_identity ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON optionx_private.v79_worker_public_identity FROM PUBLIC, anon, authenticated, service_role;
-- No RLS policies: no browser/service role can bootstrap a trusted key.
-- Do not populate VERIFIED entries from self-declared key material.
CREATE OR REPLACE FUNCTION optionx_private.v79_enforce_reserved_risk()
RETURNS trigger
LANGUAGE plpgsql SECURITY DEFINER
SET search_path = pg_catalog, optionx_private
AS $fn$
DECLARE
  v_approved_loss numeric;
  v_guard boolean;
BEGIN
  IF NEW.reserved_entries < 0 OR NEW.reserved_entries > 2 OR NEW.reserved_loss < 0 THEN
    RAISE EXCEPTION 'V79_TWO_TRADE_OR_RISK_NEGATIVE'
      USING ERRCODE='23514';
  END IF;

  -- Initial no-budget zero row is safe to create. Decrements are allowed
  -- for emergency reconciliation, but increases require independent proof.
  IF TG_OP = 'INSERT' THEN
    IF NEW.reserved_entries = 0 AND NEW.reserved_loss = 0 THEN RETURN NEW; END IF;
  ELSIF NEW.reserved_entries <= OLD.reserved_entries
        AND NEW.reserved_loss <= OLD.reserved_loss THEN
    RETURN NEW;
  END IF;

  IF session_user <> 'optionx_execution_worker' THEN
    RAISE EXCEPTION 'V79_SCOPED_WORKER_PRINCIPAL_REQUIRED'
      USING ERRCODE='42501';
  END IF;

  SELECT new_entries_blocked INTO v_guard
  FROM optionx_private.engine_guard
  WHERE owner_id=NEW.owner_id FOR SHARE;
  IF v_guard IS DISTINCT FROM false THEN
    RAISE EXCEPTION 'V79_OWNER_STOP_OR_GUARD_MISSING'
      USING ERRCODE='42501';
  END IF;

  SELECT max_reserved_loss INTO v_approved_loss
  FROM optionx_private.v65_approved_risk_policy
  WHERE owner_id=NEW.owner_id AND broker=NEW.broker
    AND day_ist=NEW.day_ist
    AND independently_verified_at >= clock_timestamp() - interval '15 minutes'
    AND independently_verified_at <= clock_timestamp()
    AND expires_at > clock_timestamp()
  FOR SHARE;

  IF v_approved_loss IS NULL
     OR NEW.reserved_loss > v_approved_loss
     OR NEW.reserved_entries > 2 THEN
    RAISE EXCEPTION 'V79_INDEPENDENT_DAILY_BUDGET_OR_TRADE_LIMIT_REQUIRED'
      USING ERRCODE='42501';
  END IF;
  RETURN NEW;
END
$fn$;

DROP TRIGGER IF EXISTS v79_enforce_reserved_risk_tg ON optionx_private.v65_reserved_day;
CREATE TRIGGER v79_enforce_reserved_risk_tg
BEFORE INSERT OR UPDATE OF reserved_entries,reserved_loss
ON optionx_private.v65_reserved_day
FOR EACH ROW EXECUTE FUNCTION optionx_private.v79_enforce_reserved_risk();
REVOKE ALL ON FUNCTION optionx_private.v79_enforce_reserved_risk() FROM PUBLIC, anon, authenticated, service_role;
-- Tighten the already staging-only worker privilege: remains NOLOGIN.
DO $do$
BEGIN
 IF EXISTS(SELECT 1 FROM pg_roles WHERE rolname='optionx_execution_worker' AND rolcanlogin) THEN
   RAISE EXCEPTION 'V79_WORKER_ROLE_MUST_REMAIN_NOLOGIN';
 END IF;
END
$do$;
COMMIT;
