-- Read-only verification after applying schema.sql to the approved dedicated DB.
-- Expected: RLS and FORCE RLS true; no policies; public client privileges false;
-- service_role SELECT/INSERT/UPDATE and RPC EXECUTE true; service_role BYPASSRLS true.
select c.relrowsecurity, c.relforcerowsecurity
from pg_catalog.pg_class c join pg_catalog.pg_namespace n on n.oid = c.relnamespace
where n.nspname = 'public' and c.relname = 'vortex_latest';
select * from pg_catalog.pg_policies where schemaname = 'public' and tablename = 'vortex_latest';
select r.role_name,
  has_table_privilege(r.role_name, 'public.vortex_latest', 'SELECT') as can_select,
  has_table_privilege(r.role_name, 'public.vortex_latest', 'INSERT') as can_insert,
  has_table_privilege(r.role_name, 'public.vortex_latest', 'UPDATE') as can_update,
  has_function_privilege(r.role_name, 'public.vortex_ingest_snapshot(jsonb)', 'EXECUTE') as can_ingest
from (values ('anon'), ('authenticated'), ('service_role')) r(role_name);
select rolname, rolbypassrls from pg_catalog.pg_roles where rolname = 'service_role';
