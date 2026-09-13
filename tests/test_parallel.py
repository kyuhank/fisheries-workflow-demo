"""Verify hosted process calculations against the preserved Python results."""
import asyncio
import os
from pathlib import Path
import tempfile
import unittest

os.environ.setdefault('PAPER_REQUEST_ID', '00000000-0000-4000-8000-000000000001')
from cloud.run import HostedWorkflow, PARALLEL_JOBS
from workflow.engine import Workflow
from workflow.spec import STAGES
from verify import compare


class HostedProcessesTest(unittest.TestCase):
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
