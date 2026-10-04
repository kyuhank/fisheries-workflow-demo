"""The integration checker must tolerate a run snapshot older than its events."""
import importlib.util
from pathlib import Path
import unittest
from unittest.mock import patch


CHECK_PATH = Path(__file__).resolve().parents[1] / 'scripts/check-online.py'


@unittest.skipUnless(CHECK_PATH.exists(), 'The calculation bundle omits the online integration checker')
class OnlinePollTest(unittest.TestCase):
    def setUp(self):
        spec = importlib.util.spec_from_file_location('online_check', CHECK_PATH)
        self.check = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(self.check)
        self.clock = 0
        self.transfers = 0
        self.session = {'id': 'test-session', 'token': 'test-token'}
        self.jobs = list(self.check.SPEC)

    def sleep(self, seconds):
        self.clock += seconds

    def update(self, status, events=(), result=None):
        return {'run': {'id': 'test-request', 'status': status, 'result': result, 'github_run': 'test-run',
                        'commit_sha': 'test-commit'},
                'events': [{'id': index + 1, 'event': event} for index, event in enumerate(events)]}

    def handover(self):
        return {'job': 'cpue_a', 'state': 'handover', 'boundary': 'data',
                'group': ['cpue_a', 'cpue_b']}

    def plan(self):
        return {'state': 'plan', 'start': 'submission', 'scope': 'workflow',
                'run': self.jobs, 'retained': [], 'run_id': 'Run 001'}

    def job_events(self, keys):
        return [{'job': key, 'state': state} for key in keys
                for state in ('running', 'complete')]

    def before_transfer(self):
        return [self.plan(), *self.job_events(self.jobs[:4]), self.handover()]

    def after_transfer(self):
        return [{**self.handover(), 'state': 'received'},
                *self.job_events(self.jobs[4:])]

    def result(self):
        return {'start': 'submission', 'scope': 'workflow', 'run': self.jobs,
                'retained': [], 'run_id': 'Run 001', 'records': {}}

    def exercise(self, polls, repeated=None):
        updates = iter(polls)

        def request(path, body=None, session=None):
            if path == '/run':
                return {'id': 'test-request'}
            if path == '/transfer':
                self.transfers += 1
                return {'ok': True}
            self.assertTrue(path.startswith('/state?after='))
            return next(updates, repeated)

        with patch.object(self.check, 'request', side_effect=request), \
             patch.object(self.check, 'check_identity') as identity, \
             patch.object(self.check.time, 'monotonic', side_effect=lambda: self.clock), \
             patch.object(self.check.time, 'sleep', side_effect=self.sleep), \
             patch('builtins.print'):
            result = self.check.execute(self.session, 'submission', self.jobs, 'manual')
            identity.assert_called_once()
            return result

    def test_new_handover_event_with_old_running_snapshot_confirms_once(self):
        result = self.result()
        self.assertEqual(self.exercise([
            self.update('running', self.before_transfer()),
            self.update('handover'),
            self.update('complete', self.after_transfer(), result=result),
        ]), result)
        self.assertEqual(self.transfers, 1)

    def test_reporting_cannot_permanently_hide_the_pending_transfer(self):
        with self.assertRaisesRegex(AssertionError, 'did not preserve the pending transfer'):
            self.exercise([self.update('running', self.before_transfer())],
                          repeated=self.update('running'))
        self.assertEqual(self.transfers, 0)
        self.assertLessEqual(self.clock, 16)

    def test_terminal_runner_error_is_not_mistaken_for_poll_lag(self):
        failed = self.update('failed', self.before_transfer())
        failed['run']['error'] = 'Runner calculation failed'
        with self.assertRaisesRegex(RuntimeError, 'status failed'):
            self.exercise([failed])
        self.assertEqual(self.transfers, 0)
        self.assertEqual(self.clock, 0)

    def test_claimed_completion_without_a_job_running_event_fails(self):
        events = [event for event in self.after_transfer()
                  if not (event.get('job') == 'cpue_b' and event['state'] == 'running')]
        with self.assertRaisesRegex(AssertionError, 'Missing running event: cpue_b'):
            self.exercise([self.update('handover', self.before_transfer()),
                           self.update('complete', events, self.result())])

    def test_claimed_completion_without_a_job_complete_event_fails(self):
        events = [event for event in self.after_transfer()
                  if not (event.get('job') == 'cpue_b' and event['state'] == 'complete')]
        with self.assertRaisesRegex(AssertionError, 'Missing complete event: cpue_b'):
            self.exercise([self.update('handover', self.before_transfer()),
                           self.update('complete', events, self.result())])

    def test_returned_submission_and_restarted_qc_remain_valid(self):
        resubmission = [
            {'job': 'submission', 'state': 'running'},
            {'job': 'submission', 'state': 'complete'},
            {'job': 'qc', 'state': 'running'},
            {'job': 'qc', 'state': 'failed'},
            {'job': 'submission', 'state': 'returned'},
            {'job': 'submission', 'state': 'running'},
            {'job': 'submission', 'state': 'complete'},
            {'job': 'qc', 'state': 'running'},
            {'job': 'qc', 'state': 'complete'},
        ]
        before = [self.plan(), *resubmission,
                  *self.job_events(['database', 'extract']), self.handover()]
        result = self.result()
        self.assertEqual(self.exercise([
            self.update('handover', before),
            self.update('complete', self.after_transfer(), result),
        ]), result)
        self.assertEqual(self.transfers, 1)


if __name__ == '__main__':
    unittest.main()
