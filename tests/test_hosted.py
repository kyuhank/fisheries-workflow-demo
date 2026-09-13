"""Check hosted-data identity without using a network or credential."""
import importlib.util
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from workflow.engine import Workflow

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
            Workflow.__init__(runner, directory)
            runner.hosted_data = {'sets': [{'year': 2023, 'hooks': 1000, 'catch_n': 20}], 'catch': []}
            first = runner.signature('submission')
            self.assertEqual(first, runner.signature('submission'))
            runner.hosted_data['sets'][0]['catch_n'] = 21
            self.assertNotEqual(first, runner.signature('submission'))
