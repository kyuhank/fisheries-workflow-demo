"""MSE extends recorded assessment results without changing their reporting path."""
import asyncio
import hashlib
import io
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
import zipfile

from workflow.engine import Workflow
from workflow.spec import SPEC
from verify import verify

MSE = ['mse_prepare', 'mse_constant', 'mse_index', 'mse_buffered', 'mse_summary', 'mse_report']
ASSESSMENTS = ['assessment_a1', 'assessment_a2', 'assessment_b1', 'assessment_b2']
BUFFER_JOBS = ['mse_buffered', 'mse_summary', 'mse_report']


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


class MSEBufferWorkflowTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.baseline = tempfile.TemporaryDirectory()
        cls.runner = Workflow(Path(cls.baseline.name) / 'baseline')
        cls.full = asyncio.run(cls.runner.run())

    @classmethod
    def tearDownClass(cls):
        cls.baseline.cleanup()

    def clone(self):
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        destination = Path(folder.name) / 'run'
        shutil.copytree(self.runner.directory, destination)
        return Workflow(destination)

    def test_buffer_settings_are_scoped_and_strictly_validated(self):
        runner = self.clone()
        self.assertEqual(len(self.full['run']), 22)
        self.assertEqual(runner.settings['mse_buffer'], 0.8)
        self.assertEqual(runner.records['mse_buffered']['settings'], {'buffer': 0.8})
        legacy = runner.state()
        legacy['settings'] = {key: value for key, value in legacy['settings'].items()
                              if key != 'mse_buffer'}
        (runner.directory / 'state.json').write_text(json.dumps(legacy))
        self.assertEqual(Workflow(runner.directory).settings['mse_buffer'], 0.8)
        previous = {key: runner.job_settings(key) for key in SPEC}
        for buffer in (0.6, 0.8, 1):
            with self.subTest(buffer=buffer):
                runner.configure({'mse_buffer': buffer})
                self.assertEqual(runner.job_settings('mse_buffered'), {'buffer': buffer})
                self.assertEqual({key: runner.job_settings(key) for key in SPEC
                                  if key != 'mse_buffered'},
                                 {key: value for key, value in previous.items()
                                  if key != 'mse_buffered'})
        accepted = runner.settings.copy()
        for buffer in (True, False, None, '0.8', 0, 0.7, -1, 1.1,
                       float('nan'), float('inf'), [], {}):
            with self.subTest(invalid_buffer=buffer):
                with self.assertRaises(ValueError):
                    runner.configure({'mse_buffer': buffer})
                self.assertEqual(runner.settings, accepted)
        with self.assertRaisesRegex(ValueError, 'Unknown analysis setting'):
            runner.configure({'mse_buffer': 0.6, 'seed': 1})
        self.assertEqual(runner.settings, accepted)

    def test_buffer_change_retains_inputs_and_reset_reproduces_original_results(self):
        runner = self.clone()
        records = json.loads(json.dumps(runner.records))
        record_bytes = {key: (runner.directory / key / 'record.json').read_bytes()
                        for key in SPEC}
        original_outputs = {key: (runner.directory / key / 'output.json').read_bytes()
                            for key in BUFFER_JOBS}
        original_buffered = runner.output('mse_buffered')
        retained = [key for key in SPEC if key not in BUFFER_JOBS]
        self.assertEqual(len(retained), 19)

        runner.configure({'mse_buffer': 0.6})
        self.assertEqual(runner.plan('mse_report')['run'], BUFFER_JOBS)
        changed = asyncio.run(runner.run('mse_report'))
        self.assertEqual(changed['run'], BUFFER_JOBS)
        self.assertEqual(changed['retained'], retained)
        for key in retained:
            with self.subTest(retained=key):
                self.assertEqual(runner.records[key], records[key])
                self.assertEqual((runner.directory / key / 'record.json').read_bytes(),
                                 record_bytes[key])
        self.assertEqual(runner.records['mse_buffered']['settings'], {'buffer': 0.6})
        self.assertEqual(runner.records['mse_buffered']['inputs'],
                         records['mse_buffered']['inputs'])
        for key in BUFFER_JOBS:
            self.assertEqual(runner.records[key]['run_id'], changed['run_id'])
            self.assertNotEqual(runner.records[key]['run_id'], records[key]['run_id'])
            for parent, details in runner.records[key]['inputs'].items():
                self.assertEqual(details, {
                    'run_id': runner.records[parent]['run_id'],
                    'checksum': runner.records[parent]['outputs']['output.json'],
                })
        for parent in ('mse_constant', 'mse_index'):
            self.assertEqual(runner.records['mse_summary']['inputs'][parent],
                             records['mse_summary']['inputs'][parent])

        buffered = runner.output('mse_buffered')
        self.assertNotEqual(buffered['metrics']['mean_catch_t'],
                            original_buffered['metrics']['mean_catch_t'])
        self.assertNotEqual(buffered['metrics']['final_SB_over_SB0'],
                            original_buffered['metrics']['final_SB_over_SB0'])
        self.assertEqual(buffered['rule_settings'], {'buffer': 0.6})
        self.assertEqual(runner.output('mse_summary')['rules']['buffered']['settings'],
                         {'buffer': 0.6})
        trial_fields = ('case', 'scenario', 'replicate', 'seed', 'random_stream')
        paired_trials = [tuple(row[field] for field in trial_fields)
                         for row in buffered['trials']]
        for result in (original_buffered, runner.output('mse_constant'), runner.output('mse_index')):
            self.assertEqual(paired_trials, [tuple(row[field] for field in trial_fields)
                                             for row in result['trials']])
            self.assertEqual(buffered['assumptions'], result['assumptions'])
            self.assertEqual(buffered['operating_models'], result['operating_models'])

        restored = Workflow(runner.directory)
        self.assertEqual(restored.settings['mse_buffer'], 0.6)
        self.assertEqual(restored.records, runner.records)
        self.assertTrue(all(restored.valid(key) for key in SPEC))
        restored.configure({'mse_buffer': 0.8})
        repeated = asyncio.run(restored.run('mse_report'))
        self.assertEqual(repeated['run'], BUFFER_JOBS)
        self.assertEqual(repeated['retained'], retained)
        for key in BUFFER_JOBS:
            self.assertEqual((restored.directory / key / 'output.json').read_bytes(),
                             original_outputs[key])
            self.assertEqual(restored.records[key]['run_id'], repeated['run_id'])
            self.assertNotEqual(repeated['run_id'], changed['run_id'])
            self.assertNotEqual(repeated['run_id'], records[key]['run_id'])
        for key in retained:
            self.assertEqual((restored.directory / key / 'record.json').read_bytes(),
                             record_bytes[key])
        self.assertTrue(all(restored.valid(key) for key in SPEC))

    def test_download_reproduces_completed_buffer_despite_pending_control_change(self):
        runner = self.clone()
        runner.configure({'mse_buffer': 0.6})
        changed = asyncio.run(runner.run('mse_report'))
        completed_records = json.loads(json.dumps(runner.records))
        record_bytes = {key: (runner.directory / key / 'record.json').read_bytes()
                        for key in SPEC}
        runner.configure({'mse_buffer': 0.8})
        with tempfile.TemporaryDirectory() as directory:
            extracted = Path(directory)
            with zipfile.ZipFile(io.BytesIO(runner.bundle())) as archive:
                settings = archive.read('settings.json')
                self.assertEqual(json.loads(settings)['mse_buffer'], 0.6)
                manifest = json.loads(archive.read('SHA256SUMS.json'))
                self.assertEqual(hashlib.sha256(settings).hexdigest(), manifest['settings.json'])
                archive.extractall(extracted)
            self.assertEqual(runner.settings['mse_buffer'], 0.8)
            reference = extracted / 'reference'
            state = json.loads((reference / 'state.json').read_text())
            self.assertEqual(state['settings']['mse_buffer'], 0.6)
            self.assertEqual(state['records'], completed_records)
            for key in SPEC:
                expected_run = changed['run_id'] if key in BUFFER_JOBS else self.full['run_id']
                self.assertEqual(state['records'][key]['run_id'], expected_run)

            reproduced = subprocess.run(
                [sys.executable, 'run.py', '--settings', 'settings.json', '--output', 'reproduced'],
                cwd=extracted, text=True, capture_output=True, timeout=180,
            )
            self.assertEqual(reproduced.returncode, 0, reproduced.stdout + reproduced.stderr)
            self.assertIn('22 jobs executed; 0 retained.', reproduced.stdout)
            checked = subprocess.run(
                [sys.executable, 'verify.py', 'reference', 'reproduced'],
                cwd=extracted, text=True, capture_output=True, timeout=30,
            )
            self.assertEqual(checked.returncode, 0, checked.stdout + checked.stderr)
            self.assertIn('22 job outputs agree', checked.stdout)
            reproduced_state = json.loads((extracted / 'reproduced/state.json').read_text())
            self.assertEqual(reproduced_state['settings']['mse_buffer'], 0.6)
            self.assertEqual(reproduced_state['records']['mse_buffered']['settings'], {'buffer': 0.6})
            self.assertNotEqual(reproduced_state['records']['mse_buffered']['run_id'],
                                completed_records['mse_buffered']['run_id'])
            for key in SPEC:
                self.assertEqual((reference / key / 'record.json').read_bytes(), record_bytes[key])
