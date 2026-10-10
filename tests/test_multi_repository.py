"""Source/provenance/scheduler tests with explicit frozen-output software doubles.

Git and hash/contract checks are real. R and Quarto are never launched here.
Reading preserved numerical JSON is only a fixture for scheduler/record tests;
these tests cannot establish MR-01--08 numerical or scientific conformance.
"""
import asyncio
import copy
import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
from unittest.mock import patch
from types import SimpleNamespace

from workflow.engine import ROOT, Workflow
from workflow.sources import GROUPS, SourceResolver, contained
from workflow.spec import SPEC

module_spec = importlib.util.spec_from_file_location('multi_repository_check', ROOT / 'scripts/check-multi-repository.py')
check = importlib.util.module_from_spec(module_spec)
module_spec.loader.exec_module(check)


def git(repository, *arguments):
    process = subprocess.run(['git', '-c', 'safe.directory=' + str(repository.resolve()),
                              '-C', str(repository), *arguments],
                             text=True, capture_output=True, timeout=15)
    if process.returncode:
        raise AssertionError(process.stderr)
    return process.stdout.strip()


def commit(repository):
    git(repository, 'add', '.')
    git(repository, '-c', 'user.name=Software fixture', '-c', 'user.email=fixture@invalid.example',
        '-c', 'commit.gpgsign=false', 'commit', '-m', 'Software-only source fixture')
    return git(repository, 'rev-parse', 'HEAD')


class SourceFixture:
    def __init__(self, folder):
        self.base = Path(folder).resolve()
        self.root = self.base / 'coordinator'
        self.root.mkdir()
        (self.root / 'workflow/r').mkdir(parents=True)
        for name in ('common.R', 'models.R', 'mse.R'):
            shutil.copyfile(ROOT / 'workflow/r' / name, self.root / 'workflow/r' / name)
        self.lock = {'schema_version': 1, 'repositories': {}, 'libraries': {}}
        for group, keys in GROUPS.items():
            checkout = self.base / group
            checkout.mkdir()
            git(checkout, 'init', '--quiet')
            for key in keys:
                target = checkout / 'jobs' / key
                target.mkdir(parents=True)
                for source in (ROOT / 'jobs' / key).iterdir():
                    if source.is_file():
                        shutil.copyfile(source, target / source.name)
            (checkout / 'R').mkdir()
            # Never evaluate this explicitly named software fixture library.
            (checkout / 'R' / (group + '.R')).write_text('# software source-resolution fixture only\n')
            self.lock['repositories'][group] = {
                'repository': 'https://github.com/kyuhank/fisheries-workflow-' + group + '-demo',
                'commit': commit(checkout), 'checkout': group, 'jobs': list(keys)}
            self.lock['libraries'][group] = {'repository': group, 'path': 'R/' + group + '.R'}
        self.path = self.base / 'source-lock.json'
        self.write()

    def write(self):
        self.path.write_text(json.dumps(self.lock, indent=2) + '\n')

    def revise(self, relative, text):
        path = self.base / 'mse' / relative
        path.write_text(text)
        self.lock['repositories']['mse']['commit'] = commit(self.base / 'mse')
        self.write()


class FrozenOutputBridge:
    """Scheduler-only double returning saved outputs, with no model evaluation."""
    def software(self):
        return {'r': 'SOFTWARE TEST DOUBLE', 'RTMB': 'SOFTWARE TEST DOUBLE',
                'container': 'Frozen-output scheduler fixture; no runtime execution'}

    async def calculate(self, context):
        path = ROOT / 'docs/example' / context['key'] / 'output.json'
        return {'result': json.loads(path.read_text()), 'effects': {}}


def test_report(root, key, result, record, folder, page, *args, **kwargs):
    (folder / 'report.html').write_text('SOFTWARE TEST DOUBLE: ' + key + ' ' + record['run_id'])
    return {'engine': 'SOFTWARE TEST DOUBLE', 'quarto_executed': False}


class MultiRepositoryTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.fixture = SourceFixture(self.temporary.name)
        environment = patch.dict(os.environ)
        environment.start()
        self.addCleanup(environment.stop)
        os.environ.pop('PAPER_SOURCE_LOCK', None)
        os.environ['PAPER_SOURCE_MODE'] = 'monorepo'

    def resolver(self):
        return SourceResolver(root=self.fixture.root, lock_path=self.fixture.path)

    def test_loaded_paths_and_origins_follow_actual_8_8_6_ownership(self):
        resolver = self.resolver()
        self.assertEqual([len(keys) for keys in GROUPS.values()], [8, 8, 6])
        for group, keys in GROUPS.items():
            for key in keys:
                self.assertEqual(resolver.job_path(key), self.fixture.base / group / 'jobs' / key / 'run.R')
                origin = resolver.origin(key)
                self.assertEqual(origin['repository'], self.fixture.lock['repositories'][group]['repository'])
                self.assertEqual(origin['commit'], self.fixture.lock['repositories'][group]['commit'])
                self.assertEqual(origin['sha256'], check.sha256(resolver.job_path(key)))
        self.assertEqual([path.name for path in resolver.library_paths('mse_prepare')],
                         ['common.R', 'assessment.R', 'mse.R'])
        self.assertEqual([path.name for path in resolver.library_paths('assessment_a1')],
                         ['common.R', 'assessment.R'])
        self.assertEqual([path.name for path in resolver.library_paths('cpue_report')], ['common.R'])

    def test_wrong_revision_dirty_checkout_and_changed_lock_are_rejected(self):
        resolver = self.resolver()
        job = self.fixture.base / 'mse/jobs/mse_buffered/run.R'
        original = job.read_text()
        job.write_text(original + '\n# uncommitted fixture\n')
        with self.assertRaisesRegex(ValueError, 'clean'):
            resolver.verify()
        job.write_text(original)
        self.fixture.lock['repositories']['mse']['commit'] = '0' * 40
        self.fixture.write()
        with self.assertRaisesRegex(ValueError, 'lock changed'):
            resolver.verify()
        with self.assertRaisesRegex(ValueError, 'pinned source revision'):
            self.resolver()

    def test_snapshot_is_portable_without_git_but_rejects_changed_source_bytes(self):
        resolver = self.resolver()
        mismatch = check.mismatched_pin_fixture(resolver, self.fixture.base / 'mismatched-pin')
        self.assertEqual(mismatch['status'], 'EXPECTED_REJECTION')
        self.assertFalse(mismatch['calculation_attempted'])
        payload = resolver.archive_payload()
        destination = self.fixture.base / 'portable'
        destination.mkdir()
        for name, data in payload.items():
            path = destination / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(data)
        with patch('workflow.sources.git', side_effect=AssertionError('Offline snapshot must not query Git')):
            portable = SourceResolver(root=self.fixture.root, lock_path=destination / 'source-lock.json')
            self.assertTrue(portable.snapshot)
            self.assertEqual(portable.origin('cpue_a'), resolver.origin('cpue_a'))
            path = portable.job_path('cpue_a')
            path.write_text(path.read_text() + '\n# tampered\n')
            with self.assertRaisesRegex(ValueError, 'byte mismatch'):
                portable.verify()

    def test_traversal_symlink_wrong_authority_and_wrong_partition_are_rejected(self):
        for path in ('../escape', '/absolute', 'mse/../cpue', 'mse\\jobs', ''):
            with self.subTest(path=path), self.assertRaises(ValueError):
                contained(self.fixture.base, path)
        link = self.fixture.base / 'link'
        link.symlink_to(self.fixture.base / 'mse', target_is_directory=True)
        with self.assertRaisesRegex(ValueError, 'Symlink'):
            contained(self.fixture.base, 'link/jobs')
        original = copy.deepcopy(self.fixture.lock)
        for field, value, pattern in (
                ('repository', 'https://example.invalid/mse', 'Unregistered repository'),
                ('jobs', ['mse_buffered'], 'ownership')):
            self.fixture.lock = copy.deepcopy(original)
            self.fixture.lock['repositories']['mse'][field] = value
            self.fixture.write()
            with self.subTest(field=field), self.assertRaisesRegex(ValueError, pattern):
                self.resolver()

    def test_environment_lock_selects_split_and_monorepo_fallback_remains_explicit(self):
        with patch.dict(os.environ, {'PAPER_SOURCE_LOCK': str(self.fixture.path), 'PAPER_SOURCE_MODE': 'split'}):
            self.assertEqual(SourceResolver(root=self.fixture.root).lock_path, self.fixture.path.resolve())
        mono = SourceResolver(root=self.fixture.root)
        self.assertFalse(mono.multi_repository)
        self.assertEqual([path.name for path in mono.library_paths('cpue_a')],
                         ['common.R', 'models.R', 'mse.R'])

    def test_derived_code_edit_is_exact_and_has_a_real_distinct_git_revision(self):
        destination = self.fixture.base / 'variant'
        path, edit = check.variant_lock(self.fixture.path, destination, 'code')
        variant, verified = check.supplied_variant(self.fixture.path, path, 'code')
        self.assertEqual(path, variant)
        self.assertNotEqual(edit['commit'], self.fixture.lock['repositories']['mse']['commit'])
        self.assertEqual(edit['after_sha256'], verified['after_sha256'])
        self.assertIn(check.CODE_NEW, SourceResolver(root=self.fixture.root, lock_path=path).job_path('mse_buffered').read_text())

    def test_component_commit_change_invalidates_only_actual_changed_bytes_and_descendants(self):
        run_directory = self.fixture.base / 'run'
        patches = [patch('workflow.engine.reports.output_page', return_value='SOFTWARE TEST DOUBLE'),
                   patch('workflow.engine.render_report', side_effect=test_report)]
        with patches[0], patches[1]:
            runner = Workflow(run_directory, source_lock=self.fixture.path, r_bridge=FrozenOutputBridge())
            runner.configure({'mse': True})
            full = asyncio.run(runner.run())
            self.assertEqual(full['run'], list(SPEC))
            before = copy.deepcopy(runner.records)
            source = self.fixture.base / 'mse/jobs/mse_buffered/run.R'
            self.fixture.revise('jobs/mse_buffered/run.R', source.read_text() + '\n# scheduler byte-change fixture\n')
            updated = Workflow(run_directory, source_lock=self.fixture.path, r_bridge=FrozenOutputBridge())
            result = asyncio.run(updated.run('mse_report'))
            self.assertEqual(result['run'], list(check.BUFFER))
            self.assertEqual(len(result['retained']), 19)
            check.expected_update(updated, result, before, check.BUFFER)
            self.assertEqual(updated.records['mse_constant'], before['mse_constant'])
            self.assertNotEqual(updated.records['mse_buffered']['analysis_source']['commit'],
                                before['mse_buffered']['analysis_source']['commit'])
            self.assertEqual(updated.records['mse_report']['inputs']['mse_summary']['run_id'], 'Run 002')
            # A historical record remains valid under unchanged dependency bytes.
            self.assertTrue(updated.valid('mse_constant'))

    def test_finite_inventory_names_real_failures_and_disallows_duplicate_attempts(self):
        frozen = check.plan()
        self.assertEqual(frozen['maximum_attempts'], 18)
        self.assertEqual(len({item['name'] for item in frozen['attempts']}), 18)
        self.assertEqual(frozen['case_ids'], [f'MR-{i:02d}' for i in range(1, 9)])
        self.assertFalse(frozen['test_doubles'])
        suite = check.EvidenceSuite.__new__(check.EvidenceSuite)
        suite.timeout = 1
        suite.receipt = {'attempts': []}
        suite.persist = lambda: None
        async def harmless():
            return 'software-only fixture'
        self.assertEqual(asyncio.run(suite.attempt('valid-cpue', harmless)), 'software-only fixture')
        with self.assertRaisesRegex(AssertionError, 'once'):
            asyncio.run(suite.attempt('valid-cpue', harmless))
        with self.assertRaisesRegex(AssertionError, 'Undeclared'):
            asyncio.run(suite.attempt('undeclared', harmless))

    def test_malformed_actual_file_is_rejected_before_adapter_and_restored(self):
        runner = Workflow(self.fixture.base / 'contract-test', source_lock=self.fixture.path,
                          r_bridge=FrozenOutputBridge())
        # Minimal explicit software checkpoint fixtures, never claimed as newly
        # produced scientific outputs. Semantic validation reads their real files.
        for key in ('extract', 'cpue_a'):
            folder = runner.directory / key
            folder.mkdir()
            source = ROOT / 'docs/example' / key / 'output.json'
            shutil.copyfile(source, folder / 'output.json')
            runner.records[key] = {'job': key, 'run_id': 'SOFTWARE CHECKPOINT FIXTURE',
                                   'outputs': {'output.json': check.sha256(folder / 'output.json')},
                                   'analysis_source': runner.sources.origin(key),
                                   'code_sources': runner.sources.code_sources(key)}
            runner.records[key]['signature'] = runner.signature(key)
        saved = copy.deepcopy(runner.records)
        original = (runner.directory / 'cpue_a/output.json').read_bytes()
        suite = check.EvidenceSuite.__new__(check.EvidenceSuite)
        suite.output = self.fixture.base
        suite.timeout = 5
        suite.receipt = {'attempts': []}
        suite.persist = lambda: None
        result = asyncio.run(suite.contract_fixture('invalid-cpue', runner, 'prepare_a', 'cpue_a',
                                                    lambda value: {**value, 'series': []}))
        self.assertEqual(result['status'], 'EXPECTED_REJECTION')
        self.assertFalse(result['adapter_invoked'])
        self.assertEqual(runner.records, saved)
        self.assertEqual((runner.directory / 'cpue_a/output.json').read_bytes(), original)
        fixture = json.loads((runner.directory / 'invalid-cpue.json').read_text())
        self.assertIn('no producing R calculation', fixture['fault_injection'])
        self.assertNotEqual(fixture['original_producer_record']['outputs']['output.json'],
                            fixture['altered_fixture_record']['outputs']['output.json'])

    def test_local_execution_requires_verified_commit_and_only_explicit_host_refs(self):
        origin = {'repository': 'https://github.com/kyuhank/fisheries-workflow-demo', 'commit': 'a' * 40}
        # Identity assembly only: explicit source/container test doubles, no runtime.
        runner = SimpleNamespace(sources=SimpleNamespace(coordinator_identity=lambda: origin.copy()))
        image = 'ghcr.io/example/test@sha256:' + 'b' * 64
        with patch.dict(os.environ), patch.object(check.RBridge, 'require_container', return_value=image):
            os.environ.pop('PAPER_EXECUTION_HOST', None)
            os.environ.pop('PAPER_COMPUTE_SELECTION_RECEIPT', None)
            execution = check.set_local_execution(runner)
            self.assertNotIn('execution_host', execution)
            self.assertNotIn('compute_selection_receipt', execution)
            self.assertEqual(execution['commit'], origin['commit'])
            self.assertEqual(execution['container'], image)
            os.environ['PAPER_EXECUTION_HOST'] = 'explicit-software-test-host'
            os.environ['PAPER_COMPUTE_SELECTION_RECEIPT'] = 'explicit-software-test-receipt'
            execution = check.set_local_execution(runner)
            self.assertEqual(execution['execution_host'], os.environ['PAPER_EXECUTION_HOST'])
            self.assertEqual(execution['compute_selection_receipt'], os.environ['PAPER_COMPUTE_SELECTION_RECEIPT'])
            self.assertIn('explicit parent-provided', execution['execution_host_source'])
            origin['commit'] = None
            with self.assertRaisesRegex(AssertionError, 'verified full coordinator commit'):
                check.set_local_execution(runner)


if __name__ == '__main__':
    unittest.main()
