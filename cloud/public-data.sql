-- Public albacore inputs for the paper demo only.
-- The workshop service uses a different project and is not changed here.
begin;

create table if not exists public.paper_public_sources (
  version text primary key,
  source_sha256 text not null check (source_sha256 ~ '^[0-9a-f]{64}$'),
  metadata jsonb not null
);
create table if not exists public.paper_public_sets (
  version text not null references public.paper_public_sources(version),
  set_id text not null,
  source_row integer not null,
  year integer not null,
  fleet text not null,
  quarter integer not null check (quarter between 1 and 4),
  cell text not null,
  stratum text not null,
  hooks double precision not null check (hooks > 0),
  catch_n integer not null check (catch_n >= 0),
  primary key (version, set_id)
);
create table if not exists public.paper_public_catches (
  version text not null references public.paper_public_sources(version),
  year integer not null,
  catch_t double precision not null check (catch_t >= 0),
  primary key (version, year)
);
alter table public.paper_public_sources enable row level security;
alter table public.paper_public_sets enable row level security;
alter table public.paper_public_catches enable row level security;
revoke all on public.paper_public_sources, public.paper_public_sets,
              public.paper_public_catches from anon, authenticated;
grant select on public.paper_public_sources, public.paper_public_sets,
                public.paper_public_catches to service_role;

commit;
