"""A job request rebuilds required inputs without executing dependent jobs."""
import asyncio
from copy import deepcopy
import io
import json
from pathlib import Path
import shlex
import shutil
import subprocess
import sys
import tempfile
import unittest
import zipfile

from workflow.engine import Workflow
from workflow.spec import SPEC


class JobScopeTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.baseline = tempfile.TemporaryDirectory()
        cls.runner = Workflow(cls.baseline.name)
        asyncio.run(cls.runner.run())

    @classmethod
    def tearDownClass(cls):
        cls.baseline.cleanup()

    def clone(self):
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        directory = Path(folder.name) / 'run'
        shutil.copytree(self.runner.directory, directory)
        return Workflow(directory)

    def assert_preserved(self, runner, previous, executed):
        for key, record in previous.items():
            if key not in executed:
                self.assertEqual(runner.records[key], record, key)
        self.assertEqual({event['job'] for event in runner.events
                          if event['state'] == 'running'}, set(executed))

    def test_fresh_job_builds_only_its_inputs_and_retains_no_missing_results(self):
        with tempfile.TemporaryDirectory() as directory:
            runner = Workflow(directory)
            expected = ['submission', 'qc', 'database', 'extract', 'cpue_a']
            plan = runner.plan('cpue_a', 'job')
            self.assertEqual(plan['run'], expected)
            self.assertEqual(plan['retained'], [])
            self.assertEqual(plan['scope'], 'job')
            result = asyncio.run(runner.run('cpue_a', 'job'))
            self.assertEqual(result['run'], expected)
            self.assertEqual(set(result['records']), set(expected))
            self.assertEqual(result['retained'], [])
            self.assertTrue(all(runner.valid(key) for key in expected))
            self.assertFalse((runner.directory / 'cpue_summary').exists())
            next_plan = runner.plan('cpue_b', 'job')
            self.assertEqual(next_plan['run'], ['cpue_b'])
            self.assertEqual(next_plan['retained'], expected)

    def test_valid_job_runs_again_without_its_dependants(self):
        runner = self.clone()
        previous = deepcopy(runner.records)
        result = asyncio.run(runner.run('cpue_a', 'job'))
        self.assertEqual(result['run'], ['cpue_a'])
        self.assertEqual(result['retained'], [key for key in SPEC if key != 'cpue_a'])
        self.assert_preserved(runner, previous, ['cpue_a'])
        self.assertNotEqual(runner.records['cpue_a']['run_id'], previous['cpue_a']['run_id'])
        self.assertIn('cpue_summary', runner.plan('cpue_a', 'job')['changed'])
        self.assertFalse(runner.valid('cpue_summary'))

    def test_unrelated_missing_results_and_changed_settings_do_not_expand_job_run(self):
        runner = self.clone()
        runner.configure({'min_hooks_a': 1200, 'mortality_2': .35, 'mse_buffer': .6})
        runner.records.pop('mse_report')
        previous = deepcopy(runner.records)
        plan = runner.plan('assessment_b1', 'job')
        self.assertEqual(plan['run'], ['assessment_b1'])
        self.assertTrue({'cpue_a', 'assessment_a2', 'assessment_b2', 'mse_buffered', 'mse_report'}
                        <= set(plan['changed']))
        self.assertNotIn('mse_report', plan['retained'])
        result = asyncio.run(runner.run('assessment_b1', 'job'))
        self.assertEqual(result['run'], ['assessment_b1'])
        self.assert_preserved(runner, previous, ['assessment_b1'])

    def test_changed_ancestor_rebuilds_intervening_inputs_but_no_other_branch(self):
        runner = self.clone()
        runner.configure({'min_hooks_a': 1200})
        previous = deepcopy(runner.records)
        # The saved intermediate still matches its saved parent record. Planning
        # must also follow the parent's changed settings through to the target.
        self.assertTrue(runner.valid('prepare_a'))
        expected = ['cpue_a', 'prepare_a', 'assessment_a1']
        result = asyncio.run(runner.run('assessment_a1', 'job'))
        self.assertEqual(result['run'], expected)
        self.assert_preserved(runner, previous, expected)
        self.assertTrue(all(runner.valid(key) for key in expected))
        self.assertEqual(runner.records['prepare_a']['inputs']['cpue_a']['run_id'], result['run_id'])

    def test_corrupt_required_file_rebuilds_its_path_without_parallel_siblings(self):
        runner = self.clone()
        previous = deepcopy(runner.records)
        (runner.directory / 'extract' / 'output.json').write_text('{}')
        expected = ['extract', 'cpue_a', 'prepare_a', 'assessment_a1']
        result = asyncio.run(runner.run('assessment_a1', 'job'))
        self.assertEqual(result['run'], expected)
        self.assert_preserved(runner, previous, expected)
        self.assertTrue(all(runner.valid(key) for key in expected))

    def test_job_mse_preparation_waits_for_revised_assessment_inputs_and_transfer(self):
        runner = self.clone()
        runner.configure({'mortality_2': .35})
        previous = deepcopy(runner.records)

        async def exercise():
            waiting, confirmed = asyncio.Event(), asyncio.Event()

            async def transfer(handover):
                self.assertEqual(handover, {'boundary': 'assessment', 'group': ['mse_prepare']})
                self.assertTrue(all(runner.records[key]['run_id'] == 'Run 002'
                                    for key in ('assessment_a2', 'assessment_b2')))
                waiting.set()
                await confirmed.wait()
                return False

            runner.manual_transfer = transfer
            execution = asyncio.create_task(runner.run('mse_prepare', 'job'))
            await asyncio.wait_for(waiting.wait(), 5)
            self.assertFalse(execution.done())
            self.assertEqual(runner.records['mse_prepare'], previous['mse_prepare'])
            self.assertEqual(runner.records['assessment_report'], previous['assessment_report'])
            confirmed.set()
            return await execution

        result = asyncio.run(exercise())
        expected = ['assessment_a2', 'assessment_b2', 'mse_prepare']
        self.assertEqual(result['run'], expected)
        self.assert_preserved(runner, previous, expected)
        self.assertEqual(runner.records['mse_prepare']['inputs']['assessment_a1']['run_id'], 'Run 001')
        self.assertEqual(runner.records['mse_prepare']['inputs']['assessment_a2']['run_id'], 'Run 002')

    def test_default_workflow_still_runs_dependants(self):
        runner = self.clone()
        self.assertEqual(runner.plan('cpue_summary')['run'], ['cpue_summary', 'cpue_report'])
        self.assertEqual(runner.plan('cpue_summary')['scope'], 'workflow')
        self.assertEqual(runner.plan('cpue_summary'), runner.plan('cpue_summary', 'workflow'))

    def test_unknown_scope_is_rejected_before_execution(self):
        runner = self.clone()
        previous = deepcopy(runner.records)
        for value in ('all', '', None, True, {}):
            with self.subTest(scope=value), self.assertRaisesRegex(ValueError, 'job or workflow'):
                asyncio.run(runner.run('cpue_a', value))
            self.assertFalse(runner.running)
            self.assertEqual(runner.records, previous)

    def test_download_reproduces_only_the_requested_job_from_fresh_or_mixed_records(self):
        for fresh in (True, False):
            with self.subTest(fresh=fresh), tempfile.TemporaryDirectory() as directory:
                runner = Workflow(Path(directory) / 'run') if fresh else self.clone()
                runner.configure({'min_hooks_a': 1200})
                asyncio.run(runner.run('cpue_a', 'job'))
                previous = deepcopy(runner.records)
                # Reloading a checkpoint must retain the last request's scope.
                runner = Workflow(runner.directory)
                runner.configure({'min_hooks_a': 0})
                extracted = Path(directory) / 'download'
                with zipfile.ZipFile(io.BytesIO(runner.bundle())) as archive:
                    instructions = archive.read('REPRODUCE.txt').decode()
                    self.assertEqual(json.loads(archive.read('settings.json'))['min_hooks_a'], 1200)
                    self.assertIn('This check compares only cpue_a.', instructions)
                    archive.extractall(extracted)
                for prefix in ('Run: ', 'Check: '):
                    command = next(line[len(prefix):] for line in instructions.splitlines()
                                   if line.startswith(prefix))
                    arguments = shlex.split(command)
                    arguments[0] = sys.executable
                    result = subprocess.run(arguments, cwd=extracted, text=True,
                                            capture_output=True, timeout=30)
                    self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                    if prefix == 'Check: ':
                        self.assertIn('1 job outputs agree', result.stdout)
                reproduced = json.loads((extracted / 'reproduced/state.json').read_text())
                self.assertEqual(set(reproduced['records']),
                                 {'submission', 'qc', 'database', 'extract', 'cpue_a'})
                reference = json.loads((extracted / 'reference/state.json').read_text())
                self.assertEqual(reference['records'], previous)
                self.assertEqual(reference['last_plan']['scope'], 'job')


if __name__ == '__main__':
    unittest.main()
