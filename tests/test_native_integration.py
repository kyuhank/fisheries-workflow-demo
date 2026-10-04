"""Six actual container R/RTMB/Quarto integration cases, explicitly enabled in CI.

This is execution consistency and workflow custody evidence. The separate R
science script owns mathematical and declared synthetic-data checks.
"""
import asyncio
import copy
import hashlib
import io
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
import zipfile

from workflow.engine import Workflow
from workflow.r_bridge import RBridge
from workflow.spec import SPEC
from verify import compare, verify

REPORTS = ('cpue_report', 'assessment_report', 'mse_report')
BUFFER = ('mse_buffered', 'mse_summary', 'mse_report')


@unittest.skipUnless(os.environ.get('PAPER_NATIVE_INTEGRATION') == '1',
                     'Enable PAPER_NATIVE_INTEGRATION=1 inside the frozen actual container.')
class NativeIntegrationTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        RBridge.require_container()
        cls.baseline = tempfile.TemporaryDirectory()
        cls.runner = Workflow(Path(cls.baseline.name) / 'baseline')
        cls.runner.configure({'mse': True})
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

    def test_1_fresh_R_results_and_genuine_Quarto_custody(self):
        self.assertEqual(self.full['run'], list(SPEC))
        self.assertTrue(all(self.runner.valid(key) for key in SPEC))
        for key, record in self.runner.records.items():
            self.assertEqual(record['software']['container'], os.environ['PAPER_RUNTIME_IMAGE'])
            self.assertEqual(record['software']['runtime'], 'Rscript (container)')
            self.assertIn('RTMB', record['software'])
            self.assertIn('quarto', record['software'])
            self.assertIn(f'jobs/{key}/run.R', record['code'])
        for key in REPORTS:
            record = self.runner.records[key]
            self.assertTrue(record['report_rendering']['quarto_executed'])
            self.assertEqual(record['report_rendering']['version'], record['software']['quarto'])
            for name in ('report.html', 'report.qmd', 'report-data.json'):
                path = self.runner.directory / key / name
                self.assertEqual(hashlib.sha256(path.read_bytes()).hexdigest(), record['outputs'][name])
            payload = json.loads((self.runner.directory / key / 'report-data.json').read_text())
            compare(payload['result'], self.runner.output(key))
            self.assertEqual(payload['record']['inputs'], record['inputs'])
            html = (self.runner.directory / key / 'report.html').read_text()
            self.assertIn('quarto', html.lower())
            self.assertIn(os.environ['PAPER_RUNTIME_IMAGE'], html)

        # The hosted process worker invokes the identical R job adapter with saved parents.
        os.environ.setdefault('PAPER_REQUEST_ID', '00000000-0000-4000-8000-000000000001')
        from cloud.run import calculate_independent_job, PARALLEL_JOBS
        for key in sorted(PARALLEL_JOBS):
            value = calculate_independent_job(str(self.runner.directory), key,
                                              self.runner.settings, 'Adapter check')
            compare(value, self.runner.output(key), key)

    def test_2_CPUE_filter_partial_update_matches_rebuilt_branch(self):
        runner = self.clone()
        before = copy.deepcopy(runner.records)
        runner.configure({'min_hooks_a': 1200})
        result = asyncio.run(runner.run('cpue_a'))
        self.assertEqual(len(result['run']), 14)
        self.assertGreater(runner.output('cpue_a')['sets_excluded'], 0)
        for key in result['retained']:
            self.assertEqual(runner.records[key], before[key])
        # Refit the same branch from preserved exact data; no additional full workflow render.
        fresh = self.clone()
        fresh.configure({'min_hooks_a': 1200})
        for key in result['run']:
            fresh.records.pop(key, None)
        asyncio.run(fresh.run('cpue_a'))
        for key in SPEC:
            compare(runner.output(key), fresh.output(key), key)

    def test_3_growth_sensitivity_changes_only_declared_fit_descendants(self):
        runner = self.clone()
        before = copy.deepcopy(runner.records)
        runner.configure({'growth_rate_2': .35})
        result = asyncio.run(runner.run('assessment_report'))
        self.assertEqual(result['run'], ['assessment_a2', 'assessment_b2',
                         'assessment_summary', 'assessment_report', 'mse_prepare',
                         'mse_constant', 'mse_index', 'mse_buffered', 'mse_summary', 'mse_report'])
        self.assertEqual(runner.output('assessment_a2')['r'], .35)
        self.assertEqual(runner.output('assessment_a1')['r'], .25)
        for key in result['retained']:
            self.assertEqual(runner.records[key], before[key])

    def test_4_buffer_reuses_paired_R_errors_and_reset_repeats_results(self):
        runner = self.clone()
        before = copy.deepcopy(runner.records)
        original = {key: runner.output(key) for key in BUFFER}
        runner.configure({'mse_buffer': .6})
        self.assertEqual(asyncio.run(runner.run('mse_report'))['run'], list(BUFFER))
        self.assertEqual(runner.records['mse_prepare'], before['mse_prepare'])
        buffered = runner.output('mse_buffered')
        self.assertEqual(buffered['error_streams'], runner.output('mse_constant')['error_streams'])
        self.assertEqual(buffered['error_streams'], original['mse_buffered']['error_streams'])
        self.assertEqual(buffered['rule_settings'], {'buffer': .6})
        self.assertNotEqual(buffered['metrics']['mean_catch_t'], original['mse_buffered']['metrics']['mean_catch_t'])
        restored = Workflow(runner.directory)
        restored.configure({'mse_buffer': .8})
        self.assertEqual(asyncio.run(restored.run('mse_report'))['run'], list(BUFFER))
        for key in BUFFER:
            compare(restored.output(key), original[key], key)
        for key in SPEC:
            if key not in BUFFER:
                self.assertEqual(restored.records[key], before[key])

    def test_5_report_only_renders_actual_QMD_without_replacing_inputs(self):
        runner = self.clone()
        before = copy.deepcopy(runner.records)
        result = asyncio.run(runner.run('assessment_report'))
        self.assertEqual(result['run'], ['assessment_report'])
        for key in SPEC:
            if key != 'assessment_report':
                self.assertEqual(runner.records[key], before[key])
        self.assertTrue(runner.records['assessment_report']['report_rendering']['quarto_executed'])
        compare(runner.output('assessment_report'), self.runner.output('assessment_report'))

    def test_6_download_reproduces_actual_results_inside_same_container(self):
        runner = self.clone()
        runner.configure({'mse_buffer': .6})
        asyncio.run(runner.run('mse_report'))
        records = copy.deepcopy(runner.records)
        runner.configure({'mse_buffer': .8})
        with tempfile.TemporaryDirectory() as directory:
            extracted = Path(directory)
            with zipfile.ZipFile(io.BytesIO(runner.bundle())) as archive:
                settings = json.loads(archive.read('settings.json'))
                self.assertEqual(settings['mse_buffer'], .6)
                for name, checksum in json.loads(archive.read('SHA256SUMS.json')).items():
                    self.assertEqual(hashlib.sha256(archive.read(name)).hexdigest(), checksum)
                recipe = archive.read('REPRODUCE.txt').decode()
                self.assertIn('docker run --rm --network none', recipe)
                self.assertIn(os.environ['PAPER_RUNTIME_IMAGE'], recipe)
                archive.extractall(extracted)
            # This test is already inside that declared container; no nested Docker daemon.
            process = subprocess.run([sys.executable, 'run.py', '--settings', 'settings.json',
                                      '--output', 'reproduced'], cwd=extracted,
                                     capture_output=True, text=True, timeout=360)
            self.assertEqual(process.returncode, 0, process.stdout + process.stderr)
            self.assertEqual(verify(extracted / 'reference', extracted / 'reproduced'), 22)
            state = json.loads((extracted / 'reference/state.json').read_text())
            self.assertEqual(state['records'], records)
            for key in REPORTS:
                preserved = json.loads((extracted / 'reproduced' / key / 'record.json').read_text())
                self.assertTrue(preserved['report_rendering']['quarto_executed'])
