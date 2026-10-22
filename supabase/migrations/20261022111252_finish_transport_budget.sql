-- Keep the existing atomic receipt and grants; only finish needs this budget.
begin;
alter function public.paper_runner_finish(uuid,uuid,text,jsonb)
 set statement_timeout = '45s';
notify pgrst, 'reload schema';
commit;
