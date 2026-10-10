"""Actual R source custody, dispatch boundaries and declared bundle runtime."""
import asyncio
import hashlib
import io
import json
import re
import shlex
import tempfile
import unittest
from unittest.mock import AsyncMock, patch
import zipfile
from pathlib import Path

from workflow.engine import ROOT, Workflow, calculation_files, job_files
from workflow.spec import SPEC
from tests.coordinator_fixtures import CoordinatorBridge


class JobSourceTests(unittest.TestCase):
    def runner(self, directory):
        return Workflow(directory, r_bridge=CoordinatorBridge())

    def test_all_registered_jobs_have_readable_R_entrypoint_and_guide(self):
        folders = {p.name for p in (ROOT / 'jobs').iterdir() if p.is_dir()
                   and p.name != '__pycache__'}
        self.assertEqual(folders, set(SPEC))
        for key in SPEC:
            self.assertTrue((ROOT / 'jobs' / key / 'README.md').is_file())
            source = (ROOT / 'jobs' / key / 'run.R').read_text()
            self.assertIn('calculate <- function(context)', source)
            self.assertNotIn('system(', source)
            self.assertNotIn('reticulate', source)
        for key in ('cpue_report', 'assessment_report', 'mse_report'):
            self.assertTrue((ROOT / 'jobs' / key / 'report.qmd').is_file())

    def test_selected_job_receives_its_declared_JSON_inputs(self):
        with tempfile.TemporaryDirectory() as directory:
            runner = self.runner(directory)
            folder = Path(directory) / 'extract'
            folder.mkdir()
            inputs = {'sets': [{'set_id': 'one'}], 'catch': []}
            (folder / 'output.json').write_text(json.dumps(inputs))
            selected = AsyncMock(return_value={'result': {'selected': 'cpue_a'}, 'effects': {}})
            runner.calculator.calculate = selected
            self.assertEqual(asyncio.run(runner.calculate('cpue_a', 'test')), {'selected': 'cpue_a'})
            context = selected.await_args.args[0]
            self.assertEqual(context['parents'], {'extract': inputs})
            self.assertEqual(context['job_settings'], {'min_hooks': 0})
            self.assertEqual(context['key'], 'cpue_a')
            self.assertEqual(context['run_id'], 'test')
            with self.assertRaisesRegex(ValueError, 'No calculation registered'):
                asyncio.run(runner.calculate('../../other', 'test'))
            selected.assert_awaited_once()

    def test_only_QC_can_request_declared_resubmission_effect(self):
        with tempfile.TemporaryDirectory() as directory:
            runner = self.runner(directory)
            path = Path(directory) / 'extract'
            path.mkdir()
            (path / 'output.json').write_text('{}')
            runner.calculator.calculate = AsyncMock(return_value={
                'result': {}, 'effects': {'resubmit_submission': {}}})
            with self.assertRaisesRegex(ValueError, 'undeclared workflow side effects'):
                asyncio.run(runner.calculate('cpue_a', 'test'))
            self.assertEqual(runner.events, [])

    def test_job_revision_is_local_and_shared_R_revision_reaches_all_sourced_jobs(self):
        with tempfile.TemporaryDirectory() as directory:
            runner = self.runner(directory)
            before = {key: runner.code_record(key) for key in ('cpue_a', 'cpue_b')}
            original = Path.read_bytes
            for name, affected in [('jobs/cpue_a/run.R', {'cpue_a'}),
                                   ('workflow/r/models.R', {'cpue_a', 'cpue_b'}),
                                   ('Makefile', {'cpue_a', 'cpue_b'}),
                                   ('workflow/Makefile', {'cpue_a', 'cpue_b'}),
                                   ('workflow/jobs.json', {'cpue_a', 'cpue_b'})]:
                target = ROOT / name
                def changed(path):
                    return original(path) + b'\n# changed source\n' if path == target else original(path)
                with patch.object(Path, 'read_bytes', changed):
                    for key in before:
                        self.assertEqual(runner.code_record(key) != before[key], key in affected)
            self.assertNotIn('jobs/cpue_a/README.md', before['cpue_a'])
            self.assertFalse(any(name.endswith('.py') and name.startswith('jobs/')
                                 for name in before['cpue_a']))

    def test_bundle_preserves_actual_R_QMD_sources_and_container_recipe(self):
        with tempfile.TemporaryDirectory() as directory:
            runner = self.runner(directory)
            image = 'ghcr.io/example/fisheries@sha256:' + 'a' * 64
            with patch.object(runner, 'software', return_value={'container': image}), \
                 zipfile.ZipFile(io.BytesIO(runner.bundle())) as archive:
                checksums = json.loads(archive.read('SHA256SUMS.json'))
                for path in [*job_files(), *calculation_files()]:
                    name = path.relative_to(ROOT).as_posix()
                    self.assertEqual(archive.read(name), path.read_bytes())
                    self.assertEqual(checksums[name], hashlib.sha256(path.read_bytes()).hexdigest())
                recipe = archive.read('REPRODUCE.txt').decode()
                self.assertIn('make reproduce', recipe)
                commands = {name: shlex.split(command) for name, command in
                            (line.split(': ', 1) for line in recipe.splitlines()
                             if line.startswith(('Pull: ', 'Run: ', 'Check: ')))}
                self.assertEqual(commands['Pull'],
                                 ['docker', 'pull', '--platform', 'linux/amd64', image])
                self.assertEqual(commands['Run'][:2], ['make', 'reproduce'])
                self.assertEqual(commands['Check'][:2], ['make', 'compare'])
                for name in ('Run', 'Check'):
                    self.assertIn('IMAGE=' + image, commands[name])
                for name in ('Makefile', 'workflow/Makefile'):
                    self.assertEqual(archive.read(name), (ROOT / name).read_bytes())
                    self.assertEqual(checksums[name], hashlib.sha256((ROOT / name).read_bytes()).hexdigest())
                self.assertIn('scripts/generate-data.R', archive.namelist())
                self.assertFalse(any(name.startswith('jobs/') and name.endswith('run.py')
                                     for name in archive.namelist()))

    def test_bundle_preserves_linked_repository_example(self):
        name = 'examples/analyst-repositories.yaml'
        guide = (ROOT / 'ADAPT.md').read_text()
        self.assertIn(name, re.findall(r'\]\(([^)]+)\)', guide))
        expected = (ROOT / name).read_bytes()
        with tempfile.TemporaryDirectory() as directory:
            runner = self.runner(directory)
            image = 'ghcr.io/example/fisheries@sha256:' + 'a' * 64
            with patch.object(runner, 'software', return_value={'container': image}), \
                 zipfile.ZipFile(io.BytesIO(runner.bundle())) as archive:
                self.assertEqual(archive.namelist().count(name), 1)
                self.assertEqual(archive.read(name), expected)
                checksums = json.loads(archive.read('SHA256SUMS.json'))
                self.assertEqual(checksums[name], hashlib.sha256(expected).hexdigest())
                for document in ('ADAPT.md', 'jobs/README.md'):
                    data = (ROOT / document).read_bytes()
                    self.assertEqual(archive.namelist().count(document), 1)
                    self.assertEqual(archive.read(document), data)
                    self.assertEqual(checksums[document], hashlib.sha256(data).hexdigest())
                self.assertIn(b'status: registered_sources', archive.read(name))


if __name__ == '__main__':
    unittest.main()
