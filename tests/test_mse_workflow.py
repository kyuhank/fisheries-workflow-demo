"""MSE extends recorded assessment results without changing their reporting path."""
import asyncio
import json
from pathlib import Path
import tempfile
import unittest

from workflow.engine import Workflow
from workflow.spec import SPEC
from verify import verify

MSE = ['mse_prepare', 'mse_constant', 'mse_index', 'mse_buffered', 'mse_summary', 'mse_report']
ASSESSMENTS = ['assessment_a1', 'assessment_a2', 'assessment_b1', 'assessment_b2']


class MSEWorkflowTest(unittest.TestCase):
    def test_assessment_only_then_mse_preserves_upstream_results(self):
        with tempfile.TemporaryDirectory() as directory:
            runner = Workflow(directory)
            runner.configure({'mse': False})
            baseline = asyncio.run(runner.run())
            self.assertEqual(len(baseline['run']), 16)
            self.assertFalse(set(MSE).intersection(runner.records))
            before = json.loads(json.dumps(runner.records))
            runner.configure({'mse': True})
            extended = asyncio.run(runner.run('mse_prepare'))
            self.assertEqual(extended['run'], MSE)
            self.assertEqual({key: runner.records[key] for key in before}, before)
            inputs = runner.records['mse_prepare']['inputs']
            self.assertEqual(list(inputs), ASSESSMENTS)
            for parent in ASSESSMENTS:
                self.assertEqual(inputs[parent]['checksum'], before[parent]['outputs']['output.json'])
            partial = asyncio.run(runner.run('mse_index'))
            self.assertEqual(partial['run'], ['mse_index', 'mse_summary', 'mse_report'])
            self.assertEqual(runner.records['mse_constant']['run_id'], extended['run_id'])
            self.assertEqual(runner.records['mse_summary']['inputs']['mse_constant']['run_id'], extended['run_id'])
            self.assertTrue(all(runner.valid(key) for key in SPEC))
            previous = runner.records['mse_report'].copy()
            report_only = asyncio.run(runner.run('assessment_report'))
            self.assertEqual(report_only['run'], ['assessment_report'])
            self.assertEqual(runner.records['mse_report'], previous)

    def test_portable_assessment_only_output_verification(self):
        with tempfile.TemporaryDirectory() as directory:
            paths = [Path(directory) / name for name in ('reference', 'repeat')]
            for path in paths:
                runner = Workflow(path)
                runner.configure({'mse': False})
                asyncio.run(runner.run())
            self.assertEqual(verify(*paths), 16)

    def test_failed_strategy_keeps_summary_and_report_until_recovery(self):
        with tempfile.TemporaryDirectory() as directory:
            runner = Workflow(directory)
            asyncio.run(runner.run())
            previous = runner.records['mse_report'].copy()
            original = runner.calculate

            async def fail(key, run_id):
                if key == 'mse_buffered':
                    raise ValueError('Strategy input unavailable')
                return await original(key, run_id)

            runner.calculate = fail
            with self.assertRaisesRegex(ValueError, 'Strategy input unavailable'):
                asyncio.run(runner.run('mse_prepare'))
            self.assertEqual(runner.records['mse_report'], previous)
            self.assertFalse(any(e['job'] == 'mse_summary' for e in runner.events))
            resumed = Workflow(directory)
            result = asyncio.run(resumed.run('mse_buffered'))
            self.assertEqual(result['run'], ['mse_buffered', 'mse_summary', 'mse_report'])
            self.assertTrue(resumed.valid('mse_report'))
