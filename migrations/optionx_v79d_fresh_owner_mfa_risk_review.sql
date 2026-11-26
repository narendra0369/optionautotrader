-- OPTIONX V79D: server-verified, fresh AAL2 owner risk review.
-- This DOES NOT unlock Owner STOP, authorize orders or create risk approval.
-- Approval requires an explicit authenticated user RPC with a recent TOTP challenge.
BEGIN;
CREATE TABLE IF NOT EXISTS optionx_private.v79_owner_mfa_risk_reviews (
  owner_id uuid NOT NULL REFERENCES auth.users(id),
  broker text NOT NULL CHECK(broker IN ('Angel','Delta')),
  day_ist date NOT NULL,
  owner_session_id uuid NOT NULL,
  max_reserved_loss numeric NOT NULL CHECK(max_reserved_loss>0),
  max_entries int NOT NULL CHECK(max_entries BETWEEN 1 AND 2),
  reviewed_at timestamptz NOT NULL,
  expires_at timestamptz NOT NULL,
  PRIMARY KEY(owner_id,broker,day_ist),
  CONSTRAINT v79_mfa_risk_review_ttl CHECK(
     expires_at>reviewed_at AND expires_at<=reviewed_at + interval '5 minutes'
  )
);
ALTER TABLE optionx_private.v79_owner_mfa_risk_reviews ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON optionx_private.v79_owner_mfa_risk_reviews FROM PUBLIC,anon,authenticated,service_role;

CREATE OR REPLACE FUNCTION public.optionx_v79_review_staging_risk(
 p_broker text,p_day date,p_limit numeric,p_entries integer
) RETURNS jsonb
LANGUAGE plpgsql SECURITY DEFINER
SET search_path=pg_catalog,auth,optionx_private
AS $fn$
DECLARE
  v_user uuid:=auth.uid();
  v_jwt jsonb:=auth.jwt();
  v_sid_text text;
  v_sid uuid;
  v_valid boolean:=false;
  v_policy numeric;
  v_now timestamptz:=clock_timestamp();
BEGIN
  IF v_user IS NULL OR v_jwt->>'aal' IS DISTINCT FROM 'aal2' THEN
    RAISE EXCEPTION 'V79_FRESH_OWNER_MFA_REQUIRED' USING ERRCODE='42501';
  END IF;
  v_sid_text:=v_jwt->>'session_id';
  IF v_sid_text IS NULL OR v_sid_text !~* '^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$' THEN
    RAISE EXCEPTION 'V79_SIGNED_AUTH_SESSION_REQUIRED' USING ERRCODE='42501';
  END IF;
  v_sid:=v_sid_text::uuid;
  IF p_broker NOT IN ('Angel','Delta') OR p_broker IS NULL
     OR p_day IS DISTINCT FROM (v_now AT TIME ZONE 'Asia/Kolkata')::date
     OR p_limit IS NULL OR p_limit<=0
     OR p_entries IS NULL OR p_entries NOT BETWEEN 1 AND 2 THEN
    RAISE EXCEPTION 'V79_INVALID_REVIEW_SCOPE' USING ERRCODE='22023';
  END IF;
  SELECT EXISTS(
   SELECT 1 FROM auth.sessions s
   JOIN auth.mfa_factors f ON f.id=s.factor_id AND f.user_id=s.user_id
   JOIN auth.users u ON u.id=s.user_id
   WHERE s.id=v_sid AND s.user_id=v_user AND s.aal::text='aal2'
     AND (s.not_after IS NULL OR s.not_after>v_now)
     AND u.deleted_at IS NULL
     AND f.status::text='verified'
     AND f.last_challenged_at BETWEEN v_now-interval '5 minutes' AND v_now
  ) INTO v_valid;
  IF NOT v_valid THEN
    RAISE EXCEPTION 'V79_CURRENT_VERIFIED_TOTP_CHALLENGE_REQUIRED' USING ERRCODE='42501';
  END IF;
  -- A fresh independent risk attestation is required before owner can review.
  SELECT max_reserved_loss INTO v_policy
  FROM optionx_private.v65_approved_risk_policy
  WHERE owner_id=v_user AND broker=p_broker AND day_ist=p_day
    AND independently_verified_at BETWEEN v_now-interval '15 minutes' AND v_now
    AND expires_at>v_now;
  IF v_policy IS NULL OR p_limit>v_policy THEN
    RAISE EXCEPTION 'V79_INDEPENDENT_RISK_POLICY_REQUIRED' USING ERRCODE='42501';
  END IF;
  INSERT INTO optionx_private.v79_owner_mfa_risk_reviews(
      owner_id,broker,day_ist,owner_session_id,max_reserved_loss,
      max_entries,reviewed_at,expires_at)
  VALUES(v_user,p_broker,p_day,v_sid,p_limit,p_entries,v_now,v_now+interval '5 minutes')
  ON CONFLICT(owner_id,broker,day_ist) DO UPDATE SET
    owner_session_id=EXCLUDED.owner_session_id,
    max_reserved_loss=EXCLUDED.max_reserved_loss,
    max_entries=EXCLUDED.max_entries,
    reviewed_at=EXCLUDED.reviewed_at,
    expires_at=EXCLUDED.expires_at;
  RETURN jsonb_build_object(
     'status','FRESH_OWNER_MFA_RISK_REVIEW_ONLY',
     'expiresAt',v_now+interval '5 minutes',
     'canIssuePermit',false,'canReserve',false,'canSendOrder',false);
END
$fn$;
REVOKE ALL ON FUNCTION public.optionx_v79_review_staging_risk(text,date,numeric,integer)
 FROM PUBLIC,anon,service_role;
GRANT EXECUTE ON FUNCTION public.optionx_v79_review_staging_risk(text,date,numeric,integer)
 TO authenticated;
COMMIT;
