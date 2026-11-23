-- OptionX V5: only non-sensitive broker routing preference; no keys, tokens,
-- credentials, API secrets, trading permissions or execution flags are stored.
CREATE TABLE IF NOT EXISTS public.optionx_broker_routes (
 user_id uuid NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
 market text NOT NULL CHECK (market IN ('NIFTY','BANKNIFTY','BTC')),
 broker text NOT NULL CHECK (broker IN ('Angel','Delta')),
 updated_at timestamptz NOT NULL DEFAULT now(),
 PRIMARY KEY (user_id, market),
 CONSTRAINT optionx_broker_route_match CHECK (
   (market IN ('NIFTY','BANKNIFTY') AND broker = 'Angel')
   OR (market = 'BTC' AND broker = 'Delta')
 )
);
ALTER TABLE public.optionx_broker_routes ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON TABLE public.optionx_broker_routes FROM PUBLIC, anon;
GRANT SELECT, INSERT, UPDATE, DELETE ON TABLE public.optionx_broker_routes TO authenticated;
DROP POLICY IF EXISTS optionx_routes_select_own ON public.optionx_broker_routes;
CREATE POLICY optionx_routes_select_own ON public.optionx_broker_routes FOR SELECT TO authenticated
 USING ((SELECT auth.uid()) = user_id);
DROP POLICY IF EXISTS optionx_routes_insert_own ON public.optionx_broker_routes;
CREATE POLICY optionx_routes_insert_own ON public.optionx_broker_routes FOR INSERT TO authenticated
 WITH CHECK ((SELECT auth.uid()) = user_id);
DROP POLICY IF EXISTS optionx_routes_update_own ON public.optionx_broker_routes;
CREATE POLICY optionx_routes_update_own ON public.optionx_broker_routes FOR UPDATE TO authenticated
 USING ((SELECT auth.uid()) = user_id)
 WITH CHECK ((SELECT auth.uid()) = user_id);
DROP POLICY IF EXISTS optionx_routes_delete_own ON public.optionx_broker_routes;
CREATE POLICY optionx_routes_delete_own ON public.optionx_broker_routes FOR DELETE TO authenticated
 USING ((SELECT auth.uid()) = user_id);
