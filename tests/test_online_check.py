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

    def sleep(self, seconds):
        self.clock += seconds

    def update(self, status, events=(), result=None):
        return {'run': {'status': status, 'result': result, 'github_run': 'test-run',
                        'commit_sha': 'test-commit'},
                'events': [{'id': index + 1, 'event': event} for index, event in enumerate(events)]}

    def handover(self):
        return {'job': 'cpue_a', 'state': 'handover', 'boundary': 'data',
                'group': ['cpue_a', 'cpue_b']}

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
             patch.object(self.check.time, 'monotonic', side_effect=lambda: self.clock), \
             patch.object(self.check.time, 'sleep', side_effect=self.sleep), \
             patch('builtins.print'):
            return self.check.execute('submission', 'manual')

    def test_new_handover_event_with_old_running_snapshot_confirms_once(self):
        result = {'run': [], 'retained': []}
        self.assertEqual(self.exercise([
            self.update('running', [self.handover()]),
            self.update('handover'),
            self.update('complete', result=result),
        ]), result)
        self.assertEqual(self.transfers, 1)

    def test_reporting_cannot_permanently_hide_the_pending_transfer(self):
        with self.assertRaisesRegex(AssertionError, 'pending transfer available: running'):
            self.exercise([self.update('running', [self.handover()])],
                          repeated=self.update('running'))
        self.assertEqual(self.transfers, 0)
        self.assertLessEqual(self.clock, 16)

    def test_terminal_runner_error_is_not_mistaken_for_poll_lag(self):
        failed = self.update('failed', [self.handover()])
        failed['run']['error'] = 'Runner calculation failed'
        with self.assertRaisesRegex(RuntimeError, 'Runner calculation failed'):
            self.exercise([failed])
        self.assertEqual(self.transfers, 0)
        self.assertEqual(self.clock, 0)


if __name__ == '__main__':
    unittest.main()
