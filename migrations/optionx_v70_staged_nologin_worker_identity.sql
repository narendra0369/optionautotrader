-- V70 staged database identity ONLY. Applied on 2026-11-26.
-- Cannot authenticate or execute any OptionX production function.
DO $$
BEGIN
 IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname='optionx_execution_worker') THEN
  CREATE ROLE optionx_execution_worker NOLOGIN NOINHERIT NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION;
 END IF;
 IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname='optionx_execution_worker' AND (rolcanlogin OR rolsuper OR rolcreaterole)) THEN
  RAISE EXCEPTION 'UNSAFE_EXISTING_OPTIONX_ROLE';
 END IF;
END $$;
REVOKE ALL ON SCHEMA optionx_private FROM optionx_execution_worker;
REVOKE ALL ON ALL TABLES IN SCHEMA optionx_private FROM optionx_execution_worker;
REVOKE ALL ON ALL FUNCTIONS IN SCHEMA optionx_private FROM optionx_execution_worker;
COMMENT ON ROLE optionx_execution_worker IS 'OptionX V70 staged NOLOGIN principal. No credentials/privileges/production certification. Provision only after scoped access and workload-auth review.';
