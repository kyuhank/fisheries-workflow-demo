"""MSE planning and checkpoint scope using an explicit scheduler test double."""
import asyncio
import copy
import tempfile
import unittest
from tests.coordinator_fixtures import CoordinatorWorkflow as Workflow
from workflow.spec import SPEC

MSE = ['mse_prepare', 'mse_constant', 'mse_index', 'mse_buffered', 'mse_summary', 'mse_report']
BUFFER = ['mse_buffered', 'mse_summary', 'mse_report']


class MSEWorkflowTest(unittest.TestCase):
    def test_extension_keeps_assessment_records_and_declared_input_versions(self):
        with tempfile.TemporaryDirectory() as directory:
            runner = Workflow(directory)
            runner.configure({'mse': False})
            asyncio.run(runner.run())
            before = copy.deepcopy(runner.records)
            self.assertEqual(len(before), 16)
            runner.configure({'mse': True})
            self.assertEqual(asyncio.run(runner.run('mse_prepare'))['run'], MSE)
            self.assertEqual({key: runner.records[key] for key in before}, before)
            for parent, value in runner.records['mse_prepare']['inputs'].items():
                self.assertEqual(value, {'run_id': before[parent]['run_id'],
                                        'checksum': before[parent]['outputs']['output.json']})

    def test_buffer_change_and_resume_preserve_all_other_records(self):
        with tempfile.TemporaryDirectory() as directory:
            runner = Workflow(directory)
            asyncio.run(runner.run())
            before = copy.deepcopy(runner.records)
            runner.configure({'mse_buffer': .6})
            self.assertEqual(asyncio.run(runner.run('mse_report'))['run'], BUFFER)
            for key in SPEC:
                if key not in BUFFER:
                    self.assertEqual(runner.records[key], before[key])
            restored = Workflow(directory)
            self.assertEqual(restored.records, runner.records)
            self.assertEqual(restored.settings['mse_buffer'], .6)
            self.assertTrue(all(restored.valid(key) for key in SPEC))
            restored.configure({'mse_buffer': .8})
            self.assertEqual(restored.plan('mse_report')['run'], BUFFER)

    def test_failed_rule_keeps_previous_report_until_explicit_recovery(self):
        with tempfile.TemporaryDirectory() as directory:
            runner = Workflow(directory)
            asyncio.run(runner.run())
            report = copy.deepcopy(runner.records['mse_report'])
            original = runner.calculate
            async def fail(key, run_id):
                if key == 'mse_buffered':
                    raise ValueError('Injected rule failure')
                return await original(key, run_id)
            runner.calculate = fail
            with self.assertRaisesRegex(ValueError, 'Injected'):
                asyncio.run(runner.run('mse_prepare'))
            self.assertEqual(runner.records['mse_report'], report)
            self.assertFalse(any(e['job'] == 'mse_summary' for e in runner.events))
            resumed = Workflow(directory)
            self.assertEqual(asyncio.run(resumed.run('mse_buffered'))['run'], BUFFER)
            self.assertTrue(resumed.valid('mse_report'))
