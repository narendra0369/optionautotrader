-- Isolated OPTIONX run history table. Existing ZELQORIS marketplace schema remains unchanged.
-- Supabase Auth users are shared at the project level; consider a dedicated project for complete isolation.
CREATE TABLE IF NOT EXISTS public.optionx_backtest_runs (
 id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
 user_id uuid NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
 market text NOT NULL CHECK(market IN ('NIFTY','BANKNIFTY','BTC')),
 source text NOT NULL,
 bars integer NOT NULL CHECK(bars>=100 AND bars<=120000),
 screened integer NOT NULL CHECK(screened BETWEEN 1 AND 200000),
 viable integer NOT NULL CHECK(viable BETWEEN 0 AND 200000),
 split_time timestamptz NOT NULL,
 training_bars integer NOT NULL CHECK(training_bars>=0),
 test_bars integer NOT NULL CHECK(test_bars>=0),
 cost_bps numeric NOT NULL CHECK(cost_bps BETWEEN 0 AND 500),
 results jsonb NOT NULL,
 created_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS optionx_backtest_runs_owner_date_idx ON public.optionx_backtest_runs(user_id, created_at DESC);
ALTER TABLE public.optionx_backtest_runs ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON public.optionx_backtest_runs FROM anon;
GRANT SELECT, INSERT, DELETE ON public.optionx_backtest_runs TO authenticated;
DROP POLICY IF EXISTS optionx_select_own ON public.optionx_backtest_runs;
CREATE POLICY optionx_select_own ON public.optionx_backtest_runs FOR SELECT TO authenticated USING ((SELECT auth.uid()) = user_id);
DROP POLICY IF EXISTS optionx_insert_own ON public.optionx_backtest_runs;
CREATE POLICY optionx_insert_own ON public.optionx_backtest_runs FOR INSERT TO authenticated WITH CHECK ((SELECT auth.uid()) = user_id);
DROP POLICY IF EXISTS optionx_delete_own ON public.optionx_backtest_runs;
CREATE POLICY optionx_delete_own ON public.optionx_backtest_runs FOR DELETE TO authenticated USING ((SELECT auth.uid()) = user_id);
