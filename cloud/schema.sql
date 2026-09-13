begin;
create table if not exists public.paper_sets (set_id text primary key, year integer not null, vessel text not null, hooks integer check(hooks>0), catch_n integer check(catch_n>=0));
create table if not exists public.paper_catches (year integer primary key, catch_t double precision check(catch_t>=0));
create table if not exists public.paper_sessions (id uuid primary key, token_hash text not null, created_at timestamptz default now(), touched_at timestamptz default now(), checkpoint text, state jsonb, accepted_year integer);
alter table public.paper_sessions add column if not exists bundle text;
create table if not exists public.paper_runs (id uuid primary key, session_id uuid references public.paper_sessions on delete cascade, created_at timestamptz default now(), status text default 'queued', start_job text not null, settings jsonb not null, handover text not null, transfer_count integer default 0, connected boolean default false, github_run text, commit_sha text, error text, result jsonb);
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
revoke all on function public.paper_start from public,anon,authenticated;
grant execute on function public.paper_start to service_role;


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
create extension if not exists pg_cron;
do $$ begin
 if not exists(select 1 from cron.job where jobname='paper-demo-expiry') then
  perform cron.schedule('paper-demo-expiry','* * * * *','select public.paper_cleanup();');
 end if;
end $$;
commit;
