-- OPTIONX V64 | additive fail-closed PostgreSQL foundation
-- Applied to Supabase project yghijfzwsvmzaffllszl on 2026-11-26
-- No changes to existing owner, broker, ZELQORIS or execution tables.
CREATE TABLE IF NOT EXISTS optionx_private.v64_worker_fence (
 owner_id uuid PRIMARY KEY REFERENCES auth.users(id),
 worker_identity uuid NOT NULL,
 fencing_epoch bigint NOT NULL CHECK (fencing_epoch > 0),
 lease_expires_at timestamptz NOT NULL,
 updated_at timestamptz NOT NULL DEFAULT now()
);
CREATE TABLE IF NOT EXISTS optionx_private.v64_risk_reservations (
 reservation_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
 owner_id uuid NOT NULL REFERENCES auth.users(id),
 broker text NOT NULL CHECK (broker IN ('Angel','Delta')),
 trade_day_ist date NOT NULL,
 intent_id uuid NOT NULL,
 idempotency_key text NOT NULL CHECK (idempotency_key ~ '^[A-Za-z0-9_-]{8,96}$'),
 worker_identity uuid NOT NULL,
 fencing_epoch bigint NOT NULL CHECK(fencing_epoch > 0),
 reserved_max_loss numeric NOT NULL CHECK (reserved_max_loss > 0),
 state text NOT NULL DEFAULT 'STAGING_HELD'
   CHECK (state IN ('STAGING_HELD','STAGING_UNCERTAIN','STAGING_RELEASED')),
 created_at timestamptz NOT NULL DEFAULT now(),
 UNIQUE (owner_id,broker,trade_day_ist,idempotency_key),
 UNIQUE (owner_id,intent_id),
 FOREIGN KEY (intent_id,owner_id) REFERENCES optionx_private.order_intents(id,owner_id)
);
CREATE INDEX IF NOT EXISTS v64_risk_reservations_owner_day_idx
 ON optionx_private.v64_risk_reservations(owner_id,broker,trade_day_ist);
ALTER TABLE optionx_private.v64_worker_fence ENABLE ROW LEVEL SECURITY;
ALTER TABLE optionx_private.v64_risk_reservations ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON TABLE optionx_private.v64_worker_fence FROM PUBLIC, anon, authenticated;
REVOKE ALL ON TABLE optionx_private.v64_risk_reservations FROM PUBLIC, anon, authenticated;
COMMENT ON TABLE optionx_private.v64_worker_fence
 IS 'V64 fail-closed leader fencing staging primitive; no active worker authorized';
COMMENT ON TABLE optionx_private.v64_risk_reservations
 IS 'V64 additive staging-only risk reservations; never confers broker order authorization';
