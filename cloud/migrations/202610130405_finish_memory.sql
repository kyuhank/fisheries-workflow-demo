-- Paper demo only: retain limits, privileges and the atomic receipt protocol.
begin;
set local lock_timeout='2s';
set local statement_timeout='25s';
do $$
declare prior text[];
begin
 select p.proconfig into strict prior from pg_proc p
  where p.oid='public.paper_runner_finish(uuid,uuid,text,jsonb)'::regprocedure;
 if ('statement_timeout=20s'=any(prior)) is distinct from true then
  raise exception 'Unexpected finish statement limit';
 end if;
 if exists(select 1 from unnest(prior) c
  where c like 'work_mem=%' and c <> 'work_mem=16MB') then
  raise exception 'Unexpected finish memory setting';
 end if;
 if exists(select 1 from pg_db_role_setting s,
  lateral unnest(s.setconfig) c
  where s.setrole=(select oid from pg_roles where rolname='authenticator')
   and s.setdatabase in (0,(select oid from pg_database where datname='postgres'))
   and c like 'pgrst.db_hoisted_tx_settings=%'
   and c <> 'pgrst.db_hoisted_tx_settings=statement_timeout,plan_filter.statement_cost_limit,default_transaction_isolation,work_mem') then
  raise exception 'Review existing PostgREST hoisted settings before migration';
 end if;
 if has_function_privilege('anon','public.paper_runner_finish(uuid,uuid,text,jsonb)','execute')
  or has_function_privilege('authenticated','public.paper_runner_finish(uuid,uuid,text,jsonb)','execute') then
  raise exception 'Unexpected public finish permission';
 end if;
end $$;
alter function public.paper_runner_finish(uuid,uuid,text,jsonb) set work_mem='16MB';
alter role authenticator in database postgres set pgrst.db_hoisted_tx_settings =
 'statement_timeout,plan_filter.statement_cost_limit,default_transaction_isolation,work_mem';
notify pgrst, 'reload config';
notify pgrst, 'reload schema';
commit;

-- Rollback for the verified deployment with no prior database-level override:
-- ALTER FUNCTION public.paper_runner_finish(uuid,uuid,text,jsonb) RESET work_mem;
-- ALTER ROLE authenticator IN DATABASE postgres RESET pgrst.db_hoisted_tx_settings;
-- NOTIFY pgrst, 'reload config'; NOTIFY pgrst, 'reload schema';
