import asyncio
import hashlib
import io
import json
from pathlib import Path
import tempfile
import unittest
import zipfile

from workflow.engine import Workflow
from workflow.spec import SPEC
from verify import compare


class WorkflowTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.base = tempfile.TemporaryDirectory()
        cls.runner = Workflow(Path(cls.base.name) / 'baseline')
        cls.full = asyncio.run(cls.runner.run())

    @classmethod
    def tearDownClass(cls):
        cls.base.cleanup()

    def clone(self):
        import shutil
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        shutil.copytree(self.runner.directory, Path(folder.name) / 'run')
        return Workflow(Path(folder.name) / 'run')

    def test_submission_returns_then_passes(self):
        events = [(e['job'], e['state']) for e in self.full['events']]
        sequence = [('submission','running'), ('submission','complete'), ('qc','running'),
                    ('qc','failed'), ('submission','returned'), ('submission','running'),
                    ('submission','complete'), ('qc','running'), ('qc','complete'),
                    ('database','running')]
        self.assertEqual(events[:len(sequence)], sequence)
        self.assertEqual(len(self.full['run']), 16)
        self.assertTrue(all(self.runner.valid(key) for key in SPEC))

    def test_input_preparation_reruns_only_its_dependants(self):
        runner = self.clone()
        previous = runner.records['cpue_a'].copy()
        for i in range(2):
            result = asyncio.run(runner.run('prepare_a'))
            self.assertEqual(result['run'], ['prepare_a','assessment_a1','assessment_a2',
                                             'assessment_summary','assessment_report'])
            self.assertEqual(runner.records['cpue_a'], previous)
            self.assertFalse(runner.running)

    def test_cpue_reporting_does_not_run_assessment(self):
        runner = self.clone()
        result = asyncio.run(runner.run('cpue_summary'))
        self.assertEqual(result['run'], ['cpue_summary','cpue_report'])
        result = asyncio.run(runner.run('cpue_report'))
        self.assertEqual(result['run'], ['cpue_report'])

    def test_changed_settings_rebuild_affected_branch(self):
        runner = self.clone()
        runner.configure({'min_hooks_a': 1200})
        result = asyncio.run(runner.run('cpue_report'))
        self.assertIn('cpue_a', result['run'])
        self.assertNotIn('cpue_b', result['run'])
        self.assertNotIn('extract', result['run'])
        self.assertGreater(runner.output('cpue_a')['sets_excluded'], 0)

    def test_tampered_output_is_rebuilt(self):
        runner = self.clone()
        (runner.directory / 'cpue_a/output.json').write_text('{}')
        result = asyncio.run(runner.run('prepare_a'))
        self.assertIn('cpue_a', result['run'])
        self.assertTrue(runner.valid('cpue_a'))

    def test_mortality_change_retains_other_fits(self):
        runner = self.clone()
        runner.configure({'mortality_2': 0.35})
        result = asyncio.run(runner.run('assessment_report'))
        self.assertEqual(result['run'], ['assessment_a2','assessment_b2','assessment_summary','assessment_report'])
        self.assertEqual(runner.records['assessment_a1']['run_id'], 'Run 001')

    def test_data_versions_do_not_accumulate(self):
        runner = self.clone()
        runner.configure({'last_year': 2024})
        asyncio.run(runner.run())
        count = runner.output('database')['rows']
        self.assertGreater(count, self.runner.output('database')['rows'])
        asyncio.run(runner.run())
        self.assertEqual(runner.output('database')['rows'], count)
        runner.configure({'last_year': 2021})
        asyncio.run(runner.run())
        self.assertEqual(runner.output('database')['last_year'], 2021)

    def test_clean_run_and_bundle(self):
        with tempfile.TemporaryDirectory() as directory:
            fresh = Workflow(directory)
            asyncio.run(fresh.run())
            for key in SPEC:
                compare(self.runner.output(key), fresh.output(key), key)
            with zipfile.ZipFile(io.BytesIO(fresh.bundle())) as archive:
                for name, expected in json.loads(archive.read('SHA256SUMS.json')).items():
                    self.assertEqual(hashlib.sha256(archive.read(name)).hexdigest(), expected)
                self.assertIn('verify.py', archive.namelist())

    def test_invalid_setting_is_rejected(self):
        with self.assertRaises(ValueError):
            self.clone().configure({'last_year': 2050})

    def test_data_coverage_and_assessment_diagnostics(self):
        data = self.runner.output('database')
        self.assertEqual(sum(row['observations'] for row in data['annual']), data['rows'])
        for row in data['annual']:
            self.assertEqual(sum(row['vessels'].values()), row['observations'])
        for key in ['assessment_a1','assessment_a2','assessment_b1','assessment_b2']:
            result = self.runner.output(key)
            self.assertEqual(result['catch_check'], 'Pass')
            self.assertEqual(len(result['series']), len(data['annual']))
            self.assertTrue(all(row['fitted_index'] > 0 for row in result['series']))
            self.assertAlmostEqual(sum(row['log_residual'] for row in result['series']), 0, places=8)


if __name__ == '__main__':
    unittest.main()
