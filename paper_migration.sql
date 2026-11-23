-- OptionX V3 isolated paper simulation state (not live broker ledger)
-- Uses Supabase Auth user ownership only. No service role needed in web clients.
CREATE TABLE IF NOT EXISTS public.optionx_paper_accounts (
 user_id uuid NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
 market text NOT NULL CHECK (market IN ('NIFTY','BANKNIFTY','BTC')),
 timeframe text NOT NULL CHECK (timeframe IN ('1m','5m','15m','30m','1h','4h','1d')),
 strategy_id integer NOT NULL CHECK (strategy_id BETWEEN 1 AND 200000),
 config jsonb NOT NULL CHECK (jsonb_typeof(config) = 'object'),
 state jsonb NOT NULL CHECK (jsonb_typeof(state) = 'object'),
 version bigint NOT NULL DEFAULT 1 CHECK (version >= 1),
 updated_at timestamptz NOT NULL DEFAULT now(),
 PRIMARY KEY (user_id,market)
);
ALTER TABLE public.optionx_paper_accounts ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON public.optionx_paper_accounts FROM PUBLIC, anon;
GRANT SELECT, INSERT, UPDATE ON public.optionx_paper_accounts TO authenticated;
DROP POLICY IF EXISTS optionx_paper_read_own ON public.optionx_paper_accounts;
CREATE POLICY optionx_paper_read_own ON public.optionx_paper_accounts FOR SELECT TO authenticated
 USING ((SELECT auth.uid()) = user_id);
DROP POLICY IF EXISTS optionx_paper_insert_own ON public.optionx_paper_accounts;
CREATE POLICY optionx_paper_insert_own ON public.optionx_paper_accounts FOR INSERT TO authenticated
 WITH CHECK ((SELECT auth.uid()) = user_id);
DROP POLICY IF EXISTS optionx_paper_update_own ON public.optionx_paper_accounts;
CREATE POLICY optionx_paper_update_own ON public.optionx_paper_accounts FOR UPDATE TO authenticated
 USING ((SELECT auth.uid()) = user_id) WITH CHECK ((SELECT auth.uid()) = user_id);
