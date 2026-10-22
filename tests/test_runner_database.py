"""Exercise the runner transaction in an explicitly selected disposable PostgreSQL.

Use a local postgres:17-alpine container with --network none, then set
PAPER_TEST_POSTGRES_CONTAINER to its name. No hosted database is accessed.
"""
from concurrent.futures import ThreadPoolExecutor
import base64
import hashlib
import json
import os
from pathlib import Path
import subprocess
import unittest
import uuid

ROOT = Path(__file__).resolve().parents[1]
CONTAINER = os.environ.get('PAPER_TEST_POSTGRES_CONTAINER')


def literal(value):
    return "'" + str(value).replace("'", "''") + "'"


@unittest.skipUnless(CONTAINER, 'Set PAPER_TEST_POSTGRES_CONTAINER for local SQL checks')
class RunnerDatabaseTest(unittest.TestCase):
    @classmethod
    def sql(cls, statement, success=True):
        result = subprocess.run(['docker', 'exec', '-i', CONTAINER, 'psql', '-X', '-qAt',
                                 '-v', 'ON_ERROR_STOP=1', '-U', 'postgres'],
                                input=statement, text=True, capture_output=True, timeout=20)
        if success and result.returncode:
            raise AssertionError(result.stderr)
        if not success and not result.returncode:
            raise AssertionError('An invalid transaction succeeded.')
        return result.stdout.strip() if success else result.stderr

    @classmethod
    def setUpClass(cls):
        details = subprocess.run(['docker', 'inspect', CONTAINER], capture_output=True,
                                 text=True, check=True)
        if json.loads(details.stdout)[0]['HostConfig']['NetworkMode'] != 'none':
            raise RuntimeError('Database checks require a container with --network none.')
        cls.sql("do $$ declare name text; begin "
                "for name in select unnest(array['anon','authenticated','service_role','authenticator']) loop "
                "if not exists(select 1 from pg_roles where rolname=name) then "
                "execute format('create role %I',name); end if; end loop; end $$;")
        cls.apply_schema()
        # Match the hosted service role, without changing production grants/policies.
        cls.sql("alter role service_role bypassrls; grant select on public.paper_runs,"
                "public.paper_sessions,public.paper_runner_receipts to service_role;")

    @classmethod
    def apply_schema(cls):
        # The vanilla image lacks pg_cron. Test all tables and functions from the
        # production schema; leave its unrelated scheduling setup out of this DB.
        schema = (ROOT / 'cloud/schema.sql').read_text().split('create extension if not exists pg_cron;')[0]
        cls.sql(schema + '\ncommit;')

    def setUp(self):
        self.session, self.request = str(uuid.uuid4()), str(uuid.uuid4())
        self.sql(f"insert into public.paper_sessions(id,token_hash) values('{self.session}','test-only');"
                 f"insert into public.paper_runs(id,session_id,status,start_job,settings,handover) "
                 f"values('{self.request}','{self.session}','running','submission',"
                 "'{\"last_year\":2024}','connected');")

    def tearDown(self):
        self.sql(f"delete from public.paper_sessions where id='{self.session}';")

    def write(self, operation, action, body, success=True):
        return self.sql(f"select public.paper_runner_write('{self.request}',{literal(operation)},"
                        f"{literal(action)},{literal(json.dumps(body))}::jsonb);", success)

    def finish_rpc(self, operation, action, body, success=True):
        action_sql = 'null' if action is None else literal(action)
        return self.sql(f"set role service_role; select public.paper_runner_finish("
                        f"'{self.request}',{literal(operation)},{action_sql},"
                        f"{literal(json.dumps(body))}::jsonb);", success)

    def value(self, expression, table):
        column = 'id' if table == 'paper_runs' else 'request_id'
        return self.sql(f"select {expression} from public.{table} where {column}='{self.request}';")

    def state(self):
        return self.sql(f"select state->>'step' from public.paper_sessions where id='{self.session}';")

    def event(self, state, step):
        return {'event': {'job': 'cpue_a', 'state': state}, 'state': {'step': step}}

    def finish(self, pending=None, error=None):
        return {'checkpoint': 'retained-checkpoint', 'bundle': 'actual-bundle', 'state': {'step': 'final'},
                'result': None if error else {'run_id': 'Run 001'}, 'error': error,
                'pending_events': pending or []}

    def test_run_scope_migration_can_be_reapplied_without_changing_saved_scope(self):
        # Recreate the pre-scope table with an existing run in this disposable DB.
        self.sql('alter table public.paper_runs drop column scope;')
        self.apply_schema()
        self.assertEqual(self.value('scope', 'paper_runs'), 'workflow')
        self.sql(f"update public.paper_runs set scope='job' where id='{self.request}';")
        self.apply_schema()
        self.apply_schema()
        self.assertEqual(self.value('scope', 'paper_runs'), 'job')

    def test_legacy_and_scoped_start_calls_keep_scope_separate_from_settings(self):
        for scope in (None, 'workflow', 'job'):
            with self.subTest(scope=scope):
                self.sql(f"update public.paper_runs set status='complete' where id='{self.request}';")
                argument = '' if scope is None else f",p_scope=>'{scope}'"
                self.sql("set role service_role; select public.paper_start("
                         f"p_session=>'{self.session}',p_request=>'{self.request}',"
                         "p_start=>'cpue_a',p_settings=>'{\"last_year\":2024}'::jsonb,"
                         f"p_handover=>'connected'{argument});")
                self.assertEqual(self.value('scope', 'paper_runs'), scope or 'workflow')
                self.assertEqual(json.loads(self.value('settings', 'paper_runs')), {'last_year': 2024})
                self.assertEqual(self.value('status', 'paper_runs'), 'queued')

    def test_invalid_scope_cannot_replace_a_run_or_spend_quota(self):
        self.sql(f"update public.paper_runs set status='complete' where id='{self.request}';")
        count = self.sql('select count from public.paper_limits where id;')
        for scope in ("'all'", "''", 'null'):
            with self.subTest(scope=scope):
                error = self.sql("set role service_role; select public.paper_start("
                                 f"'{self.session}','{self.request}','cpue_a',"
                                 f"'{{\"last_year\":2024}}','connected',{scope});", success=False)
                self.assertIn('Invalid run scope', error)
                self.assertEqual(self.value('status', 'paper_runs'), 'complete')
                self.assertEqual(self.value('start_job', 'paper_runs'), 'submission')
                self.assertEqual(self.sql('select count from public.paper_limits where id;'), count)
                self.sql(f"update public.paper_runs set scope={scope} where id='{self.request}';",
                         success=False)
                self.assertEqual(self.value('scope', 'paper_runs'), 'workflow')

    def test_public_roles_cannot_start_either_run_scope(self):
        for role in ('anon', 'authenticated'):
            for argument in ('', ",'workflow'", ",'job'"):
                error = self.sql(f"set role {role}; select public.paper_start("
                                 f"'{self.session}','{self.request}','submission',"
                                 f"'{{\"last_year\":2024}}','connected'{argument});", success=False)
                self.assertIn('permission denied', error)

    def test_duplicate_and_delayed_event_cannot_repeat_or_reorder_state(self):
        first, second = str(uuid.uuid4()), str(uuid.uuid4())
        running, waiting = self.event('running', 'first'), self.event('handover', 'second')
        self.write(first, 'event', running)
        self.write(second, 'event', waiting)
        self.write(first, 'event', running)
        self.assertEqual(self.value('count(*)', 'paper_events'), '2')
        self.assertEqual(self.value('status', 'paper_runs'), 'handover')
        self.assertEqual(self.state(), 'second')
        self.write(first, 'event', waiting, success=False)
        self.assertEqual(self.state(), 'second')

    def test_concurrent_duplicate_receipts_commit_one_event(self):
        operation = str(uuid.uuid4())
        with ThreadPoolExecutor(max_workers=4) as pool:
            list(pool.map(lambda _: self.write(operation, 'event', self.event('running', 'one')), range(4)))
        self.assertEqual(self.value('count(*)', 'paper_events'), '1')
        self.assertEqual(self.value('count(*)', 'paper_runner_receipts'), '1')

    def test_failed_output_write_rolls_back_event_state_and_receipt(self):
        operation = str(uuid.uuid4())
        invalid = {'event': {'state': 'complete'}, 'output': {'value': 1}, 'state': {'step': 'invalid'}}
        self.write(operation, 'event', invalid, success=False)
        self.assertEqual(self.value('count(*)', 'paper_events'), '0')
        self.assertEqual(self.value('count(*)', 'paper_runner_receipts'), '0')
        self.assertEqual(self.state(), '')
        self.write(operation, 'event', self.event('complete', 'valid'))
        self.assertEqual(self.state(), 'valid')

    def test_finish_replays_pending_events_once_then_acknowledges_lost_response(self):
        first, second, final = str(uuid.uuid4()), str(uuid.uuid4()), str(uuid.uuid4())
        start, completed = self.event('running', 'start'), self.event('complete', 'done')
        completed['output'] = {'value': 'actual result'}
        self.write(first, 'event', start)  # The server committed but its response was lost.
        body = self.finish([{'operation_id': first, **start}, {'operation_id': second, **completed}])
        self.write(final, 'finish', body)
        self.write(final, 'finish', body)
        self.assertEqual(self.value('count(*)', 'paper_events'), '2')
        self.assertEqual(self.value('status', 'paper_runs'), 'complete')
        self.assertEqual(self.state(), 'final')
        self.assertEqual(self.sql(f"select output->>'value' from paper_outputs where session_id='{self.session}';"),
                         'actual result')
        self.write(str(uuid.uuid4()), 'finish', body, success=False)
        self.write(str(uuid.uuid4()), 'event', start, success=False)
        self.assertEqual(self.state(), 'final')

    def test_failed_finish_remains_failed_and_missing_results_cannot_complete(self):
        invalid = self.finish()
        invalid['result'] = None
        self.write(str(uuid.uuid4()), 'finish', invalid, success=False)
        self.assertEqual(self.value('status', 'paper_runs'), 'running')
        operation, failed = str(uuid.uuid4()), self.finish(error='Preparation failed.')
        self.write(operation, 'finish', failed)
        self.write(operation, 'finish', failed)
        self.assertEqual(self.value('status', 'paper_runs'), 'failed')
        self.assertEqual(self.value('error', 'paper_runs'), 'Preparation failed.')

    def test_finish_rpc_replays_and_acknowledges_the_same_atomic_receipt(self):
        first, second, final = str(uuid.uuid4()), str(uuid.uuid4()), str(uuid.uuid4())
        invalid = {**self.finish(), 'result': None}
        self.assertIn('Invalid completed execution',
                      self.finish_rpc(final, 'finish', invalid, success=False))
        self.assertEqual(self.value('count(*)', 'paper_runner_receipts'), '0')
        self.assertEqual(self.value('status', 'paper_runs'), 'running')
        start, completed = self.event('running', 'start'), self.event('complete', 'done')
        self.write(first, 'event', start)
        body = self.finish([{'operation_id': first, **start}, {'operation_id': second, **completed}])
        self.finish_rpc(final, 'finish', body)
        self.finish_rpc(final, 'finish', body)
        self.write(final, 'finish', body)  # Legacy path shares exactly the same receipt.
        self.assertEqual(self.value('count(*)', 'paper_events'), '2')
        self.assertEqual(self.value('count(*)', 'paper_runner_receipts'), '3')
        self.assertEqual(self.value('status', 'paper_runs'), 'complete')
        self.assertEqual(self.state(), 'final')
        altered = {**body, 'bundle': 'changed bytes'}
        self.assertIn('Operation identifier already used',
                      self.finish_rpc(final, 'finish', altered, success=False))
        self.assertIn('Run is no longer active',
                      self.finish_rpc(str(uuid.uuid4()), 'finish', body, success=False))
        self.assertEqual(self.sql(f"select bundle from public.paper_sessions where id='{self.session}';"),
                         body['bundle'])
        self.assertEqual(self.value('count(*)', 'paper_runner_receipts'), '3')

    def test_finish_rpc_rejects_other_actions_and_public_roles(self):
        for action in ('event', '', None):
            error = self.finish_rpc(str(uuid.uuid4()), action, self.finish(), success=False)
            self.assertIn('Invalid completed execution action', error)
        self.assertEqual(self.value('count(*)', 'paper_runner_receipts'), '0')
        self.assertEqual(self.value('status', 'paper_runs'), 'running')
        for role in ('anon', 'authenticated'):
            error = self.sql(f"set role {role}; select public.paper_runner_finish('{self.request}',"
                             f"'{uuid.uuid4()}','finish','{{}}');", success=False)
            self.assertIn('permission denied', error)
        self.write(str(uuid.uuid4()), 'event', self.event('handover', 'original event path'))
        self.assertEqual(self.value('status', 'paper_runs'), 'handover')

    def test_finish_rpc_has_a_scoped_budget_and_no_new_definer_privilege(self):
        metadata = json.loads(self.sql("select jsonb_build_object('definer',prosecdef,"
                                       "'settings',proconfig) from pg_proc where "
                                       "oid='public.paper_runner_finish(uuid,uuid,text,jsonb)'::regprocedure;"))
        self.assertFalse(metadata['definer'])
        self.assertEqual(set(metadata['settings']), {'search_path=""', 'statement_timeout=45s', 'work_mem=16MB'})
        original = json.loads(self.sql("select to_jsonb(proconfig) from pg_proc where "
                                      "oid='public.paper_runner_write(uuid,uuid,text,jsonb)'::regprocedure;"))
        self.assertEqual(original, ['search_path=""'])
        # Direct SQL is not a PostgREST hoisting test. These finite settings must
        # still be restored after returning to an ordinary event caller.
        settings = self.sql("set statement_timeout='8s'; set lock_timeout='8s'; "
                            "set role service_role; "
                            f"select public.paper_runner_finish('{self.request}','{uuid.uuid4()}',"
                            f"'finish',{literal(json.dumps(self.finish()))}::jsonb); "
                            "select current_setting('statement_timeout')||','||current_setting('lock_timeout');")
        self.assertEqual(settings, '8s,8s')

    def test_finish_budget_migration_preserves_the_receipt_and_other_rpc_settings(self):
        operation, body = str(uuid.uuid4()), self.finish()
        self.finish_rpc(operation, 'finish', body)
        before = self.sql("select jsonb_build_object('body',prosrc,'acl',proacl,"
                          "'definer',prosecdef) from pg_proc where "
                          "oid='public.paper_runner_finish(uuid,uuid,text,jsonb)'::regprocedure;")
        original = self.sql("select to_jsonb(proconfig) from pg_proc where "
                            "oid='public.paper_runner_write(uuid,uuid,text,jsonb)'::regprocedure;")
        self.sql("alter function public.paper_runner_finish(uuid,uuid,text,jsonb) "
                 "set statement_timeout='20s';")
        migration = (ROOT / 'supabase/migrations/20261022111252_finish_transport_budget.sql').read_text()
        self.sql(migration)
        self.sql(migration)
        after = self.sql("select jsonb_build_object('body',prosrc,'acl',proacl,"
                         "'definer',prosecdef) from pg_proc where "
                         "oid='public.paper_runner_finish(uuid,uuid,text,jsonb)'::regprocedure;")
        self.assertEqual(before, after)
        settings = json.loads(self.sql("select to_jsonb(proconfig) from pg_proc where "
                                       "oid='public.paper_runner_finish(uuid,uuid,text,jsonb)'::regprocedure;"))
        self.assertEqual(set(settings), {'search_path=""', 'statement_timeout=45s', 'work_mem=16MB'})
        self.assertEqual(original, self.sql("select to_jsonb(proconfig) from pg_proc where "
                                           "oid='public.paper_runner_write(uuid,uuid,text,jsonb)'::regprocedure;"))
        self.finish_rpc(operation, 'finish', body)
        self.assertEqual(self.value('count(*)', 'paper_runner_receipts'), '1')
        self.assertEqual(self.value('status', 'paper_runs'), 'complete')
        self.assertEqual(self.state(), 'final')

    def test_late_setup_message_does_not_move_a_handover_backwards(self):
        self.write(str(uuid.uuid4()), 'event', self.event('handover', 'waiting'))
        self.write(str(uuid.uuid4()), 'event', {'event': {'state': 'phase', 'title': 'Downloading Docker'}})
        self.assertEqual(self.value('count(*)', 'paper_events'), '1')
        self.assertEqual(self.value('status', 'paper_runs'), 'handover')

    def test_public_roles_cannot_write_runner_receipts(self):
        for role in ('anon', 'authenticated'):
            error = self.sql(f"set role {role}; select public.paper_runner_write('{self.request}',"
                             f"'{uuid.uuid4()}','event','{{}}');", success=False)
            self.assertIn('permission denied', error)
            self.assertIn('permission denied', self.sql(
                f'set role {role}; select * from public.paper_runner_receipts;', success=False))

    def test_independent_reporting_keeps_manual_transfer_available(self):
        self.write(str(uuid.uuid4()), 'event', {
            'event': {'job': 'prepare_a', 'state': 'handover', 'boundary': 'cpue',
                      'group': ['prepare_a', 'prepare_b']}})
        for state in ('running', 'complete'):
            self.write(str(uuid.uuid4()), 'event', {
                'event': {'job': 'cpue_report', 'state': state}})
            self.assertEqual(self.value('status', 'paper_runs'), 'handover')
        # Match the reader API's conditional acknowledgement while reporting is complete.
        self.sql(f"update public.paper_runs set transfer_count=transfer_count+1,status='running' "
                 f"where id='{self.request}' and status='handover' and transfer_count=0;")
        self.assertEqual(self.value('transfer_count', 'paper_runs'), '1')
        self.write(str(uuid.uuid4()), 'event', {'event': {
            'job': 'prepare_a', 'state': 'received', 'boundary': 'cpue',
            'group': ['prepare_a', 'prepare_b']}})
        self.assertEqual(self.value('status', 'paper_runs'), 'running')

    def receipt(self, operation):
        return json.loads(self.sql("set role service_role; select coalesce(public.paper_runner_finish_receipt("
                                   f"'{self.request}',{literal(operation)}),'null'::jsonb);"))

    def test_finish_readback_matches_exact_original_operation_and_decoded_archives(self):
        operation = str(uuid.uuid4())
        self.sql(f"update public.paper_runs set github_run='39365433531',commit_sha='{'a' * 40}' "
                 f"where id='{self.request}';")
        body = {**self.finish(),
                'checkpoint': base64.b64encode(b'checkpoint\x00').decode(),
                'bundle': base64.b64encode(b'bundle\xff').decode()}
        self.assertIsNone(self.receipt(operation))
        self.finish_rpc(operation, 'finish', body)
        first = self.receipt(operation)
        self.assertEqual(first, {
            'request_id': self.request, 'operation_id': operation,
            # This is PostgreSQL's stored fingerprint, not a Python wire hash.
            'payload_hash': self.sql("select payload_hash from public.paper_runner_receipts "
                                     f"where request_id='{self.request}' and operation_id='{operation}';"),
            'github_run': '39365433531', 'commit_sha': 'a' * 40, 'status': 'complete',
            'error': None, 'run_id': 'Run 001',
            'bundle_sha256': hashlib.sha256(b'bundle\xff').hexdigest(),
            'checkpoint_sha256': hashlib.sha256(b'checkpoint\x00').hexdigest()})
        self.assertEqual(len(first['payload_hash']), 64)
        self.assertEqual(self.receipt(operation), first)
        self.assertIsNone(self.receipt(str(uuid.uuid4())))
        self.assertEqual(self.value('count(*)', 'paper_runner_receipts'), '1')
        self.assertEqual(self.value('count(*)', 'paper_events'), '0')
        self.assertEqual(self.state(), 'final')
        self.assertEqual(self.value('status', 'paper_runs'), 'complete')
        self.assertIn('Operation identifier already used',
                      self.finish_rpc(operation, 'finish', {**body, 'bundle': 'changed'}, success=False))
        self.assertIn('Run is no longer active',
                      self.finish_rpc(str(uuid.uuid4()), 'finish', body, success=False))

    def test_finish_readback_retains_failed_outcome_and_excludes_active_event_receipts(self):
        event, operation = str(uuid.uuid4()), str(uuid.uuid4())
        self.write(event, 'event', self.event('running', 'working'))
        self.assertIsNone(self.receipt(event))
        body = {**self.finish(error='Original calculation failed.'),
                'bundle': base64.b64encode(b'bundle').decode(),
                'checkpoint': base64.b64encode(b'checkpoint').decode()}
        self.finish_rpc(operation, 'finish', body)
        receipt = self.receipt(operation)
        self.assertEqual(receipt['status'], 'failed')
        self.assertEqual(receipt['error'], 'Original calculation failed.')
        self.assertIsNone(receipt['run_id'])
        self.assertEqual(self.value('status', 'paper_runs'), 'failed')

    def test_finish_readback_is_stable_invoker_and_service_role_only(self):
        metadata = json.loads(self.sql("select jsonb_build_object('definer',prosecdef,"
                                       "'volatility',provolatile,'arguments',pronargs,'settings',proconfig) "
                                       "from pg_proc where oid="
                                       "'public.paper_runner_finish_receipt(uuid,uuid)'::regprocedure;"))
        self.assertFalse(metadata['definer'])
        self.assertEqual(metadata['volatility'], 's')
        self.assertEqual(metadata['arguments'], 2)
        self.assertEqual(metadata['settings'], ['search_path=""'])
        for role in ('anon', 'authenticated'):
            self.assertIn('permission denied', self.sql(
                f"set role {role}; select public.paper_runner_finish_receipt("
                f"'{self.request}','{uuid.uuid4()}');", success=False))
        self.assertEqual(self.sql("select has_function_privilege('service_role',"
                                 "'public.paper_runner_finish_receipt(uuid,uuid)','execute');"), 't')
