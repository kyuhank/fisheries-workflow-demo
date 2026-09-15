import asyncio
import hashlib
import io
import json
from pathlib import Path
import tempfile
import unittest
import zipfile

from workflow.engine import Workflow
from workflow.spec import SPEC, STAGES
from verify import compare

MSE_JOBS = ['mse_prepare', 'mse_constant', 'mse_index', 'mse_buffered', 'mse_summary', 'mse_report']


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
        self.assertEqual(len(self.full['run']), 22)
        self.assertFalse(any(state in ('handover', 'received') for _, state in events))
        self.assertTrue(all(self.runner.valid(key) for key in SPEC))

    def test_input_preparation_reruns_only_its_dependants(self):
        runner = self.clone()
        previous = runner.records['cpue_a'].copy()
        for i in range(2):
            result = asyncio.run(runner.run('prepare_a'))
            self.assertEqual(result['run'], ['prepare_a','assessment_a1','assessment_a2',
                                             'assessment_summary','assessment_report'] + MSE_JOBS)
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

    def test_each_peer_group_blocks_its_dependants_until_every_peer_finishes(self):
        for group in [keys for keys in STAGES if len(keys) > 1]:
            with self.subTest(group=group):
                runner = self.clone()
                original = runner.calculate

                async def exercise():
                    entered, both_started, release = set(), asyncio.Event(), asyncio.Event()

                    async def calculate(key, run_id):
                        if key in group:
                            entered.add(key)
                            if len(entered) == len(group):
                                both_started.set()
                            if key == group[-1]:
                                await release.wait()
                        return await original(key, run_id)

                    runner.calculate = calculate
                    execution = asyncio.create_task(runner.run('extract'))
                    await asyncio.wait_for(both_started.wait(), 5)
                    await asyncio.sleep(0)
                    dependants = [key for key, job in SPEC.items()
                                  if set(job['parents']).intersection(group)]
                    self.assertFalse(any(event['job'] in dependants for event in runner.events))
                    release.set()
                    await execution
                    last_complete = max(i for i, event in enumerate(runner.events)
                                        if event['job'] in group and event['state'] == 'complete')
                    self.assertTrue(all(i > last_complete for i, event in enumerate(runner.events)
                                        if event['job'] in dependants and event['state'] == 'running'))

                asyncio.run(exercise())

    def test_manual_groups_pause_together_while_independent_reporting_continues(self):
        for fresh in (True, False):
            with self.subTest(fresh=fresh):
                if fresh:
                    folder = tempfile.TemporaryDirectory()
                    self.addCleanup(folder.cleanup)
                    runner = Workflow(folder.name)
                else:
                    runner = self.clone()
                previous = {key: record.copy() for key, record in runner.records.items()}

                async def exercise():
                    waiting = asyncio.Queue()
                    reports = {key: asyncio.Event() for key in ('cpue_report', 'assessment_report')}

                    def notify(event):
                        if event.get('job') in reports and event['state'] == 'complete':
                            reports[event['job']].set()

                    async def transfer(handover):
                        acknowledgement = asyncio.Event()
                        await waiting.put((handover, acknowledgement))
                        await acknowledgement.wait()
                        return False

                    runner.notify, runner.manual_transfer = notify, transfer
                    execution = asyncio.create_task(runner.run('submission' if fresh else 'extract'))
                    first, acknowledge_data = await asyncio.wait_for(waiting.get(), 5)
                    self.assertEqual(first, {'boundary': 'data', 'group': ['cpue_a', 'cpue_b']})
                    self.assertFalse(any(event['job'].startswith('cpue_') and event['state'] == 'running'
                                         for event in runner.events))
                    for key in first['group']:
                        self.assertEqual(runner.records.get(key), previous.get(key))
                    acknowledge_data.set()
                    second, acknowledge_cpue = await asyncio.wait_for(waiting.get(), 5)
                    self.assertEqual(second, {'boundary': 'cpue', 'group': ['prepare_a', 'prepare_b']})
                    await asyncio.wait_for(reports['cpue_report'].wait(), 5)
                    self.assertFalse(execution.done())
                    for key in [*second['group'], 'assessment_a1']:
                        self.assertEqual(runner.records.get(key), previous.get(key))
                    run_id = 'Run 001' if fresh else 'Run 002'
                    self.assertEqual(runner.records['cpue_report']['run_id'], run_id)
                    acknowledge_cpue.set()
                    third, acknowledge_assessment = await asyncio.wait_for(waiting.get(), 5)
                    self.assertEqual(third, {'boundary': 'assessment', 'group': ['mse_prepare']})
                    await asyncio.wait_for(reports['assessment_report'].wait(), 5)
                    self.assertFalse(execution.done())
                    for key in ['assessment_summary', 'assessment_report', *SPEC['mse_prepare']['parents']]:
                        self.assertEqual(runner.records[key]['run_id'], run_id)
                    for key in MSE_JOBS:
                        self.assertEqual(runner.records.get(key), previous.get(key))
                    self.assertFalse(any(event['job'] in MSE_JOBS and event['state'] == 'running'
                                         for event in runner.events))
                    gate = next(i for i, event in enumerate(runner.events)
                                if event['state'] == 'handover' and event['boundary'] == 'assessment')
                    self.assertTrue(all(i < gate for i, event in enumerate(runner.events)
                                        if event['job'] in SPEC['mse_prepare']['parents']
                                        and event['state'] == 'complete'))
                    acknowledge_assessment.set()
                    await execution
                    self.assertTrue(all(runner.valid(key) for key in SPEC))
                    self.assertEqual(len([event for event in runner.events if event['state'] == 'handover']), 3)
                    self.assertEqual(len([event for event in runner.events if event['state'] == 'received']), 3)
                    for key in ['cpue_a', 'cpue_b', 'prepare_a', 'prepare_b', 'mse_prepare']:
                        self.assertTrue(any('File transfer confirmed' in line for line in runner.records[key]['log']))
                    for key in SPEC:
                        compare(runner.output(key), self.runner.output(key), key)

                asyncio.run(exercise())

    def test_partial_manual_reruns_transfer_only_changed_branches(self):
        runner = self.clone()
        retained_b = {key: runner.records[key].copy() for key in
                      ['cpue_b', 'prepare_b', 'assessment_b1', 'assessment_b2']}
        transfers = []

        async def transfer(handover):
            transfers.append(handover)
            return False

        runner.manual_transfer = transfer
        for _ in range(2):
            transfers.clear()
            result = asyncio.run(runner.run('cpue_a'))
            self.assertEqual(transfers, [
                {'boundary': 'cpue', 'group': ['prepare_a']},
                {'boundary': 'assessment', 'group': ['mse_prepare']},
            ])
            self.assertEqual(len(result['run']), 14)
            self.assertEqual({key: runner.records[key] for key in retained_b}, retained_b)
        transfers.clear()
        asyncio.run(runner.run('prepare_a'))
        self.assertEqual(transfers, [{'boundary': 'assessment', 'group': ['mse_prepare']}])
        transfers.clear()
        asyncio.run(runner.run('cpue_summary'))
        self.assertEqual(transfers, [])

    def test_manual_assessment_revisions_wait_for_all_results_and_preserve_retained_inputs(self):
        for start, settings, revised in [
            ('assessment_a1', {}, ['assessment_a1']),
            ('assessment_report', {'mortality_2': 0.35}, ['assessment_a2', 'assessment_b2']),
        ]:
            with self.subTest(revised=revised):
                runner = self.clone()
                previous = {key: record.copy() for key, record in runner.records.items()}
                runner.configure(settings)
                original = runner.calculate

                async def exercise():
                    fitting, finish_fit = asyncio.Event(), asyncio.Event()
                    waiting, confirmed, report_ready = asyncio.Event(), asyncio.Event(), asyncio.Event()
                    transfers = []

                    async def calculate(key, run_id):
                        if key == revised[-1]:
                            fitting.set()
                            await finish_fit.wait()
                        return await original(key, run_id)

                    async def transfer(handover):
                        transfers.append(handover)
                        waiting.set()
                        await confirmed.wait()
                        return False

                    def notify(event):
                        if event.get('job') == 'assessment_report' and event['state'] == 'complete':
                            report_ready.set()

                    runner.calculate, runner.manual_transfer, runner.notify = calculate, transfer, notify
                    execution = asyncio.create_task(runner.run(start))
                    await asyncio.wait_for(fitting.wait(), 5)
                    self.assertEqual(transfers, [])
                    self.assertEqual(runner.records['mse_prepare'], previous['mse_prepare'])
                    finish_fit.set()
                    await asyncio.wait_for(waiting.wait(), 5)
                    await asyncio.wait_for(report_ready.wait(), 5)
                    self.assertEqual(transfers, [{'boundary': 'assessment', 'group': ['mse_prepare']}])
                    self.assertFalse(execution.done())
                    for key in MSE_JOBS:
                        self.assertEqual(runner.records[key], previous[key])
                    self.assertFalse(any(event['job'] in MSE_JOBS and event['state'] == 'running'
                                         for event in runner.events))
                    self.assertEqual(runner.records['assessment_report']['run_id'], 'Run 002')
                    confirmed.set()
                    result = await execution
                    self.assertEqual(result['run'], revised + ['assessment_summary', 'assessment_report'] + MSE_JOBS)
                    for key in result['retained']:
                        self.assertEqual(runner.records[key], previous[key])
                    for key, details in runner.records['mse_prepare']['inputs'].items():
                        self.assertEqual(details, {
                            'run_id': 'Run 002' if key in revised else 'Run 001',
                            'checksum': runner.records[key]['outputs']['output.json'],
                        })
                    self.assertTrue(all(runner.valid(key) for key in SPEC))

                asyncio.run(exercise())

    def test_manual_report_and_mse_buffer_updates_do_not_transfer_unchanged_inputs(self):
        runner = self.clone()
        transfers = []

        async def transfer(handover):
            transfers.append(handover)
            return False

        runner.manual_transfer = transfer
        previous = {key: record.copy() for key, record in runner.records.items()}
        result = asyncio.run(runner.run('assessment_report'))
        self.assertEqual(result['run'], ['assessment_report'])
        for key in MSE_JOBS:
            self.assertEqual(runner.records[key], previous[key])
        runner.configure({'mse_buffer': 0.6})
        result = asyncio.run(runner.run('mse_report'))
        self.assertEqual(result['run'], ['mse_buffered', 'mse_summary', 'mse_report'])
        self.assertEqual(runner.records['mse_prepare'], previous['mse_prepare'])
        self.assertEqual(transfers, [])
        self.assertTrue(all(runner.valid(key) for key in SPEC))

    def test_connecting_at_first_transfer_releases_later_boundaries(self):
        runner = self.clone()
        transfers = []

        async def transfer(handover):
            transfers.append(handover)
            return True

        runner.manual_transfer = transfer
        asyncio.run(runner.run('extract'))
        self.assertEqual(transfers, [{'boundary': 'data', 'group': ['cpue_a', 'cpue_b']}])
        self.assertTrue(runner.valid('assessment_report'))
        self.assertTrue(runner.valid('mse_report'))

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
        self.assertEqual(len(result['run']), 11)
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
        self.assertEqual(result['run'], ['assessment_a2','assessment_b2','assessment_summary','assessment_report'] + MSE_JOBS)
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
