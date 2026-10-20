begin;
-- Read the original atomic receipt without resending or hashing a finish body.
create or replace function public.paper_runner_finish_receipt(
 p_request uuid,p_operation uuid
) returns jsonb language sql stable security invoker set search_path='' as $$
 select jsonb_build_object(
  'request_id',r.id,'operation_id',c.operation_id,'payload_hash',c.payload_hash,
  'github_run',r.github_run,'commit_sha',r.commit_sha,'status',r.status,
  'error',r.error,'run_id',r.result->>'run_id',
  'bundle_sha256',encode(sha256(decode(s.bundle,'base64')),'hex'),
  'checkpoint_sha256',encode(sha256(decode(s.checkpoint,'base64')),'hex'))
 from public.paper_runner_receipts c
 join public.paper_runs r on r.id=c.request_id
 join public.paper_sessions s on s.id=r.session_id
 where c.request_id=p_request and c.operation_id=p_operation
  and r.status in ('complete','failed');
$$;
revoke all on function public.paper_runner_finish_receipt(uuid,uuid) from public,anon,authenticated;
grant execute on function public.paper_runner_finish_receipt(uuid,uuid) to service_role;
notify pgrst, 'reload schema';
commit;
