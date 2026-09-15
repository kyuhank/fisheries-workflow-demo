begin;
create table if not exists public.paper_sets (set_id text primary key, year integer not null, vessel text not null, hooks integer check(hooks>0), catch_n integer check(catch_n>=0));
create table if not exists public.paper_catches (year integer primary key, catch_t double precision check(catch_t>=0));
create table if not exists public.paper_sessions (id uuid primary key, token_hash text not null, created_at timestamptz default now(), touched_at timestamptz default now(), checkpoint text, state jsonb, accepted_year integer);
alter table public.paper_sessions add column if not exists bundle text;
create table if not exists public.paper_runs (id uuid primary key, session_id uuid references public.paper_sessions on delete cascade, created_at timestamptz default now(), status text default 'queued', start_job text not null, settings jsonb not null, handover text not null, transfer_count integer default 0, connected boolean default false, github_run text, commit_sha text, error text, result jsonb);
alter table public.paper_runs add column if not exists scope text not null default 'workflow' check(scope in ('workflow','job'));
create unique index if not exists paper_one_active_per_session on public.paper_runs(session_id) where status in ('queued','running','handover');
create table if not exists public.paper_events (id bigint generated always as identity primary key, request_id uuid references public.paper_runs on delete cascade, event jsonb not null);
create table if not exists public.paper_outputs (session_id uuid references public.paper_sessions on delete cascade, job text, output jsonb not null, primary key(session_id,job));
create table if not exists public.paper_limits (id boolean primary key default true check(id), day date default current_date, count integer default 0, last_request timestamptz);
insert into public.paper_limits(id) values(true) on conflict do nothing;
alter table public.paper_sets enable row level security;
alter table public.paper_catches enable row level security;
alter table public.paper_sessions enable row level security;
alter table public.paper_runs enable row level security;
alter table public.paper_events enable row level security;
alter table public.paper_outputs enable row level security;
alter table public.paper_limits enable row level security;
revoke all on public.paper_sets,public.paper_catches,public.paper_sessions,public.paper_runs,public.paper_events,public.paper_outputs,public.paper_limits from anon,authenticated;
create or replace function public.paper_start(p_session uuid,p_request uuid,p_start text,p_settings jsonb,p_handover text) returns void language plpgsql security definer set search_path='' as $$
declare n integer;
begin
 perform 1 from public.paper_limits where id for update;
 update public.paper_runs set status='expired' where status in ('queued','running','handover') and created_at<now()-interval '8 minutes';
 delete from public.paper_sessions s where s.touched_at<now()-interval '10 minutes' and not exists(select 1 from public.paper_runs r where r.session_id=s.id and r.status in ('queued','running','handover'));
 update public.paper_limits set day=current_date,count=0 where day<>current_date;
 if (select count from public.paper_limits where id)>=300 then raise exception 'Daily demonstration limit reached'; end if;
 if (select count(*) from public.paper_runs where status in ('queued','running','handover'))>=3 then raise exception 'Three demonstrations are active; try again shortly'; end if;
 if exists(select 1 from public.paper_runs where session_id=p_session and status in ('queued','running','handover')) then raise exception 'This session already has an active run'; end if;
 delete from public.paper_runs where session_id=p_session;
 insert into public.paper_runs(id,session_id,start_job,settings,handover) values(p_request,p_session,p_start,p_settings,p_handover);
 update public.paper_limits set count=count+1,last_request=now() where id;
 update public.paper_sessions set touched_at=now() where id=p_session;
end $$;
revoke all on function public.paper_start(uuid,uuid,text,jsonb,text) from public,anon,authenticated;
grant execute on function public.paper_start(uuid,uuid,text,jsonb,text) to service_role;

-- Keep the original RPC for already deployed API versions. The required sixth
-- argument selects this overload, and both writes commit in one transaction.
create or replace function public.paper_start(p_session uuid,p_request uuid,p_start text,p_settings jsonb,p_handover text,p_scope text) returns void language plpgsql security definer set search_path='' as $$
begin
 if p_scope is null or p_scope not in ('workflow','job') then raise exception 'Invalid run scope'; end if;
 perform public.paper_start(p_session,p_request,p_start,p_settings,p_handover);
 update public.paper_runs set scope=p_scope where id=p_request;
end $$;
revoke all on function public.paper_start(uuid,uuid,text,jsonb,text,text) from public,anon,authenticated;
grant execute on function public.paper_start(uuid,uuid,text,jsonb,text,text) to service_role;


create table if not exists public.paper_app (
 id boolean primary key default true check(id),
 app_id bigint, private_key text, slug text, setup_hash text, setup_expires timestamptz
);
alter table public.paper_app enable row level security;
revoke all on public.paper_app from public,anon,authenticated;
grant all on public.paper_app to service_role;
create or replace function public.paper_cleanup() returns void language sql security definer set search_path='' as $$
 update public.paper_runs set status='expired' where status in ('queued','running','handover') and created_at<now()-interval '8 minutes';
 delete from public.paper_sessions s where s.touched_at<now()-interval '10 minutes' and not exists(select 1 from public.paper_runs r where r.session_id=s.id and r.status in ('queued','running','handover'));
$$;
revoke all on function public.paper_cleanup from public,anon,authenticated;
grant execute on function public.paper_cleanup to service_role;

-- Atomic runner updates. A repeated operation acknowledges the original write;
-- it never adds an event or replaces newer state a second time.
create table if not exists public.paper_runner_receipts (
 request_id uuid references public.paper_runs on delete cascade,
 operation_id uuid not null, payload_hash text not null,
 primary key(request_id,operation_id)
);
alter table public.paper_runner_receipts enable row level security;
revoke all on public.paper_runner_receipts from public,anon,authenticated;
grant all on public.paper_runner_receipts to service_role;
create or replace function public.paper_runner_write(
 p_request uuid,p_operation uuid,p_action text,p_body jsonb
) returns void language plpgsql security definer set search_path='' as $$
declare
 r public.paper_runs%rowtype;
 fingerprint text := encode(sha256(convert_to(p_action || p_body::text,'UTF8')),'hex');
 previous text;
 pending jsonb;
begin
 if p_operation is null or p_action is null or p_action not in ('event','finish') or p_body is null then
  raise exception 'Invalid runner operation';
 end if;
 select * into r from public.paper_runs where id=p_request for update;
 if not found then raise exception 'Run expired'; end if;
 select payload_hash into previous from public.paper_runner_receipts
  where request_id=p_request and operation_id=p_operation;
 if found then
  if previous<>fingerprint then raise exception 'Operation identifier already used'; end if;
  return;
 end if;
 if r.status not in ('queued','running','handover') then
  raise exception 'Run is no longer active';
 end if;
 if p_action='event' then
  if jsonb_typeof(p_body->'event') is distinct from 'object' or
     jsonb_typeof(p_body->'event'->'state') is distinct from 'string' then
   raise exception 'Invalid job event';
  end if;
  -- An optional setup announcement may arrive after its caller timed out.
  -- Once analysis events exist it is obsolete and must not move the display back.
  if p_body->'event'->>'state'='phase' and
     exists(select 1 from public.paper_events where request_id=p_request) then
   insert into public.paper_runner_receipts(request_id,operation_id,payload_hash)
    values(p_request,p_operation,fingerprint);
   return;
  end if;
  insert into public.paper_events(request_id,event) values(p_request,p_body->'event');
  if p_body->'event'->>'state'<>'phase' then
   -- Independent reporting may continue while another branch awaits files.
   update public.paper_runs set status=case
    when p_body->'event'->>'state'='handover' then 'handover'
    when p_body->'event'->>'state'='received' then 'running'
    when r.status='handover' then 'handover'
    else 'running' end where id=p_request;
  end if;
  if p_body->'output' is not null and p_body->'output'<>'null'::jsonb then
   insert into public.paper_outputs(session_id,job,output)
    values(r.session_id,p_body->'event'->>'job',p_body->'output')
    on conflict(session_id,job) do update set output=excluded.output;
  end if;
  if p_body->'state' is not null and p_body->'state'<>'null'::jsonb then
   update public.paper_sessions set state=p_body->'state',touched_at=now()
    where id=r.session_id;
  end if;
  if p_body->'event'->>'job'='database' and p_body->'event'->>'state'='complete' then
   update public.paper_sessions set accepted_year=(r.settings->>'last_year')::integer
    where id=r.session_id;
  end if;
 else
  if jsonb_typeof(p_body->'pending_events') is distinct from 'array' or
     jsonb_typeof(p_body->'checkpoint') is distinct from 'string' or
     jsonb_typeof(p_body->'bundle') is distinct from 'string' or
     jsonb_typeof(p_body->'state') is distinct from 'object' or
     (coalesce(p_body->>'error','')='' and
      jsonb_typeof(p_body->'result') is distinct from 'object') then
   raise exception 'Invalid completed execution';
  end if;
  for pending in select value from jsonb_array_elements(p_body->'pending_events') loop
   perform public.paper_runner_write(p_request,(pending->>'operation_id')::uuid,
    'event',pending-'operation_id');
  end loop;
  update public.paper_sessions set checkpoint=p_body->>'checkpoint',
   bundle=p_body->>'bundle',state=p_body->'state',touched_at=now() where id=r.session_id;
  update public.paper_runs set status=case when coalesce(p_body->>'error','')<>''
   then 'failed' else 'complete' end,error=nullif(p_body->>'error',''),
   result=p_body->'result' where id=p_request;
 end if;
 insert into public.paper_runner_receipts(request_id,operation_id,payload_hash)
  values(p_request,p_operation,fingerprint);
end $$;
revoke all on function public.paper_runner_write from public,anon,authenticated;
grant execute on function public.paper_runner_write to service_role;

create extension if not exists pg_cron;
do $$ begin
 if not exists(select 1 from cron.job where jobname='paper-demo-expiry') then
  perform cron.schedule('paper-demo-expiry','* * * * *','select public.paper_cleanup();');
 end if;
end $$;
notify pgrst, 'reload schema';
commit;
