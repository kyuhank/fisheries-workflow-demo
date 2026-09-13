"""Verify hosted process calculations against the preserved Python results."""
import asyncio
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

os.environ.setdefault('PAPER_REQUEST_ID', '00000000-0000-4000-8000-000000000001')
from cloud.run import HostedWorkflow, PARALLEL_JOBS, EventDelivery
from workflow.engine import Workflow
from workflow.spec import SPEC, STAGES
from verify import compare


class HostedProcessesTest(unittest.TestCase):
    def test_live_events_preserve_peer_barriers_and_manual_reporting_on_partial_rerun(self):
        with tempfile.TemporaryDirectory() as directory:
            runner = object.__new__(HostedWorkflow)
            Workflow.__init__(runner, directory, notify=runner.publish,
                              manual_transfer=runner.handover)
            runner.hosted_data = Workflow(directory).source_rows()
            runner.pool, runner.transfer_count, runner.delivery = None, 0, EventDelivery()
            delivered, confirmed = [], set()

            def api(path, body=None):
                if path == 'event':
                    delivered.append(json.loads(json.dumps(body)))
                    return {'ok': True}
                self.assertEqual(path, 'control')
                handover = next(item['event'] for item in reversed(delivered)
                                if item['event']['state'] == 'handover')
                boundary = handover['boundary']
                if boundary == 'data' or any(item['event'].get('job') == 'cpue_report'
                                             and item['event']['state'] == 'complete'
                                             for item in delivered):
                    confirmed.add(boundary)
                return {'transfer_count': len(confirmed), 'connected': False}

            with patch('cloud.run.api', side_effect=api), patch('builtins.print'):
                full = asyncio.run(runner.run())
                retained = {key: runner.records[key].copy() for key in
                            ['cpue_b', 'prepare_b', 'assessment_b1', 'assessment_b2']}
                self.assertEqual([item['event']['group'] for item in delivered
                                  if item['event']['state'] == 'handover'],
                                 [['cpue_a', 'cpue_b'], ['prepare_a', 'prepare_b']])
                self.assert_event_barriers(full['events'])
                self.assert_reporting_before_transfer(full['events'])
                for _ in range(2):
                    delivered.clear(); confirmed.clear()
                    runner.transfer_count = 0
                    runner.configure({'min_hooks_a': 1200})
                    partial = asyncio.run(runner.run('cpue_a'))
                    self.assertEqual([item['event']['group'] for item in delivered
                                      if item['event']['state'] == 'handover'], [['prepare_a']])
                    self.assertEqual({key: runner.records[key] for key in retained}, retained)
                    self.assertEqual(len(partial['run']), 8)
                    self.assert_event_barriers(partial['events'])
                    self.assert_reporting_before_transfer(partial['events'])
                    self.assertTrue(all(runner.valid(key) for key in SPEC))

    def assert_reporting_before_transfer(self, events):
        report = next(i for i, event in enumerate(events)
                      if event['job'] == 'cpue_report' and event['state'] == 'complete')
        confirmed = next(i for i, event in enumerate(events)
                         if event['state'] == 'received' and event['boundary'] == 'cpue')
        self.assertLess(report, confirmed)

    def assert_event_barriers(self, events):
        positions = {(event['job'], event['state']): i for i, event in enumerate(events)}
        for group in STAGES:
            completed = [positions[(key, 'complete')] for key in group
                         if (key, 'complete') in positions]
            for key, job in SPEC.items():
                if completed and set(job['parents']).intersection(group) and (key, 'running') in positions:
                    self.assertLess(max(completed), positions[(key, 'running')])

    def test_process_outputs_match_python(self):
        with tempfile.TemporaryDirectory() as directory:
            baseline = Workflow(Path(directory) / 'baseline')
            asyncio.run(baseline.run())
            hosted = object.__new__(HostedWorkflow)
            Workflow.__init__(hosted, baseline.directory)
            hosted.pool = None

            async def exercise():
                for stage in STAGES:
                    keys = [key for key in stage if key in PARALLEL_JOBS]
                    results = await asyncio.gather(
                        *(hosted.calculate(key, 'Process check') for key in keys))
                    for key, result in zip(keys, results):
                        compare(baseline.output(key), result, key)

            try:
                asyncio.run(exercise())
            finally:
                if hosted.pool:
                    hosted.pool.shutdown(wait=True, cancel_futures=True)


if __name__ == '__main__':
    unittest.main()
