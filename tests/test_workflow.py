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

    def test_parallel_stage_waits_for_both_cpue_jobs(self):
        runner = self.clone()
        original = runner.calculate

        async def exercise():
            entered, both_started, release = set(), asyncio.Event(), asyncio.Event()

            async def calculate(key, run_id):
                if key in ('cpue_a', 'cpue_b'):
                    entered.add(key)
                    if len(entered) == 2:
                        both_started.set()
                    await both_started.wait()
                    if key == 'cpue_b':
                        await release.wait()
                return await original(key, run_id)

            runner.calculate = calculate
            execution = asyncio.create_task(runner.run('extract'))
            await asyncio.wait_for(both_started.wait(), timeout=5)
            await asyncio.sleep(0.01)
            self.assertFalse(any(e['job'] == 'prepare_a' for e in runner.events))
            self.assertFalse(any(e['job'] == 'cpue_a' and e['state'] == 'complete'
                                 for e in runner.events))
            release.set()
            await execution
            self.assertTrue(all(runner.valid(key) for key in SPEC))

        asyncio.run(exercise())

    def test_failed_parallel_job_blocks_the_next_stage(self):
        runner = self.clone()
        original = runner.calculate
        previous = runner.records['prepare_b'].copy()

        async def calculate(key, run_id):
            if key == 'cpue_a':
                raise ValueError('Invalid CPUE input')
            return await original(key, run_id)

        runner.calculate = calculate
        with self.assertRaisesRegex(ValueError, 'Invalid CPUE input'):
            asyncio.run(runner.run('extract'))
        self.assertTrue(runner.valid('cpue_b'))
        self.assertEqual(runner.records['prepare_b'], previous)
        self.assertFalse(any(e['job'].startswith('prepare_') for e in runner.events))
        self.assertFalse(runner.running)

    def test_cpue_reporting_does_not_run_assessment(self):
        runner = self.clone()
        previous = runner.records['assessment_report'].copy()
        runner.execution = {'repository': 'example/workflow', 'commit': 'a' * 40}
        result = asyncio.run(runner.run('cpue_summary'))
        self.assertEqual(result['run'], ['cpue_summary','cpue_report'])
        self.assertEqual(runner.records['cpue_report']['source']['commit'], 'a' * 40)
        self.assertEqual(runner.records['assessment_report'], previous)
        result = asyncio.run(runner.run('cpue_report'))
        self.assertEqual(result['run'], ['cpue_report'])

    def test_handover_waits_before_replacing_assessment_inputs(self):
        runner = self.clone()
        previous = runner.records['prepare_a'].copy()

        async def exercise():
            waiting, received = asyncio.Event(), asyncio.Event()

            async def transfer(key):
                if key == 'prepare_a':
                    waiting.set()
                    await received.wait()

            runner.before_job = transfer
            runner.configure({'min_hooks_a': 1200})
            execution = asyncio.create_task(runner.run('cpue_a'))
            await asyncio.wait_for(waiting.wait(), timeout=5)
            self.assertFalse(execution.done())
            self.assertEqual(runner.records['prepare_a'], previous)
            self.assertEqual(runner.records['cpue_a']['run_id'], 'Run 002')
            self.assertNotIn(('prepare_a', 'running'),
                             [(event['job'], event['state']) for event in runner.events])
            received.set()
            await execution
            self.assertEqual(runner.records['prepare_a']['inputs']['cpue_a']['run_id'], 'Run 002')
            self.assertTrue(runner.valid('assessment_report'))

        asyncio.run(exercise())

    def test_changed_settings_rebuild_affected_branch(self):
        runner = self.clone()
        runner.configure({'min_hooks_a': 1200})
        result = asyncio.run(runner.run('cpue_report'))
        self.assertIn('cpue_a', result['run'])
        self.assertNotIn('cpue_b', result['run'])
        self.assertNotIn('extract', result['run'])
        self.assertGreater(runner.output('cpue_a')['sets_excluded'], 0)

    def test_partial_revision_matches_clean_full_calculation(self):
        runner = self.clone()
        retained = runner.records['cpue_b'].copy()
        runner.configure({'min_hooks_a': 1200})
        asyncio.run(runner.run('cpue_a'))
        with tempfile.TemporaryDirectory() as directory:
            fresh = Workflow(directory)
            fresh.configure({'min_hooks_a': 1200})
            asyncio.run(fresh.run())
            for key in SPEC:
                compare(runner.output(key), fresh.output(key))
        self.assertEqual(runner.records['cpue_b'], retained)

    def test_missing_output_rebuilds_its_dependants(self):
        runner = self.clone()
        (runner.directory / 'cpue_a/output.json').unlink()
        result = asyncio.run(runner.run('assessment_report'))
        self.assertIn('cpue_a', result['run'])
        self.assertNotIn('cpue_b', result['run'])
        self.assertTrue(all(runner.valid(key) for key in SPEC))

    def test_failed_preparation_can_resume_from_saved_state(self):
        runner = self.clone()
        previous = runner.records['assessment_a1'].copy()
        original = runner.calculate

        async def fail_preparation(key, run_id):
            if key == 'prepare_a':
                raise ValueError('Injected input preparation failure')
            return await original(key, run_id)

        runner.calculate = fail_preparation
        with self.assertRaisesRegex(ValueError, 'Injected'):
            asyncio.run(runner.run('prepare_a'))
        self.assertFalse(runner.running)
        self.assertNotIn('prepare_a', runner.records)
        self.assertEqual(runner.records['assessment_a1'], previous)
        resumed = Workflow(runner.directory)
        self.assertFalse(resumed.valid('prepare_a'))
        result = asyncio.run(resumed.run('prepare_a'))
        self.assertEqual(len(result['run']), 5)
        self.assertTrue(all(resumed.valid(key) for key in SPEC))

    def test_incompatible_year_is_rejected_before_model_fitting(self):
        runner = self.clone()
        output = runner.output('extract')
        output['catch'] = output['catch'][1:]
        (runner.directory / 'extract/output.json').write_text(json.dumps(output))
        with self.assertRaisesRegex(ValueError, 'no matching catch'):
            asyncio.run(runner.calculate('prepare_a', 'Input check'))

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
