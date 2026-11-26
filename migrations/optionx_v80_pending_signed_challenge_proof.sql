-- OPTIONX V80 independent pending-key proof-of-possession only.
-- A successful proof does not change PENDING/VERIFIED and does not issue orders.
BEGIN;
CREATE TABLE IF NOT EXISTS optionx_private.v80_pending_worker_proofs (
  owner_id uuid NOT NULL,
  worker_id uuid NOT NULL,
  nonce uuid NOT NULL,
  verified_at timestamptz NOT NULL DEFAULT clock_timestamp(),
  PRIMARY KEY(owner_id,worker_id,nonce),
  FOREIGN KEY(owner_id,worker_id)
    REFERENCES optionx_private.v79_worker_public_identity(owner_id,worker_id)
);
ALTER TABLE optionx_private.v80_pending_worker_proofs ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON optionx_private.v80_pending_worker_proofs
  FROM PUBLIC,anon,authenticated,service_role;

CREATE OR REPLACE FUNCTION public.optionx_v80_pending_worker_key(
 p_owner uuid,p_worker uuid
) RETURNS TABLE (public_key_pem text,key_fingerprint_sha256 text)
LANGUAGE sql VOLATILE SECURITY DEFINER
SET search_path=pg_catalog,optionx_private
AS $fn$
 SELECT public_key_pem,key_fingerprint_sha256
 FROM optionx_private.v79_worker_public_identity
 WHERE owner_id=p_owner AND worker_id=p_worker
   AND registration_state='PENDING'
 LIMIT 1
$fn$;
REVOKE ALL ON FUNCTION public.optionx_v80_pending_worker_key(uuid,uuid)
 FROM PUBLIC,anon,authenticated;
GRANT EXECUTE ON FUNCTION public.optionx_v80_pending_worker_key(uuid,uuid)
 TO service_role;

CREATE OR REPLACE FUNCTION public.optionx_v80_consume_pending_proof(
 p_owner uuid,p_worker uuid,p_nonce uuid
) RETURNS boolean
LANGUAGE plpgsql SECURITY DEFINER
SET search_path=pg_catalog,optionx_private
AS $fn$
DECLARE
 v_inserted bigint:=0;
BEGIN
 IF p_owner IS NULL OR p_worker IS NULL OR p_nonce IS NULL THEN RETURN false; END IF;
 IF NOT EXISTS(
   SELECT 1 FROM optionx_private.v79_worker_public_identity
   WHERE owner_id=p_owner AND worker_id=p_worker
     AND registration_state='PENDING'
 ) THEN RETURN false; END IF;
 INSERT INTO optionx_private.v80_pending_worker_proofs(owner_id,worker_id,nonce)
 VALUES(p_owner,p_worker,p_nonce)
 ON CONFLICT DO NOTHING;
 GET DIAGNOSTICS v_inserted=ROW_COUNT;
 RETURN v_inserted=1;
END
$fn$;
REVOKE ALL ON FUNCTION public.optionx_v80_consume_pending_proof(uuid,uuid,uuid)
 FROM PUBLIC,anon,authenticated;
GRANT EXECUTE ON FUNCTION public.optionx_v80_consume_pending_proof(uuid,uuid,uuid)
 TO service_role;
COMMIT;
