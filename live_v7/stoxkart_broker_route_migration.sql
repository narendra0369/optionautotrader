-- OptionX V7 Stoxkart market-routing preference extension.
-- This small change affects ONLY stored broker labels; NOT credentials or orders.
-- Existing RLS owner policies, PK, FK and CHECK on market are preserved.
-- Was 0 saved route rows when reviewed on 2026-11-24.
BEGIN;
ALTER TABLE public.optionx_broker_routes
  DROP CONSTRAINT optionx_broker_route_match,
  DROP CONSTRAINT optionx_broker_routes_broker_check;
ALTER TABLE public.optionx_broker_routes
  ADD CONSTRAINT optionx_broker_routes_broker_check
    CHECK (broker IN ('Angel','Stoxkart','Delta')),
  ADD CONSTRAINT optionx_broker_route_match
    CHECK ((market IN ('NIFTY','BANKNIFTY') AND broker IN ('Angel','Stoxkart'))
            OR (market='BTC' AND broker='Delta'));
COMMIT;

-- Rollback (apply separately if ever necessary and after migrating any saved
-- Stoxkart route labels back to Angel One):
-- BEGIN;
-- UPDATE public.optionx_broker_routes
-- SET broker='Angel'
-- WHERE broker='Stoxkart';
-- ALTER TABLE public.optionx_broker_routes
--   DROP CONSTRAINT optionx_broker_route_match,
--   DROP CONSTRAINT optionx_broker_routes_broker_check;
-- ALTER TABLE public.optionx_broker_routes
--   ADD CONSTRAINT optionx_broker_routes_broker_check
--     CHECK (broker IN ('Angel','Delta')),
--   ADD CONSTRAINT optionx_broker_route_match
--     CHECK ((market IN ('NIFTY','BANKNIFTY') AND broker='Angel')
--            OR (market='BTC' AND broker='Delta'));
-- COMMIT;
