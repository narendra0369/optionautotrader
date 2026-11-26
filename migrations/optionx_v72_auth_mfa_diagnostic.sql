-- OPTIONX V72 strict, independent Supabase Auth MFA gate.
-- Diagnostic only: never modifies engine guard, risk, permits, positions or orders.
-- Deliberately NOT granted to application roles until audited API integration.
CREATE OR REPLACE FUNCTION optionx_private.v72_mfa_session_evidence()
RETURNS jsonb
LANGUAGE plpgsql STABLE SECURITY DEFINER
SET search_path = pg_catalog, auth, optionx_private
AS $func$
DECLARE
 v_uid uuid := auth.uid();
 v_jwt jsonb := auth.jwt();
 v_session_text text;
 v_session_id uuid;
 v_valid boolean := false;
 v_reasons text[] := ARRAY[]::text[];
BEGIN
 IF v_uid IS NULL THEN
   v_reasons := array_append(v_reasons,'AUTHENTICATED_OWNER_SESSION_REQUIRED');
 ELSE
   v_session_text := v_jwt->>'session_id';
   IF v_session_text IS NULL OR v_session_text !~* '^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$' THEN
     v_reasons := array_append(v_reasons,'AUTH_SESSION_ID_MISSING');
   ELSIF v_jwt->>'aal' IS DISTINCT FROM 'aal2' THEN
     v_reasons := array_append(v_reasons,'AAL2_REQUIRED');
   ELSE
     v_session_id := v_session_text::uuid;
     SELECT EXISTS (
       SELECT 1
       FROM auth.sessions s
       JOIN auth.mfa_factors f
         ON f.id=s.factor_id AND f.user_id=s.user_id
       JOIN auth.users u
         ON u.id=s.user_id
       WHERE s.id=v_session_id
         AND s.user_id=v_uid
         AND s.aal::text='aal2'
         AND (s.not_after IS NULL OR s.not_after>clock_timestamp())
         AND u.deleted_at IS NULL
         AND f.status::text='verified'
         AND f.last_challenged_at IS NOT NULL
         AND f.last_challenged_at>=clock_timestamp()-interval '5 minutes'
         AND f.last_challenged_at<=clock_timestamp()
     ) INTO v_valid;
     IF NOT v_valid THEN
       v_reasons := array_append(v_reasons,'FRESH_VERIFIED_FACTOR_SESSION_NOT_FOUND');
     END IF;
   END IF;
 END IF;
 RETURN jsonb_build_object(
   'scope','V72_MFA_DIAGNOSTIC_ONLY',
   'mfaSessionVerified',v_valid,
   'canIssuePermit',false,
   'canReserve',false,
   'canDispatch',false,
   'blockers',to_jsonb(v_reasons)
 );
END
$func$;
REVOKE ALL ON FUNCTION optionx_private.v72_mfa_session_evidence()
  FROM PUBLIC, anon, authenticated, service_role;
COMMENT ON FUNCTION optionx_private.v72_mfa_session_evidence()
 IS 'V72 verified Supabase Auth AAL2 MFA session diagnostic; no live permissions, do not expose until owner API route audited';
