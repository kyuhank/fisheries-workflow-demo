"""Exercise the runner transaction in an explicitly selected disposable PostgreSQL.

Use a local postgres:17-alpine container with --network none, then set
PAPER_TEST_POSTGRES_CONTAINER to its name. No hosted database is accessed.
"""
from concurrent.futures import ThreadPoolExecutor
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
                "for name in select unnest(array['anon','authenticated','service_role']) loop "
                "if not exists(select 1 from pg_roles where rolname=name) then "
                "execute format('create role %I',name); end if; end loop; end $$;")
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
