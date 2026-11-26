-- V79C: service-role-only lookup of independently reviewed worker public keys.
-- Does not authenticate a worker by itself or issue any execution permit.
BEGIN;
CREATE OR REPLACE FUNCTION public.optionx_v79_worker_verification_key(
 p_owner uuid, p_worker uuid
) RETURNS TABLE(public_key_pem text, key_fingerprint_sha256 text)
LANGUAGE sql STABLE SECURITY DEFINER
SET search_path=pg_catalog,optionx_private
AS $fn$
 SELECT k.public_key_pem,k.key_fingerprint_sha256
 FROM optionx_private.v79_worker_public_identity k
 WHERE k.owner_id=p_owner AND k.worker_id=p_worker
   AND k.registration_state='VERIFIED'
   AND k.approved_at<=clock_timestamp()
   AND k.expires_at>clock_timestamp()
 LIMIT 1
$fn$;
REVOKE ALL ON FUNCTION public.optionx_v79_worker_verification_key(uuid,uuid)
 FROM PUBLIC,anon,authenticated;
GRANT EXECUTE ON FUNCTION public.optionx_v79_worker_verification_key(uuid,uuid)
 TO service_role;
COMMIT;
