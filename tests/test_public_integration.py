"""Actual released-data R/RTMB/Quarto checks, gated by the execution environment.

The same cases run against local sources and the pinned component repositories.
The altered-input case is explicitly a derived fixture, not new released data
or evidence of a live hosted service. No calculation executes merely on import.
"""
import asyncio
import copy
import io
import json
import os
from pathlib import Path
import shutil
import sqlite3
import subprocess
import tempfile
import unittest
import zipfile

from workflow.engine import FROZEN_SOURCE, ROOT, Workflow, digest, encoded
from workflow.r_bridge import RBridge
from workflow.spec import SPEC
from verify import compare, verify
from tests.native_evidence import NativeEvidence

CORE = [key for key, job in SPEC.items() if job['module'] != 'mse']
MSE = ['mse_prepare', 'mse_constant', 'mse_index', 'mse_buffered', 'mse_summary', 'mse_report']
FILTER = ['cpue_a', 'cpue_summary', 'cpue_report', 'prepare_a', 'assessment_a1',
          'assessment_a2', 'assessment_summary', 'assessment_report']
BUFFER = ['mse_buffered', 'mse_summary', 'mse_report']


@unittest.skipUnless(os.environ.get('PAPER_NATIVE_INTEGRATION') == '1',
                     'Enable PAPER_NATIVE_INTEGRATION=1 in the registered frozen-container run.')
@unittest.skipIf(os.environ.get('PAPER_DATA_MODE') == 'synthetic',
                 'Released aggregates have a separate explicit public-data gate.')
class PublicNativeIntegrationTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.evidence = NativeEvidence('public-native')
        cls.evidence.install()
        cls.addClassCleanup(cls.evidence.close)
        RBridge.require_container()
        cls.baseline = tempfile.TemporaryDirectory()
        cls.addClassCleanup(cls.baseline.cleanup)
        cls.runner = Workflow(Path(cls.baseline.name) / 'baseline')
        if cls.runner.settings['last_year'] != 2021 or cls.runner.settings['mse'] is not True:
            raise AssertionError('The public default must be the 2021 full 22-job workflow.')
        cls.source = cls.runner.source_context()
        reference = os.environ.get('PAPER_PUBLIC_REFERENCE2021')
        if reference:
            destination = cls.runner.directory
            destination.rmdir()
            shutil.copytree(reference, destination)
            cls.runner = Workflow(destination)
            if (cls.runner.settings['last_year'] != 2021 or cls.runner.settings['mse'] is not True
                    or not all(cls.runner.valid(key) for key in SPEC)):
                raise ValueError('The supplied public 2021 checkpoint is incomplete or stale; no automatic rerun.')
            cls.evidence.event({'state': 'REFERENCE_REUSED', 'source': str(Path(reference).resolve()),
                                'state_sha256': digest((Path(reference) / 'state.json').read_bytes())})
            cls.full = None
        else:
            cls.full = asyncio.run(cls.runner.run())

    @classmethod
    def tearDownClass(cls):
        pass  # Class cleanups preserve evidence and run even after setup failure.

    def setUp(self):
        self.evidence.begin_case(self.id())

    def tearDown(self):
        self.evidence.end_case()

    def clone(self):
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        destination = Path(folder.name) / 'run'
        shutil.copytree(self.runner.directory, destination)
        return Workflow(destination)

    def assert_retained(self, runner, before, selected):
        for key, record in before.items():
            if key not in selected:
                self.assertEqual(runner.records[key], record, key)

    def assert_source_custody(self, runner):
        for key, record in runner.records.items():
            self.assertEqual(record['data_source'], self.source['metadata'])
            self.assertEqual(record['software']['container'], os.environ['PAPER_RUNTIME_IMAGE'])
            self.assertEqual(record['software']['runtime'], 'Rscript (container)')
            for name, checksum in record['data_files'].items():
                path = ROOT / name
                if not path.is_file():
                    path = ROOT / 'data' / name
                self.assertEqual(digest(path.read_bytes()), checksum)
            for parent, details in record['inputs'].items():
                producer = runner.records[parent]
                self.assertEqual(details['run_id'], producer['run_id'])
                self.assertEqual(details['checksum'], producer['outputs']['output.json'])
            if os.environ.get('PAPER_SOURCE_MODE') == 'multi-repository':
                self.assertTrue(runner.sources.multi_repository)
                origin = record['analysis_source']
                self.assertRegex(origin['commit'], r'^[a-f0-9]{40}$')
                self.assertEqual(origin['sha256'], digest(runner.sources.job_path(key).read_bytes()))
                self.assertIn('code_sources', record)
                for parent, details in record['inputs'].items():
                    self.assertEqual(details['analysis_source'], runner.records[parent]['analysis_source'])
        for key, record in runner.records.items():
            rendering = record['report_rendering']
            self.assertTrue(rendering['quarto_executed'])
            self.assertEqual(rendering['engine'], 'Quarto')
            self.assertEqual(rendering['execution_engine'], 'knitr' if key.endswith('_report') else 'static')
            for name in rendering['artifacts']:
                path = runner.directory / key / name
                self.assertEqual(digest(path.read_bytes()), record['outputs'][name])
            payload = json.loads((runner.directory / key / 'report-data.json').read_text())
            compare(payload['result'], runner.output(key))

    def assert_cpue_and_catch_oracles(self, runner, last_year):
        extracted = runner.output('extract')
        self.assertEqual(extracted['data_kind'], 'public-wcpfc-albacore')
        rows = extracted['sets']
        years = list(range(2000, last_year + 1))
        strata = self.source['metadata']['reference_strata']
        self.assertEqual(len(rows), 6 * len(years))
        self.assertEqual({(row['year'], row['stratum']) for row in rows},
                         {(year, stratum) for year in years for stratum in strata})
        self.assertTrue(all(row['fleet'] == 'FJ' and 'vessel' not in row for row in rows))
        expected_catch = [row for row in self.source['catch'] if row['year'] <= last_year]
        self.assertEqual([row['year'] for row in extracted['catch']], [row['year'] for row in expected_catch])
        for actual, expected in zip(extracted['catch'], expected_catch):
            self.assertAlmostEqual(actual['catch_t'], expected['catch_t'], places=8)
        catches = {row['year']: row['catch_t'] for row in extracted['catch']}
        for suffix in ('a', 'b'):
            result = runner.output('cpue_' + suffix)
            self.assertEqual(result['data_kind'], 'public-wcpfc')
            self.assertTrue(result['converged'])
            self.assertEqual(result['rank'], result['model_columns'])
            self.assertGreater(result['residual_degrees_of_freedom'], 0)
            self.assertEqual(result['normalisation']['reference_year'], 2000)
            self.assertAlmostEqual(result['series'][0]['index'], 1)
            self.assertEqual([row['stratum'] for row in result['weights']], strata)
            for row in result['weights']:
                self.assertAlmostEqual(row['weight'], 1 / 6, delta=1e-15)
            # Each JSON weight has the same bounded decimal rounding error.
            self.assertAlmostEqual(sum(row['weight'] for row in result['weights']), 1,
                                   delta=len(strata) * 1e-15)
            self.assertEqual(len(result['prediction_grid']), 6 * len(years))
            self.assertLess(result['year_score_residual'], 1e-7)
            minimum = runner.settings['min_hooks_a'] if suffix == 'a' else 0
            accepted = [row for row in rows if row['hooks'] >= minimum]
            self.assertEqual(result['rows_excluded'], len(rows) - len(accepted))
            self.assertEqual(result['released_zero_rows'], sum(row['catch_n'] == 0 for row in accepted))
            for point in result['series']:
                selected = [row for row in accepted if row['year'] == point['year']]
                nominal = 1000 * sum(row['catch_n'] for row in selected) / sum(row['hooks'] for row in selected)
                self.assertAlmostEqual(point['nominal_cpue'], nominal, places=8)
                grid = [row for row in result['prediction_grid'] if row['year'] == point['year']]
                self.assertEqual({row['stratum'] for row in grid}, set(strata))
                self.assertTrue(all(row['hooks'] == 1000 for row in grid))
                weighted = sum(row['weight'] * row['predicted_cpue'] for row in grid)
                self.assertAlmostEqual(point['standardised_cpue'], weighted, places=8)
                self.assertAlmostEqual(point['index'], weighted / result['normalisation']['divisor'], places=8)
                if suffix == 'b':
                    self.assertAlmostEqual(point['standardised_cpue'], nominal, places=7)
            prepared = runner.output('prepare_' + suffix)['rows']
            self.assertEqual([row['year'] for row in prepared], years)
            for row in prepared:
                self.assertAlmostEqual(row['catch_t'], catches[row['year']], places=8)

    def test_1_default_public_workflow_has_22_jobs_and_actual_fixed_support(self):
        if self.full is not None:
            self.assertEqual(self.full['run'], list(SPEC))
        self.assertEqual(len(self.runner.records), 22)
        self.assertEqual(self.runner.output('qc')['returned'], [])
        self.assertFalse(any(event['state'] == 'returned' for event in self.runner.events))
        self.assertTrue(all(self.runner.valid(key) for key in SPEC))
        self.assert_source_custody(self.runner)
        self.assert_cpue_and_catch_oracles(self.runner, 2021)
        with sqlite3.connect(self.runner.directory / 'database/snapshot.sqlite') as db:
            columns = {row[1] for row in db.execute('pragma table_info(sets)')}
            self.assertTrue({'source_row', 'fleet', 'quarter', 'cell', 'stratum'} <= columns)
            self.assertNotIn('vessel', columns)

    def test_2_2022_data_update_matches_a_fresh_full_workflow(self):
        runner = self.clone()
        reference = os.environ.get('PAPER_PUBLIC_REFERENCE2022')
        if reference:
            shutil.rmtree(runner.directory)
            shutil.copytree(reference, runner.directory)
            runner = Workflow(runner.directory)
            expected = {**self.runner.settings, 'last_year': 2022}
            if (runner.settings != expected or len(runner.records) != 22 or
                    not all(runner.valid(key) for key in SPEC)):
                raise ValueError('The supplied public 2022 checkpoint is incomplete or stale; no automatic rerun.')
            self.evidence.event({'state': 'REFERENCE_REUSED', 'purpose': 'completed 2022 data update',
                                 'source': str(Path(reference).resolve()),
                                 'state_sha256': digest((Path(reference) / 'state.json').read_bytes())})
            self.assertEqual(runner.last_plan['run'], list(SPEC))
            self.assertEqual(runner.last_plan['retained'], [])
        else:
            runner.configure({'last_year': 2022})
            outcome = asyncio.run(runner.run())
            self.assertEqual(outcome['run'], list(SPEC))
            self.assertEqual(outcome['retained'], [])
        self.assert_cpue_and_catch_oracles(runner, 2022)
        self.assertEqual(len(runner.records), 22)
        with tempfile.TemporaryDirectory() as directory:
            fresh = Workflow(directory)
            fresh.configure({'last_year': 2022})
            self.assertEqual(asyncio.run(fresh.run())['run'], list(SPEC))
            for key in SPEC:
                compare(runner.output(key), fresh.output(key), key)
        self.assert_source_custody(runner)

    def test_3_cpue_filter_updates_only_declared_branch_and_matches_fresh_outputs(self):
        runner = self.clone()
        before = copy.deepcopy(runner.records)
        runner.configure({'min_hooks_a': 1200})
        outcome = asyncio.run(runner.run('cpue_a'))
        selected = FILTER + MSE
        self.assertEqual(outcome['run'], selected)
        self.assertEqual(len(outcome['retained']), 8)
        self.assert_retained(runner, before, selected)
        self.assert_cpue_and_catch_oracles(runner, 2021)
        with tempfile.TemporaryDirectory() as directory:
            fresh = Workflow(directory)
            fresh.configure({'min_hooks_a': 1200})
            self.assertEqual(asyncio.run(fresh.run())['run'], list(SPEC))
            for key in SPEC:
                compare(runner.output(key), fresh.output(key), key)

    def repeat_bundle(self, runner, expected_count, job=None):
        with tempfile.TemporaryDirectory() as directory:
            extracted = Path(directory)
            with zipfile.ZipFile(io.BytesIO(runner.bundle())) as archive:
                manifest = json.loads(archive.read('SHA256SUMS.json'))
                for name, checksum in manifest.items():
                    self.assertEqual(digest(archive.read(name)), checksum, name)
                for pin in self.source['metadata']['sources']:
                    self.assertEqual(digest(archive.read(pin['file'])), pin['sha256'])
                self.assertIn('workflow/extract-public.sql', manifest)
                self.assertIn('scripts/import-public-data.py', manifest)
                self.assertIn('PAPER_DATA_MODE=public', archive.read('REPRODUCE.txt').decode())
                self.assertEqual(json.loads(archive.read('data/public-source.json'))['metadata'],
                                 self.source['metadata'])
                archive.extractall(extracted)
            arguments = ['JOB=' + job] if job else []
            environment = dict(os.environ, PAPER_TEST_EVIDENCE_PARENT_CASE=self.id())
            for target in ('inside-reproduce', 'inside-compare'):
                process = subprocess.run(['make', '--no-print-directory', '--silent', target, *arguments],
                                         cwd=extracted, env=environment, capture_output=True, text=True, timeout=600)
                self.assertEqual(process.returncode, 0, process.stdout + process.stderr)
            self.assertEqual(verify(extracted / 'reference', extracted / 'reproduced', job), expected_count)
            record = json.loads((extracted / 'reproduced/submission/record.json').read_text())
            self.assertEqual(record['data_source'], self.source['metadata'])
            self.assertEqual(record['data_files']['data/public-source.json'],
                             digest((ROOT / 'data/public-source.json').read_bytes()))
            if hasattr(runner, 'hosted_data'):
                self.assertEqual((extracted / FROZEN_SOURCE).read_bytes(), encoded(runner.hosted_data))
                self.assertEqual(record['data_files'][FROZEN_SOURCE], digest(encoded(runner.hosted_data)))

    def test_4_download_reproduces_the_explicit_22_job_public_workflow(self):
        runner = self.clone()
        self.repeat_bundle(runner, 22)

    def test_5_derived_public_input_fixture_is_frozen_for_single_job_reproduction(self):
        with tempfile.TemporaryDirectory() as directory:
            runner = Workflow(directory)
            runner.configure({'mse': False})
            runner.hosted_data = copy.deepcopy(self.source)
            selected = next(row for row in runner.hosted_data['sets']
                            if row['year'] == 2000 and row['stratum'] in self.source['metadata']['reference_strata'])
            selected['catch_n'] += 7
            outcome = asyncio.run(runner.run('cpue_a', 'job'))
            self.assertEqual(outcome['run'], ['submission', 'qc', 'database', 'extract', 'cpue_a'])
            self.assertNotEqual(runner.output('cpue_a'), self.runner.output('cpue_a'))
            self.assertEqual(runner.output('submission')['data_kind'], 'public-wcpfc-albacore')
            self.repeat_bundle(runner, 1, 'cpue_a')

    def test_public_snapshots_reject_unsupplied_synthetic_years(self):
        runner = self.clone()
        for year in (2023, 2024):
            with self.subTest(year=year), self.assertRaisesRegex(ValueError, '2021 and 2022 snapshots'):
                runner.configure({'last_year': year})


@unittest.skipUnless(os.environ.get('PAPER_NATIVE_INTEGRATION') == '1',
                     'Enable actual native execution in the frozen container.')
@unittest.skipIf(os.environ.get('PAPER_DATA_MODE') == 'synthetic',
                 'Reader updates require the explicit public-data gate.')
class PublicReaderUpdateIntegrationTest(unittest.TestCase):
    """UI growth and buffer updates compared with separate fresh full workflows."""
    clone = PublicNativeIntegrationTest.clone
    assert_retained = PublicNativeIntegrationTest.assert_retained
    assert_source_custody = PublicNativeIntegrationTest.assert_source_custody

    @classmethod
    def setUpClass(cls):
        cls.evidence = NativeEvidence('public-reader-updates')
        cls.evidence.install()
        cls.addClassCleanup(cls.evidence.close)
        RBridge.require_container()
        cls.baseline = tempfile.TemporaryDirectory()
        cls.addClassCleanup(cls.baseline.cleanup)
        destination = Path(cls.baseline.name) / 'baseline-2022'
        reference = os.environ.get('PAPER_PUBLIC_REFERENCE2022')
        if reference:
            shutil.copytree(reference, destination)
        cls.runner = Workflow(destination)
        cls.source = cls.runner.source_context()
        if reference:
            if (cls.runner.settings != {'last_year': 2022, 'min_hooks_a': 0, 'growth_rate_2': .3,
                                         'mse': True, 'mse_buffer': .8}
                    or not all(cls.runner.valid(key) for key in SPEC)):
                raise ValueError('The supplied public 2022 checkpoint is incomplete or stale; no automatic rerun.')
            cls.evidence.event({'state': 'REFERENCE_REUSED', 'source': str(Path(reference).resolve()),
                                'state_sha256': digest((Path(reference) / 'state.json').read_bytes())})
        else:
            cls.runner.configure({'last_year': 2022})
            asyncio.run(cls.runner.run())

    def setUp(self):
        self.evidence.begin_case(self.id())

    def tearDown(self):
        self.evidence.end_case()

    def test_growth_then_buffer_updates_match_fresh_full_workflows(self):
        runner = self.clone()
        before = copy.deepcopy(runner.records)
        growth = ['assessment_a2', 'assessment_b2', 'assessment_summary', 'assessment_report'] + MSE
        runner.configure({'growth_rate_2': .35})
        result = asyncio.run(runner.run('assessment_report'))
        self.assertEqual(result['run'], growth)
        self.assertEqual(len(result['retained']), 12)
        self.assert_retained(runner, before, growth)
        self.assertEqual(runner.output('assessment_a2')['r'], .35)
        self.assertEqual(runner.output('assessment_a1')['r'], .25)
        with tempfile.TemporaryDirectory() as directory:
            fresh = Workflow(directory)
            fresh.configure({'last_year': 2022, 'growth_rate_2': .35})
            self.assertEqual(asyncio.run(fresh.run())['run'], list(SPEC))
            for key in SPEC:
                compare(runner.output(key), fresh.output(key), key)
        before = copy.deepcopy(runner.records)
        original_errors = copy.deepcopy(runner.output('mse_prepare')['error_streams'])
        runner.configure({'mse_buffer': .6})
        result = asyncio.run(runner.run('mse_report'))
        self.assertEqual(result['run'], BUFFER)
        self.assertEqual(len(result['retained']), 19)
        self.assert_retained(runner, before, BUFFER)
        self.assertEqual(runner.output('mse_buffered')['error_streams'], original_errors)
        self.assertEqual(runner.output('mse_buffered')['rule_settings'], {'buffer': .6})
        with tempfile.TemporaryDirectory() as directory:
            fresh = Workflow(directory)
            fresh.configure({'last_year': 2022, 'growth_rate_2': .35, 'mse_buffer': .6})
            self.assertEqual(asyncio.run(fresh.run())['run'], list(SPEC))
            for key in SPEC:
                compare(runner.output(key), fresh.output(key), key)
        self.assert_source_custody(runner)
