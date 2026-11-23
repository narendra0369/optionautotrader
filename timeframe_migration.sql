-- Non-destructive OPTIONX-only addition; ZELQORIS tables are unchanged.
ALTER TABLE public.optionx_backtest_runs
 ADD COLUMN IF NOT EXISTS timeframe text NOT NULL DEFAULT '15m';
ALTER TABLE public.optionx_backtest_runs
 DROP CONSTRAINT IF EXISTS optionx_runs_timeframe_allowed;
ALTER TABLE public.optionx_backtest_runs
 ADD CONSTRAINT optionx_runs_timeframe_allowed CHECK (timeframe IN ('1m','5m','15m','30m','1h','4h','1d'));
