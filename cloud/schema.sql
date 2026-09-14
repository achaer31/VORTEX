-- DRAFT for a dedicated, approved project. This is not a provisioned database.
-- One current telemetry snapshot; no broker identity, credentials, orders, or history.
begin;

create table public.vortex_latest (
  singleton boolean primary key default true check (singleton),
  session_id uuid not null,
  session_started_at timestamptz not null,
  sequence bigint not null check (sequence between 0 and 9007199254740991),
  produced_at timestamptz not null,
  received_at timestamptz not null default clock_timestamp(),
  snapshot jsonb not null,
  check (produced_at >= session_started_at),
  check (jsonb_typeof(snapshot) = 'object'),
  check (snapshot->>'mode' = 'demo' and snapshot->'schemaVersion' = '1'::jsonb)
);

alter table public.vortex_latest enable row level security;
alter table public.vortex_latest force row level security;
revoke all on table public.vortex_latest from public, anon, authenticated;
grant usage on schema public to service_role;
grant select, insert, update on table public.vortex_latest to service_role;
-- Deliberately no policies for anon/authenticated. service_role bypasses RLS.

create function public.vortex_ingest_snapshot(p_snapshot jsonb)
returns jsonb
language plpgsql
security invoker
set search_path = ''
as $function$
declare
  v_session uuid;
  v_started timestamptz;
  v_sequence bigint;
  v_produced timestamptz;
  v_received timestamptz;
  v_current public.vortex_latest%rowtype;
  v_clock timestamptz := pg_catalog.clock_timestamp();
begin
  -- The Edge function applies the complete nested allowlist. These checks also
  -- reject invalid mode/time/order at the transactional persistence boundary.
  if p_snapshot is null or pg_catalog.jsonb_typeof(p_snapshot) <> 'object'
     or p_snapshot->>'mode' is distinct from 'demo'
     or p_snapshot->'schemaVersion' is distinct from '1'::jsonb
     or pg_catalog.octet_length(p_snapshot::text) > 131072
     or pg_catalog.jsonb_typeof(p_snapshot->'sequence') is distinct from 'number'
     or (p_snapshot->>'sequence') !~ '^[0-9]+$' then
    raise exception 'invalid snapshot' using errcode = '22023';
  end if;
  v_session := (p_snapshot->>'sessionId')::uuid;
  v_started := (p_snapshot->>'sessionStartedAt')::timestamptz;
  v_sequence := (p_snapshot->>'sequence')::bigint;
  v_produced := (p_snapshot->>'producedAt')::timestamptz;
  if v_session is null or v_started is null or v_sequence is null or v_produced is null
     or v_sequence < 0 or v_sequence > 9007199254740991
     or not pg_catalog.isfinite(v_started) or not pg_catalog.isfinite(v_produced)
     or v_produced < v_started or v_produced < v_clock - interval '120 seconds'
     or v_produced > v_clock + interval '30 seconds' then
    raise exception 'invalid snapshot time or sequence' using errcode = '22023';
  end if;

  insert into public.vortex_latest as existing
    (singleton, session_id, session_started_at, sequence, produced_at, received_at, snapshot)
  values
    (true, v_session, v_started, v_sequence, v_produced, v_clock, p_snapshot)
  on conflict (singleton) do update set
    session_id = excluded.session_id,
    session_started_at = excluded.session_started_at,
    sequence = excluded.sequence,
    produced_at = excluded.produced_at,
    received_at = excluded.received_at,
    snapshot = excluded.snapshot
  where
    (excluded.session_id = existing.session_id
     and excluded.session_started_at = existing.session_started_at
     and excluded.sequence > existing.sequence
     and excluded.produced_at >= existing.produced_at)
    or
    (excluded.session_id <> existing.session_id
     and excluded.session_started_at > existing.produced_at
     and excluded.produced_at > existing.produced_at)
  returning received_at into v_received;

  if found then
    return pg_catalog.jsonb_build_object('reason', 'accepted', 'receivedAt', v_received);
  end if;

  select * into v_current from public.vortex_latest where singleton = true;
  if v_current.snapshot = p_snapshot then
    -- Retries never refresh received_at, so replay cannot fake a healthy heartbeat.
    return pg_catalog.jsonb_build_object('reason', 'duplicate', 'receivedAt', v_current.received_at);
  end if;
  return pg_catalog.jsonb_build_object('reason', 'not_newer', 'receivedAt', v_current.received_at);
end;
$function$;

revoke all on function public.vortex_ingest_snapshot(jsonb) from public, anon, authenticated;
grant execute on function public.vortex_ingest_snapshot(jsonb) to service_role;
comment on table public.vortex_latest is 'Private latest demo telemetry. No anon/authenticated access. Not an execution or audit-history store.';
commit;
