"""Actual container R/RTMB/Quarto integration cases, explicitly enabled in CI.

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
import tempfile
import unittest
import zipfile

from workflow.engine import FROZEN_SOURCE, Workflow, digest, encoded
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

    def test_2_CPUE_filter_partial_update_matches_independent_full_workflow(self):
        runner = self.clone()
        before = copy.deepcopy(runner.records)
        runner.configure({'min_hooks_a': 1200})
        result = asyncio.run(runner.run('cpue_a'))
        self.assertEqual(len(result['run']), 14)
        self.assertGreater(runner.output('cpue_a')['sets_excluded'], 0)
        for key in result['retained']:
            self.assertEqual(runner.records[key], before[key])
        # Independent fresh full workflow: no restored checkpoint or baseline outputs.
        with tempfile.TemporaryDirectory() as directory:
            fresh = Workflow(directory)
            fresh.configure({'mse': True, 'min_hooks_a': 1200})
            full = asyncio.run(fresh.run())
            self.assertEqual(full['run'], list(SPEC))
            self.assertEqual(full['retained'], [])
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
                self.assertIn('make reproduce', recipe)
                self.assertIn(os.environ['PAPER_RUNTIME_IMAGE'], recipe)
                archive.extractall(extracted)
            # This test is already inside that declared container; no nested Docker daemon.
            process = subprocess.run(['make', '--no-print-directory', '--silent', 'inside-reproduce'], cwd=extracted,
                                     capture_output=True, text=True, timeout=360)
            self.assertEqual(process.returncode, 0, process.stdout + process.stderr)
            self.assertEqual(verify(extracted / 'reference', extracted / 'reproduced'), 22)
            check = subprocess.run(['make', '--no-print-directory', '--silent', 'inside-compare'],
                                   cwd=extracted, capture_output=True, text=True, timeout=30)
            self.assertEqual(check.returncode, 0, check.stdout + check.stderr)
            state = json.loads((extracted / 'reference/state.json').read_text())
            self.assertEqual(state['records'], records)
            for key in REPORTS:
                preserved = json.loads((extracted / 'reproduced' / key / 'record.json').read_text())
                self.assertTrue(preserved['report_rendering']['quarto_executed'])

    def test_7_hosted_bundle_freezes_different_actual_inputs_for_fresh_R_reproduction(self):
        identity = {name: os.environ.get(name) for name in
                    ('GITHUB_SHA', 'GITHUB_REPOSITORY', 'GITHUB_RUN_ID')}
        if not all(identity.values()):
            self.skipTest('This hosted-coordinator fixture requires actual GitHub native CI identity.')
        self.assertRegex(identity['GITHUB_SHA'], r'^[a-f0-9]{40}$')
        self.assertRegex(identity['GITHUB_REPOSITORY'], r'^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$')
        self.assertRegex(identity['GITHUB_RUN_ID'], r'^[0-9]+$')
        os.environ.setdefault('PAPER_REQUEST_ID', '00000000-0000-4000-8000-000000000001')
        from cloud.run import HostedWorkflow
        source = self.runner.source_context()
        supplied = copy.deepcopy({'sets': source['sets'], 'catch': source['catch']})
        supplied['sets'][0]['catch_n'] += 7
        frozen = encoded(supplied)
        with tempfile.TemporaryDirectory() as directory:
            # Use the actual hosted coordinator/adapter without an API or
            # credential; record the real enclosing native CI execution.
            runner = HostedWorkflow.__new__(HostedWorkflow)
            Workflow.__init__(runner, Path(directory) / 'hosted')
            runner.hosted_data, runner.pool = supplied, None
            runner.execution = {'provider': 'GitHub Actions',
                                'purpose': 'native-hosted-input-fixture',
                                'repository': identity['GITHUB_REPOSITORY'],
                                'commit': identity['GITHUB_SHA'],
                                'github_run': identity['GITHUB_RUN_ID'],
                                'container': RBridge.require_container(),
                                'data_checksum': digest(frozen)}
            runner.configure({'mse': True})
            result = asyncio.run(runner.run())
            self.assertEqual(result['run'], list(SPEC))
            self.assertNotEqual(runner.output('cpue_a'), self.runner.output('cpue_a'))
            extracted = Path(directory) / 'extracted'
            with zipfile.ZipFile(io.BytesIO(runner.bundle())) as archive:
                self.assertEqual(archive.namelist().count(FROZEN_SOURCE), 1)
                self.assertEqual(archive.read(FROZEN_SOURCE), frozen)
                manifest = json.loads(archive.read('SHA256SUMS.json'))
                self.assertEqual(manifest[FROZEN_SOURCE],
                                 runner.records['submission']['execution']['data_checksum'])
                archive.extractall(extracted)
            process = subprocess.run(['make', '--no-print-directory', '--silent', 'inside-reproduce'], cwd=extracted,
                                     capture_output=True, text=True, timeout=360)
            self.assertEqual(process.returncode, 0, process.stdout + process.stderr)
            self.assertEqual(verify(extracted / 'reference', extracted / 'reproduced'), 22)
            check = subprocess.run(['make', '--no-print-directory', '--silent', 'inside-compare'],
                                   cwd=extracted, capture_output=True, text=True, timeout=30)
            self.assertEqual(check.returncode, 0, check.stdout + check.stderr)
            reproduced = json.loads((extracted / 'reproduced/submission/output.json').read_text())
            self.assertEqual(reproduced, runner.output('submission'))
            record = json.loads((extracted / 'reproduced/submission/record.json').read_text())
            self.assertEqual(record['data_files']['frozen-source.json'], digest(frozen))


    def test_8_single_job_download_repeats_only_its_required_inputs(self):
        runner = self.clone()
        runner.configure({'min_hooks_a': 1200})
        asyncio.run(runner.run('cpue_a', 'job'))
        original = copy.deepcopy(runner.records)
        runner.configure({'min_hooks_a': 0})
        with tempfile.TemporaryDirectory() as directory:
            extracted = Path(directory)
            with zipfile.ZipFile(io.BytesIO(runner.bundle())) as archive:
                recipe = archive.read('REPRODUCE.txt').decode()
                self.assertIn('Run: make reproduce', recipe)
                self.assertIn('Check: make compare', recipe)
                self.assertEqual(recipe.count('JOB=cpue_a'), 2)
                self.assertIn('Other saved results retain their earlier records', recipe)
                self.assertEqual(json.loads(archive.read('settings.json'))['min_hooks_a'], 1200)
                archive.extractall(extracted)
            preserved = (extracted / 'reference/cpue_b/record.json').read_bytes()
            for target in ('inside-reproduce', 'inside-compare'):
                process = subprocess.run(['make', '--no-print-directory', '--silent', target,
                                          'JOB=cpue_a'], cwd=extracted,
                                         capture_output=True, text=True, timeout=360)
                self.assertEqual(process.returncode, 0, process.stdout + process.stderr)
            self.assertEqual(verify(extracted / 'reference', extracted / 'reproduced', 'cpue_a'), 1)
            self.assertFalse((extracted / 'reproduced/cpue_b').exists())
            self.assertEqual((extracted / 'reference/cpue_b/record.json').read_bytes(), preserved)
            self.assertEqual(json.loads((extracted / 'reference/state.json').read_text())['records'], original)
