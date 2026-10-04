"""Job boundaries must survive dispatch, code changes and portable downloads."""
import asyncio
import hashlib
import importlib
import io
from pathlib import Path
import tempfile
import unittest
from unittest.mock import AsyncMock, patch
import zipfile

from workflow.engine import ROOT, Workflow, job_files
from workflow.spec import SPEC


class JobSourceTests(unittest.TestCase):
    def test_each_registered_job_has_an_importable_entrypoint_and_guide(self):
        folders = {p.name for p in (ROOT / 'jobs').iterdir() if p.is_dir()
                   and p.name != '__pycache__'}
        self.assertEqual(folders, set(SPEC))
        for key in SPEC:
            self.assertTrue((ROOT / 'jobs' / key / 'README.md').is_file())
            self.assertTrue(asyncio.iscoroutinefunction(
                importlib.import_module(f'jobs.{key}.run').calculate))

    def test_coordinator_calls_selected_job_and_rejects_unregistered_names(self):
        with tempfile.TemporaryDirectory() as directory:
            runner = Workflow(directory)
            calculation = AsyncMock(return_value={'selected': 'cpue_a'})
            with patch('jobs.cpue_a.run.calculate', calculation):
                self.assertEqual(asyncio.run(runner.calculate('cpue_a', 'test')),
                                 {'selected': 'cpue_a'})
                calculation.assert_awaited_once_with(runner, 'test')
            with self.assertRaisesRegex(ValueError, 'No calculation registered'):
                asyncio.run(runner.calculate('../../other', 'test'))

    def test_job_source_revision_changes_only_its_own_code_record(self):
        with tempfile.TemporaryDirectory() as directory:
            runner = Workflow(directory)
            before_a, before_b = runner.code_record('cpue_a'), runner.code_record('cpue_b')
            original = Path.read_bytes
            target = ROOT / 'jobs/cpue_a/run.py'
            def changed(path):
                return original(path) + b'\n# a different job revision\n' if path == target else original(path)
            with patch.object(Path, 'read_bytes', changed):
                self.assertNotEqual(runner.code_record('cpue_a'), before_a)
                self.assertEqual(runner.code_record('cpue_b'), before_b)
            self.assertNotIn('jobs/cpue_a/README.md', before_a)

    def test_download_contains_all_job_sources_and_guides_with_checksums(self):
        with tempfile.TemporaryDirectory() as directory:
            runner = Workflow(directory)
            with zipfile.ZipFile(io.BytesIO(runner.bundle())) as archive:
                import json
                checksums = json.loads(archive.read('SHA256SUMS.json'))
                for path in job_files():
                    name = path.relative_to(ROOT).as_posix()
                    self.assertEqual(archive.read(name), path.read_bytes())
                    self.assertEqual(checksums[name], hashlib.sha256(path.read_bytes()).hexdigest())
                self.assertIn('ADAPT.md', archive.namelist())
                self.assertIn('cloud/README.md', archive.namelist())


if __name__ == '__main__':
    unittest.main()
