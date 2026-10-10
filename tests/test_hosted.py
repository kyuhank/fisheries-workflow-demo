"""Check hosted-data identity without using a network or credential."""
import importlib.util
import asyncio
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import AsyncMock, patch

from workflow.engine import Workflow
from tests.coordinator_fixtures import CoordinatorBridge, test_report

ROOT = Path(__file__).resolve().parents[1]


@unittest.skipUnless((ROOT / 'cloud/run.py').exists(), 'The offline-only bundle has no hosted adapter')
class HostedDataTest(unittest.TestCase):
    def test_hosted_data_changes_invalidate_the_submission(self):
        with patch.dict(os.environ, {'PAPER_REQUEST_ID': '00000000-0000-4000-8000-000000000001'}):
            spec = importlib.util.spec_from_file_location('hosted_example', ROOT / 'cloud/run.py')
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
        with tempfile.TemporaryDirectory() as directory:
            runner = module.HostedWorkflow.__new__(module.HostedWorkflow)
            Workflow.__init__(runner, directory, r_bridge=CoordinatorBridge())
            runner.hosted_data = {'sets': [{'year': 2023, 'hooks': 1000, 'catch_n': 20}], 'catch': []}
            first = runner.signature('submission')
            self.assertEqual(first, runner.signature('submission'))
            runner.hosted_data['sets'][0]['catch_n'] = 21
            self.assertNotEqual(first, runner.signature('submission'))


@unittest.skipUnless((ROOT / 'cloud/run.py').exists() and (ROOT / 'source-lock.json').exists(),
                     'Hosted multi-repository fixtures require hydrated source snapshots')
class HostedSourceContextTest(unittest.TestCase):
    """Production persistence/transfer checks with explicit non-numerical doubles."""

    def setUp(self):
        with patch.dict(os.environ, {'PAPER_REQUEST_ID': '00000000-0000-4000-8000-000000000001'}):
            spec = importlib.util.spec_from_file_location('hosted_worker_test', ROOT / 'cloud/run.py')
            self.module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(self.module)
        self.lock = ROOT / 'source-lock.json'
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.runner = self.module.HostedWorkflow.__new__(self.module.HostedWorkflow)
        Workflow.__init__(self.runner, self.temp.name, r_bridge=CoordinatorBridge(), source_lock=self.lock)
        self.runner.hosted_data = {'sets': [], 'catch': []}
        self.runner.execution = {'provider': 'TEST DOUBLE', 'scope': 'hosted worker context only'}
        with patch('workflow.engine.reports.output_page', return_value='TEST DOUBLE'), \
             patch('workflow.engine.render_report', side_effect=test_report):
            for key in ('submission', 'qc', 'database', 'extract'):
                if key == 'database':
                    folder = Path(self.temp.name) / key
                    folder.mkdir()
                    (folder / 'snapshot.sqlite').write_bytes(b'Explicit non-numerical fixture')
                self.runner.save(key, {'job': key, 'sets': [], 'catch': []}, 'Software fixture')

    def worker(self):
        worker = self.module.HostedCalculationWorkflow(self.temp.name, r_bridge=CoordinatorBridge(),
                                                       source_lock=self.lock)
        worker.hosted_data = json.loads(json.dumps(self.runner.hosted_data))
        return worker

    def calculate(self, bridge):
        with patch('workflow.engine.RBridge', return_value=bridge), \
             patch('workflow.engine.reports.output_page', return_value='TEST DOUBLE'), \
             patch('workflow.engine.render_report', side_effect=test_report), \
             patch.object(self.module, 'api', side_effect=AssertionError('Worker must not contact the service')):
            return self.module.calculate_independent_job(
                self.temp.name, 'cpue_a', self.runner.settings, 'Software worker fixture',
                str(self.lock), self.runner.hosted_data, self.runner.execution)

    def test_state_roundtrip_preserves_hosted_parent_fingerprints_and_execution(self):
        before = (Path(self.temp.name) / 'extract/output.json').read_bytes()
        plain = Workflow(self.temp.name, r_bridge=CoordinatorBridge(), source_lock=self.lock)
        self.assertTrue(self.runner.valid('extract'))
        self.assertFalse(plain.valid('extract'))
        self.assertEqual(set(self.runner.code_record('extract')) - set(plain.code_record('extract')),
                         {'cloud/run.py'})
        with self.assertRaisesRegex(ValueError, 'Transfer input stale or checksum mismatch: extract'):
            plain.transferred_output('extract')
        restored = self.worker()
        self.assertEqual(restored.records, self.runner.records)
        for key in ('submission', 'qc', 'database', 'extract'):
            self.assertEqual(restored.signature(key), self.runner.signature(key))
            self.assertTrue(restored.valid(key))
        result = self.calculate(CoordinatorBridge())
        self.assertEqual(result['job'], 'cpue_a')
        # Production workers return results; Workflow.run saves them in the parent.
        with patch('workflow.engine.reports.output_page', return_value='TEST DOUBLE'), \
             patch('workflow.engine.render_report', side_effect=test_report):
            self.runner.save('cpue_a', result, 'Software worker fixture')
        record = json.loads((Path(self.temp.name) / 'cpue_a/record.json').read_text())
        self.assertEqual(record['execution'], self.runner.execution)
        self.assertIn('cloud/run.py', record['code'])
        self.assertEqual(before, (Path(self.temp.name) / 'extract/output.json').read_bytes())
        self.assertTrue(self.worker().valid('cpue_a'))

    def test_worker_rejects_tampered_producer_bytes_before_calculation(self):
        (Path(self.temp.name) / 'extract/output.json').write_bytes(b'{"tampered":true}')
        bridge = CoordinatorBridge()
        with patch.object(bridge, 'calculate', wraps=bridge.calculate) as calculate:
            with self.assertRaisesRegex(ValueError, 'Transfer input stale or checksum mismatch: extract'):
                self.calculate(bridge)
            calculate.assert_not_called()

    def test_worker_rejects_stale_producer_signature_before_calculation(self):
        self.runner.records['extract']['signature'] = '0' * 64
        self.runner.persist()
        bridge = CoordinatorBridge()
        with patch.object(bridge, 'calculate', wraps=bridge.calculate) as calculate:
            with self.assertRaisesRegex(ValueError, 'Transfer input stale or checksum mismatch: extract'):
                self.calculate(bridge)
            calculate.assert_not_called()

    def test_process_dispatch_supplies_frozen_lock_hosted_data_and_execution(self):
        self.runner.pool = object()

        async def dispatch():
            loop = asyncio.get_running_loop()
            with patch.object(loop, 'run_in_executor', new=AsyncMock(return_value='fixture result')) as executor:
                result = await self.runner.calculate('cpue_a', 'Software dispatch fixture')
                self.assertEqual(result, 'fixture result')
                executor.assert_awaited_once_with(
                    self.runner.pool, self.module.calculate_independent_job, self.temp.name,
                    'cpue_a', self.runner.settings, 'Software dispatch fixture', str(self.lock),
                    self.runner.hosted_data, self.runner.execution)

        asyncio.run(dispatch())
