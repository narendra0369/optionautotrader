-- OPTIONX V81: Independent-review gate, default-deny, no trading grants.
-- Existing V80 PENDING proof remains valid, no privilege changes.
BEGIN;
CREATE TABLE IF NOT EXISTS optionx_private.v81_independent_worker_attestations (
 owner_id uuid NOT NULL,
 worker_id uuid NOT NULL,
 public_key_fingerprint_sha256 text NOT NULL CHECK(public_key_fingerprint_sha256 ~ '^[0-9a-f]{64}$'),
 independent_reviewer_id uuid NOT NULL REFERENCES auth.users(id),
 independent_evidence_reference text NOT NULL CHECK(length(independent_evidence_reference) BETWEEN 32 AND 256),
 workload_identity_kind text NOT NULL CHECK(workload_identity_kind IN ('VERIFIED_MACHINE_WORKLOAD','VERIFIED_HARDWARE_BACKED')),
 process_identity_verified boolean NOT NULL CHECK(process_identity_verified=true),
 key_custody_verified boolean NOT NULL CHECK(key_custody_verified=true),
 observed_at timestamptz NOT NULL,
 expires_at timestamptz NOT NULL,
 created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
 PRIMARY KEY(owner_id,worker_id),
 FOREIGN KEY (owner_id,worker_id)
   REFERENCES optionx_private.v79_worker_public_identity(owner_id,worker_id),
 CONSTRAINT v81_independent_reviewer_required CHECK(independent_reviewer_id<>owner_id),
 CONSTRAINT v81_attestation_ttl CHECK(
   expires_at>observed_at AND expires_at<=observed_at+interval '15 minutes'
 )
);
ALTER TABLE optionx_private.v81_independent_worker_attestations ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON optionx_private.v81_independent_worker_attestations
 FROM PUBLIC,anon,authenticated,service_role;

-- No self-attested worker can become VERIFIED without separate reviewed evidence.
CREATE OR REPLACE FUNCTION optionx_private.v81_block_unattested_worker_promotion()
RETURNS trigger LANGUAGE plpgsql
SECURITY DEFINER SET search_path=pg_catalog,optionx_private
AS $fn$
BEGIN
 IF NEW.registration_state='VERIFIED' THEN
   IF NOT EXISTS(
     SELECT 1
     FROM optionx_private.v81_independent_worker_attestations a
     WHERE a.owner_id=NEW.owner_id
       AND a.worker_id=NEW.worker_id
       AND a.public_key_fingerprint_sha256=NEW.key_fingerprint_sha256
       AND a.independent_reviewer_id<>NEW.owner_id
       AND a.process_identity_verified=true AND a.key_custody_verified=true
       AND a.observed_at BETWEEN clock_timestamp()-interval '15 minutes' AND clock_timestamp()
       AND a.expires_at>clock_timestamp()
   ) THEN
     RAISE EXCEPTION 'V81_INDEPENDENT_WORKLOAD_ATTESTATION_REQUIRED' USING ERRCODE='42501';
   END IF;
 END IF;
 RETURN NEW;
END
$fn$;
DROP TRIGGER IF EXISTS v81_independent_worker_promotion_gate
 ON optionx_private.v79_worker_public_identity;
CREATE TRIGGER v81_independent_worker_promotion_gate
 BEFORE INSERT OR UPDATE OF registration_state,key_fingerprint_sha256
 ON optionx_private.v79_worker_public_identity
 FOR EACH ROW EXECUTE FUNCTION optionx_private.v81_block_unattested_worker_promotion();
REVOKE ALL ON FUNCTION optionx_private.v81_block_unattested_worker_promotion()
 FROM PUBLIC,anon,authenticated,service_role;

-- Critical: verifier independently checks active attestation each request.
-- Merely setting registration_state='VERIFIED' must not suffice.
CREATE OR REPLACE FUNCTION public.optionx_v79_worker_verification_key(
 p_owner uuid, p_worker uuid
) RETURNS TABLE(public_key_pem text,key_fingerprint_sha256 text)
LANGUAGE sql VOLATILE SECURITY DEFINER
SET search_path=pg_catalog,optionx_private
AS $fn$
 SELECT k.public_key_pem,k.key_fingerprint_sha256
 FROM optionx_private.v79_worker_public_identity k
 JOIN optionx_private.v81_independent_worker_attestations a
   ON a.owner_id=k.owner_id AND a.worker_id=k.worker_id
   AND a.public_key_fingerprint_sha256=k.key_fingerprint_sha256
 WHERE k.owner_id=p_owner AND k.worker_id=p_worker
   AND k.registration_state='VERIFIED'
   AND k.approved_at<=clock_timestamp()
   AND k.expires_at>clock_timestamp()
   AND a.independent_reviewer_id<>k.owner_id
   AND a.process_identity_verified=true
   AND a.key_custody_verified=true
   AND a.observed_at BETWEEN clock_timestamp()-interval '15 minutes' AND clock_timestamp()
   AND a.expires_at>clock_timestamp()
 LIMIT 1
$fn$;

CREATE OR REPLACE FUNCTION public.optionx_v79_consume_worker_nonce(
 p_owner uuid,p_worker uuid,p_nonce uuid
) RETURNS boolean
LANGUAGE plpgsql SECURITY DEFINER
SET search_path=pg_catalog,optionx_private
AS $fn$
DECLARE v_inserted bigint:=0;
BEGIN
 IF p_owner IS NULL OR p_worker IS NULL OR p_nonce IS NULL THEN RETURN false; END IF;
 -- Use the *same* independent-attestation admission predicate as key lookup.
 IF NOT EXISTS(
  SELECT 1 FROM optionx_private.v79_worker_public_identity k
  JOIN optionx_private.v81_independent_worker_attestations a
    ON a.owner_id=k.owner_id AND a.worker_id=k.worker_id
    AND a.public_key_fingerprint_sha256=k.key_fingerprint_sha256
  WHERE k.owner_id=p_owner AND k.worker_id=p_worker
    AND k.registration_state='VERIFIED'
    AND k.approved_at<=clock_timestamp()
    AND k.expires_at>clock_timestamp()
    AND a.independent_reviewer_id<>k.owner_id
    AND a.process_identity_verified AND a.key_custody_verified
    AND a.observed_at BETWEEN clock_timestamp()-interval '15 minutes' AND clock_timestamp()
    AND a.expires_at>clock_timestamp()
 ) THEN RETURN false; END IF;
 INSERT INTO optionx_private.v79_worker_signed_nonces(owner_id,worker_id,nonce)
 VALUES(p_owner,p_worker,p_nonce)
 ON CONFLICT DO NOTHING;
 GET DIAGNOSTICS v_inserted=ROW_COUNT;
 RETURN v_inserted=1;
END
$fn$;
-- Preserve exact prior privileges on redefinition.
REVOKE ALL ON FUNCTION public.optionx_v79_worker_verification_key(uuid,uuid)
 FROM PUBLIC,anon,authenticated;
GRANT EXECUTE ON FUNCTION public.optionx_v79_worker_verification_key(uuid,uuid) TO service_role;
REVOKE ALL ON FUNCTION public.optionx_v79_consume_worker_nonce(uuid,uuid,uuid)
 FROM PUBLIC,anon,authenticated;
GRANT EXECUTE ON FUNCTION public.optionx_v79_consume_worker_nonce(uuid,uuid,uuid) TO service_role;
COMMIT;
