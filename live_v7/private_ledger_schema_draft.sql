-- OptionX V7 DURABLE LEDGER SCHEMA DRAFT — NOT APPLIED.
-- Review, stage, backup and test before installing in Supabase.
-- The production V6 DB must remain unchanged during deferred testing.
-- Sensitive broker credentials/tokens must NEVER be stored in these tables.
-- All tables are in a non-exposed, private schema. Not callable from frontend.
BEGIN;

CREATE SCHEMA IF NOT EXISTS optionx_private;
REVOKE ALL ON SCHEMA optionx_private FROM PUBLIC, anon, authenticated;
GRANT USAGE ON SCHEMA optionx_private TO service_role;

CREATE TABLE IF NOT EXISTS optionx_private.owner_brokers (
    owner_id uuid NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    broker text NOT NULL CHECK (broker IN ('Angel', 'Delta')),
    account_fingerprint_sha256 char(64) NOT NULL CHECK (account_fingerprint_sha256 ~ '^[0-9a-f]{64}$'),
    connected_at timestamptz,
    snapshot_verified_at timestamptz,
    updated_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY(owner_id, broker)
);

-- V7 has NO ON state. A later audited migration would be required to add one.
CREATE TABLE IF NOT EXISTS optionx_private.engine_guard (
    owner_id uuid PRIMARY KEY REFERENCES auth.users(id) ON DELETE CASCADE,
    state text NOT NULL DEFAULT 'STOPPED'
        CHECK (state IN ('STOPPED','RESET_REQUESTED','REVIEW_REQUIRED')),
    new_entries_blocked boolean NOT NULL DEFAULT true CHECK (new_entries_blocked = true),
    revision bigint NOT NULL DEFAULT 0 CHECK (revision >= 0),
    updated_at timestamptz NOT NULL DEFAULT now(),
    stop_reason text NOT NULL DEFAULT 'DEFAULT_DENY'
        CHECK (length(stop_reason) BETWEEN 1 AND 160)
);

CREATE TABLE IF NOT EXISTS optionx_private.order_intents (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    owner_id uuid NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    trade_day_ist date NOT NULL,
    idempotency_key varchar(96) NOT NULL
        CHECK (idempotency_key ~ '^[A-Za-z0-9_-]{8,96}$'),
    broker text NOT NULL CHECK (broker IN ('Angel','Delta')),
    market text NOT NULL CHECK (market IN ('NIFTY','BANKNIFTY','BTC')),
    instrument_token varchar(64) NOT NULL,
    contract_symbol varchar(72) NOT NULL,
    contract_kind varchar(16) NOT NULL,
    side text NOT NULL CHECK (side = 'ENTRY_BUY'),
    quantity bigint NOT NULL CHECK(quantity > 0),
    planned_entry numeric(25, 10) NOT NULL CHECK(planned_entry > 0),
    planned_stop numeric(25, 10) NOT NULL CHECK(planned_stop > 0),
    planned_target numeric(25, 10) NOT NULL CHECK(planned_target > 0),
    estimated_max_loss numeric(25, 10) NOT NULL CHECK(estimated_max_loss > 0),
    state text NOT NULL DEFAULT 'PREPARED'
        CHECK(state IN (
            'PREPARED','LOCAL_REJECTED','LOCAL_CANCELLED',
            'AWAITING_BROKER_ACK','BROKER_REJECTED','BROKER_ACCEPTED',
            'PARTIALLY_FILLED','FILLED','CANCEL_REQUESTED','CANCELLED',
            'UNKNOWN_BROKER_OUTCOME','MANUAL_REVIEW'
        )),
    external_broker_order_id varchar(96),
    filled_quantity bigint NOT NULL DEFAULT 0 CHECK(filled_quantity >= 0 AND filled_quantity <= quantity),
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE(owner_id, broker, trade_day_ist, idempotency_key),
    UNIQUE(owner_id, broker, external_broker_order_id)
);
CREATE INDEX IF NOT EXISTS optionx_intents_owner_day_idx
    ON optionx_private.order_intents (owner_id, trade_day_ist, created_at DESC);
CREATE INDEX IF NOT EXISTS optionx_intents_unresolved_idx
    ON optionx_private.order_intents (owner_id, broker, state)
    WHERE state IN (
        'AWAITING_BROKER_ACK','BROKER_ACCEPTED','PARTIALLY_FILLED',
        'CANCEL_REQUESTED','UNKNOWN_BROKER_OUTCOME','MANUAL_REVIEW'
    );

CREATE TABLE IF NOT EXISTS optionx_private.order_events (
    event_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    order_intent_id uuid NOT NULL REFERENCES optionx_private.order_intents(id),
    owner_id uuid NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    source_event_key varchar(96) NOT NULL,
    previous_state varchar(40),
    next_state varchar(40) NOT NULL,
    filled_quantity bigint,
    reason_code varchar(64) NOT NULL,
    occurred_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE(owner_id, source_event_key),
    CHECK (filled_quantity IS NULL OR filled_quantity >= 0),
    CHECK (reason_code ~ '^[A-Z0-9_]{2,64}$')
);
CREATE INDEX IF NOT EXISTS optionx_events_intent_idx ON optionx_private.order_events
    (order_intent_id, occurred_at);

CREATE TABLE IF NOT EXISTS optionx_private.broker_position_snapshots (
    id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    owner_id uuid NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    broker text NOT NULL CHECK(broker IN ('Angel','Delta')),
    instrument_token varchar(64) NOT NULL,
    contract_symbol varchar(72) NOT NULL,
    net_quantity bigint NOT NULL,
    snapshot_at timestamptz NOT NULL,
    saved_at timestamptz NOT NULL DEFAULT now(),
    authenticated_source boolean NOT NULL CHECK(authenticated_source = true),
    UNIQUE(owner_id, broker, instrument_token, snapshot_at)
);
CREATE INDEX IF NOT EXISTS optionx_position_owner_time_idx
    ON optionx_private.broker_position_snapshots (owner_id, broker, snapshot_at DESC);

CREATE TABLE IF NOT EXISTS optionx_private.risk_day_snapshot (
    owner_id uuid NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    broker text NOT NULL CHECK(broker IN ('Angel','Delta')),
    day_ist date NOT NULL,
    number_of_entries int NOT NULL CHECK(number_of_entries >= 0 AND number_of_entries <= 2),
    realized_pnl numeric(25,10) NOT NULL,
    open_risk_estimate numeric(25,10) NOT NULL CHECK(open_risk_estimate >= 0),
    verified_at timestamptz NOT NULL,
    PRIMARY KEY (owner_id, broker, day_ist)
);

CREATE TABLE IF NOT EXISTS optionx_private.audit_events (
    audit_event_id varchar(96) NOT NULL PRIMARY KEY,
    owner_id uuid NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    broker text NOT NULL CHECK(broker IN ('Angel','Delta','NONE')),
    market text NOT NULL CHECK(market IN ('NIFTY','BANKNIFTY','BTC','NONE')),
    event_type varchar(64) NOT NULL,
    reason_code varchar(64) NOT NULL,
    previous_digest char(64) NOT NULL CHECK(previous_digest ~ '^[a-f0-9]{64}$'),
    digest char(64) NOT NULL CHECK(digest ~ '^[a-f0-9]{64}$'),
    created_at timestamptz NOT NULL DEFAULT now(),
    CHECK (event_type ~ '^[A-Z0-9_]{2,64}$' AND reason_code ~ '^[A-Z0-9_]{2,64}$')
);
CREATE INDEX IF NOT EXISTS optionx_audit_owner_time_idx
    ON optionx_private.audit_events(owner_id, created_at, audit_event_id);

CREATE TABLE IF NOT EXISTS optionx_private.audit_heads (
    owner_id uuid PRIMARY KEY REFERENCES auth.users(id) ON DELETE CASCADE,
    head_digest char(64) NOT NULL CHECK(head_digest ~ '^[a-f0-9]{64}$'),
    revision bigint NOT NULL CHECK(revision >= 0),
    updated_at timestamptz NOT NULL DEFAULT now()
);

-- DB-level append-only: no retroactive modification of event rows through
-- normal clients. Independent head anchoring and backups remain required.
CREATE OR REPLACE FUNCTION optionx_private.reject_event_mutation()
RETURNS trigger LANGUAGE plpgsql SECURITY INVOKER SET search_path = ''
AS $fn$
BEGIN
    RAISE EXCEPTION 'APPEND_ONLY_EVENT_TABLE';
END
$fn$;

DROP TRIGGER IF EXISTS lock_order_events ON optionx_private.order_events;
CREATE TRIGGER lock_order_events
BEFORE UPDATE OR DELETE ON optionx_private.order_events
FOR EACH ROW EXECUTE FUNCTION optionx_private.reject_event_mutation();

DROP TRIGGER IF EXISTS lock_audit_events ON optionx_private.audit_events;
CREATE TRIGGER lock_audit_events
BEFORE UPDATE OR DELETE ON optionx_private.audit_events
FOR EACH ROW EXECUTE FUNCTION optionx_private.reject_event_mutation();

-- Defense in depth: service-only access in a non-exposed schema.
ALTER TABLE optionx_private.owner_brokers ENABLE ROW LEVEL SECURITY;
ALTER TABLE optionx_private.engine_guard ENABLE ROW LEVEL SECURITY;
ALTER TABLE optionx_private.order_intents ENABLE ROW LEVEL SECURITY;
ALTER TABLE optionx_private.order_events ENABLE ROW LEVEL SECURITY;
ALTER TABLE optionx_private.broker_position_snapshots ENABLE ROW LEVEL SECURITY;
ALTER TABLE optionx_private.risk_day_snapshot ENABLE ROW LEVEL SECURITY;
ALTER TABLE optionx_private.audit_events ENABLE ROW LEVEL SECURITY;
ALTER TABLE optionx_private.audit_heads ENABLE ROW LEVEL SECURITY;

REVOKE ALL ON ALL TABLES IN SCHEMA optionx_private FROM PUBLIC, anon, authenticated;
REVOKE ALL ON ALL SEQUENCES IN SCHEMA optionx_private FROM PUBLIC, anon, authenticated;
GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA optionx_private TO service_role;
GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA optionx_private TO service_role;
REVOKE ALL ON FUNCTION optionx_private.reject_event_mutation() FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION optionx_private.reject_event_mutation() TO service_role;

-- RLS has no permissive policies; ordinary browser sessions may not access
-- this schema even if schema exposure is accidentally broadened. The trusted
-- backend MUST enforce the correct verified owner_id on every operation.
-- Supabase service_role bypasses RLS: never expose its key to a browser!
COMMIT;

-- NOT RUN. Before applying to ANY database:
-- 1. Inspect and backup production database.
-- 2. Confirm secure server vault and least-privilege DB access.
-- 3. Audit event/owner foreign-key consistency and SQL trigger permissions.
-- 4. Review network, compliance, recovery, concurrency and migration strategy.
-- 5. Explicit owner approval for schema changes in production.
