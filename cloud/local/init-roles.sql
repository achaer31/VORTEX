-- Local fresh database only; Supabase already provides these three roles.
create role anon nologin;
create role authenticated nologin;
create role service_role nologin bypassrls;
create role vortex_rest login noinherit;
grant service_role to vortex_rest;
-- psql reads the secret as a variable, avoiding a password in process arguments.
\set rest_password `cat /run/secrets/rest_password`
alter role vortex_rest password :'rest_password';
\unset rest_password
