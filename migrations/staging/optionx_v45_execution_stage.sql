-- OptionX V45: ISOLATED STAGING-ONLY migration. Never apply to existing
-- Supabase/production database or optionx_private schema.
-- Execute ONLY on a fresh dedicated PostgreSQL staging DB with an isolated
-- non-production credential and an audited explicit operator step.
BEGIN;
CREATE SCHEMA IF NOT EXISTS optionx_exec_stage;
REVOKE ALL ON SCHEMA optionx_exec_stage FROM PUBLIC;
CREATE TABLE IF NOT EXISTS optionx_exec_stage.guard (
  owner_id uuid PRIMARY KEY,
  state text NOT NULL DEFAULT 'STOPPED'
    CHECK (state = 'STOPPED'),
  new_orders_blocked boolean NOT NULL DEFAULT TRUE
    CHECK (new_orders_blocked = TRUE),
  changed_at timestamptz NOT NULL DEFAULT now()
);
CREATE TABLE IF NOT EXISTS optionx_exec_stage.order_intents (
  owner_id uuid NOT NULL,
  intent_key text NOT NULL CHECK (intent_key ~ '^[A-Za-z0-9_-]{8,96}$'),
  payload_hash char(64) NOT NULL CHECK (payload_hash ~ '^[0-9a-f]{64}$'),
  symbol text NOT NULL CHECK (length(symbol) BETWEEN 6 AND 80),
  token text NOT NULL CHECK (token ~ '^[0-9]+$'),
  side text NOT NULL CHECK (side IN ('BUY','SELL')),
  order_type text NOT NULL CHECK (order_type IN ('LIMIT','STOPLOSS_LIMIT')),
  quantity integer NOT NULL CHECK (quantity > 0),
  price numeric(16,4) NOT NULL CHECK (price > 0),
  state text NOT NULL DEFAULT 'RESERVED_UNSENT'
    CHECK (state IN ('RESERVED_UNSENT','MAY_HAVE_SENT_RECONCILE',
                    'BROKER_RECONCILIATION_REQUIRED','CLOSED_REVIEWED')),
  created_at timestamptz NOT NULL DEFAULT now(),
  PRIMARY KEY(owner_id,intent_key)
);
CREATE TABLE IF NOT EXISTS optionx_exec_stage.order_events (
  event_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  owner_id uuid NOT NULL,
  intent_key text NOT NULL,
  event text NOT NULL CHECK(event IN ('RESERVED','SEALED_UNKNOWN',
     'BROKER_RECONCILIATION_REQUIRED','CLOSED_REVIEWED')),
  created_at timestamptz NOT NULL DEFAULT now(),
  FOREIGN KEY (owner_id,intent_key)
    REFERENCES optionx_exec_stage.order_intents(owner_id,intent_key)
);
CREATE INDEX IF NOT EXISTS ix_stage_intents_owner_state
 ON optionx_exec_stage.order_intents(owner_id,state);
-- Defense in depth: staging-only guard cannot be changed to RUNNING,
-- and no SQL function grants a broker dispatch right.
COMMIT;
