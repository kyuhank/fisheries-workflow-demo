"""Continuation receipt tests using explicit software-only temporary fixtures.

Files, sizes, SHA-256 checks and JSON consistency are real. Dummy source hashes,
records and PASSED labels below describe fixtures, never model calculations.
No R, Docker, Git repository fixture or numerical conformance run is launched.
"""
import copy
import hashlib
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from workflow.spec import DEFAULTS, SPEC

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('multi_repository_continuation_check',
                                            ROOT / 'scripts/check-multi-repository.py')
check = importlib.util.module_from_spec(spec)
spec.loader.exec_module(check)

PRIOR_COMMIT = '5cca42bedf3ea61027b282799400adf8483980b9'
CURRENT_COMMIT = 'd' * 40
REPOSITORY = 'https://github.com/kyuhank/fisheries-workflow-demo'
IMAGE = 'ghcr.io/pacificcommunity/fisheries-workflow@sha256:9dea950a713b87daad728517138bcb664a151f0f5b44a1d5370623734a5bca9d'
PROOF = {'scripts/check-multi-repository.py', 'scripts/MULTI_REPOSITORY.md',
         'tests/test_multi_repository.py', 'tests/test_multi_repository_continuation.py', 'Dockerfile'}
CORE = {'run.py', 'verify.py', 'Makefile', 'workflow/engine.py', 'workflow/spec.py',
        'workflow/r_bridge.py', 'workflow/r_driver.R', 'workflow/Makefile',
        'workflow/jobs.json', 'workflow/sources.py', 'workflow/contracts.py',
        'workflow/reports.py', 'workflow/quarto_reports.py', 'workflow/r/common.R'}


def checksum(data):
    return hashlib.sha256(data).hexdigest()


def write_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, sort_keys=True, indent=2, allow_nan=False) + '\n')


class CheckpointFixture:
    def __init__(self, root):
        self.root = Path(root).resolve()
        files = {name: checksum(('explicit dummy source bytes: ' + name).encode())
                 for name in CORE | PROOF | {'data/scenario.json', 'README.md'}}
        self.origin = {'schema_version': 1, 'repository': REPOSITORY,
                       'commit': PRIOR_COMMIT, 'files': files}
        self.current = copy.deepcopy(self.origin)
        self.current['commit'] = CURRENT_COMMIT
        self.current['files']['scripts/check-multi-repository.py'] = checksum(b'changed proof runner fixture')
        self.origin_path = self.root / 'baseline-origin.json'
        write_json(self.origin_path, self.origin)
        self.origin_sha = checksum(self.origin_path.read_bytes())
        execution = {'provider': 'Local Docker validation',
                     'repository': 'kyuhank/fisheries-workflow-demo',
                     'commit': PRIOR_COMMIT, 'container': IMAGE}
        self.receipt = {'schema_version': 1, 'status': 'FAILED', 'actual_client': 'codex',
                        'automatic_retry': False, 'test_doubles': False, 'runtime_image': IMAGE,
                        'maximum_attempts': 18, 'execution_identity': execution,
                        'comparison': {'source': 'verify.py', 'sha256': files['verify.py']},
                        'attempts': [], 'cases': {}, 'artifacts': {}}
        self.states = {}
        for case, name, kind, selected in check.ATTEMPTS[:6]:
            self.receipt['attempts'].append({'case': case, 'name': name, 'kind': kind,
                                            'expected_selected': list(selected), 'status': 'PASSED'})
            settings = {**DEFAULTS, 'mse': True}
            if name.startswith('cpue-'):
                settings['min_hooks_a'] = 1200
            if name.startswith('buffer-'):
                settings['mse_buffer'] = 0.6
            records = {}
            for key, job in SPEC.items():
                folder = self.root / name / key
                folder.mkdir(parents=True)
                write_json(folder / 'output.json', {'job': key, 'software_only_fixture': True})
                (folder / 'report.html').write_text('Explicit software fixture: ' + key + '\n')
                outputs = {filename: checksum((folder / filename).read_bytes())
                           for filename in ('output.json', 'report.html')}
                group = 'cpue' if job['module'] in ('data', 'cpue') else job['module']
                entrypoint = 'jobs/' + key + '/run.R'
                component_path = 'components/' + group + '/' + entrypoint
                component = {'repository': 'https://github.com/kyuhank/fisheries-workflow-' + group + '-demo',
                             'commit': 'c' * 40, 'path': entrypoint,
                             'sha256': checksum(('dummy entrypoint: ' + key).encode())}
                record = {'job': key, 'owner': job['owner'], 'run_id': 'SOFTWARE FIXTURE',
                          'signature': checksum(('dummy signature: ' + key).encode()),
                          'settings': {}, 'snapshot': settings['last_year'], 'outputs': outputs,
                          'analysis_source': component, 'source': {'repository': REPOSITORY, 'commit': PRIOR_COMMIT},
                          'execution': execution.copy(), 'software': {'container': IMAGE},
                          'data_files': {'scenario.json': files['data/scenario.json']},
                          'code': {**{path: files[path] for path in CORE}, component_path: component['sha256']},
                          'code_sources': {component_path: component},
                          'inputs': {parent: {'run_id': records[parent]['run_id'],
                                              'checksum': records[parent]['outputs']['output.json'],
                                              'signature': records[parent]['signature']}
                                     for parent in job['parents']}}
                record['code_sources'].update({path: {'repository': REPOSITORY, 'commit': PRIOR_COMMIT,
                                                      'path': path, 'sha256': files[path]} for path in CORE})
                write_json(folder / 'record.json', record)
                records[key] = record
            state = {'settings': settings, 'records': records, 'run_number': 1,
                     'last_plan': {'run': list(selected),
                                   'retained': [key for key in SPEC if key not in selected]},
                     'jobs': list(SPEC.values()), 'events': []}
            self.states[name] = state
            write_json(self.root / name / 'state.json', state)
        self.receipt['attempts'].append({'case': 'MR-04', 'name': 'code-selective',
                                        'kind': check.ATTEMPTS[6][2],
                                        'expected_selected': list(check.ATTEMPTS[6][3]),
                                        'status': 'FAILED', 'error': 'Explicit failed-attempt software fixture'})
        for case, name in (('MR-01', 'split-baseline'), ('MR-02', 'cpue-selective'), ('MR-03', 'buffer-selective')):
            self.receipt['cases'][case] = {'status': 'PASSED', 'records': copy.deepcopy(self.states[name]['records'])}
        self.path = self.root / 'evidence.json'
        self.refresh_artifacts()
        self.write_receipt()

    def write_receipt(self):
        write_json(self.path, self.receipt)
        self.receipt_sha = checksum(self.path.read_bytes())

    def refresh_artifacts(self):
        for _, name, _, _ in check.ATTEMPTS[:6]:
            for path in (self.root / name).rglob('*'):
                if path.is_file():
                    self.receipt['artifacts'][path.relative_to(self.root).as_posix()] = {
                        'bytes': path.stat().st_size, 'sha256': checksum(path.read_bytes())}

    def validate(self, **kwargs):
        return check.validate_checkpoint(self.path, self.receipt_sha, self.origin_path,
                                         self.current, IMAGE, expected_origin_sha256=self.origin_sha, **kwargs)


class MultiRepositoryContinuationTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.fixture = CheckpointFixture(self.temporary.name)

    def assertRejected(self, operation):
        with self.assertRaises((AssertionError, ValueError, OSError, KeyError, TypeError)):
            operation()

    def test_import_copies_verified_outputs_and_keeps_new_attempt_ledger_empty(self):
        # Explicit resolver/runtime/comparison software doubles; file copies and
        # all receipt/artifact checks are real. No calculate/run method exists.
        current = self.fixture.root / 'current-coordinator'
        current.mkdir()
        (current / 'verify.py').write_text('explicit dummy source bytes: verify.py')
        write_json(current / 'coordinator-origin.json', self.fixture.current)
        lock = current / 'source-lock.json'
        lock.write_text('{}\n')
        reference = self.fixture.root / 'reference-manifest.json'
        reference.write_text('{}\n')
        self.fixture.receipt['source_lock'] = {'sha256': checksum(lock.read_bytes())}
        self.fixture.receipt['reference'] = {'commit': check.REFERENCE_COMMIT,
                                              'manifest_sha256': checksum(reference.read_bytes())}
        self.fixture.write_receipt()
        output = self.fixture.root / 'imported-output'
        resolver = SimpleNamespace(verify=lambda: None,
                                   coordinator_identity=lambda: {'repository': REPOSITORY,
                                                                  'commit': CURRENT_COMMIT})
        with patch.object(check, 'ROOT', current), \
                patch.object(check.RBridge, 'require_container', return_value=IMAGE), \
                patch('workflow.sources.SourceResolver', return_value=resolver), \
                patch.object(check, 'sources_and_lineage') as lineage, \
                patch.object(check, 'verify', return_value=22):
            suite = check.EvidenceSuite(output, lock, self.fixture.root, check.REFERENCE_COMMIT,
                                        180, reference_manifest=reference,
                                        continue_from=self.fixture.path,
                                        continue_sha256=self.fixture.receipt_sha,
                                        checkpoint_origin=self.fixture.origin_path,
                                        checkpoint_origin_sha256=self.fixture.origin_sha)
            suite.verify_reference_sources = lambda: None
            suite.compare = lambda left, right: {'software_comparison_double': True}
            def restored(name):
                state = json.loads((output / name / 'state.json').read_text())
                return SimpleNamespace(directory=output / name, records=state['records'],
                                       settings=state['settings'])
            suite.runner = restored
            baseline, cpue = suite.import_checkpoint()
        self.assertEqual(baseline.directory, output / 'split-baseline')
        self.assertEqual(cpue.directory, output / 'cpue-selective')
        self.assertEqual(suite.receipt['attempts'], [])
        self.assertEqual(len(suite.receipt['imported_attempts']), 6)
        self.assertEqual(set(suite.receipt['cases']), {'MR-01', 'MR-02', 'MR-03'})
        self.assertEqual(suite.receipt['continuation']['preserved_failed_attempt'],
                         self.fixture.receipt['attempts'][6])
        self.assertEqual(suite.receipt['continuation']['receipt_sha256'], self.fixture.receipt_sha)
        self.assertEqual(lineage.call_count, 5)
        for call in lineage.call_args_list:
            self.assertEqual(call.kwargs['produced'], ())
            self.assertEqual(call.args[0].records, call.kwargs['retained_records'])
        for name, item in suite.receipt['continuation']['verified_imported_artifacts'].items():
            self.assertEqual(checksum((output / name).read_bytes()), item['sha256'])

    def test_valid_checkpoint_imports_six_attempts_and_three_cases_without_new_execution(self):
        result = self.fixture.validate()
        self.assertEqual(result['root'], self.fixture.root)
        self.assertEqual(list(result['imported_names']), [item[1] for item in check.ATTEMPTS[:6]])
        self.assertEqual(set(result['imported_cases']), {'MR-01', 'MR-02', 'MR-03'})
        self.assertEqual(result['receipt']['status'], 'FAILED')
        self.assertEqual(result['origin'], self.fixture.origin)
        self.assertEqual(result['origin_sha256'], self.fixture.origin_sha)
        self.assertEqual(set(result['states']), {item[1] for item in check.ATTEMPTS[:6]})
        self.assertTrue(result['verified_artifacts'])

    def test_receipt_and_origin_pins_are_exact_byte_checks(self):
        self.assertRejected(lambda: check.validate_checkpoint(self.fixture.path, '0' * 64,
                            self.fixture.origin_path, self.fixture.current, IMAGE,
                            expected_origin_sha256=self.fixture.origin_sha))
        self.assertRejected(lambda: check.validate_checkpoint(self.fixture.path, self.fixture.receipt_sha,
                            self.fixture.origin_path, self.fixture.current, IMAGE,
                            expected_origin_sha256='0' * 64))

    def test_ledger_status_client_image_and_completed_case_scope_cannot_be_relabelled(self):
        original = copy.deepcopy(self.fixture.receipt)
        mutations = [lambda d: d.update(status='PASSED'), lambda d: d.update(actual_client='other'),
                     lambda d: d.update(test_doubles=True), lambda d: d.update(automatic_retry=True),
                     lambda d: d.update(runtime_image=IMAGE.replace('9', '8', 1)),
                     lambda d: d['execution_identity'].update(commit='e' * 40),
                     lambda d: d['execution_identity'].update(provider='GitHub Actions'),
                     lambda d: d['attempts'][0].update(status='FAILED'),
                     lambda d: d['attempts'][1].update(name='different-baseline'),
                     lambda d: d['attempts'][2].update(expected_selected=[]),
                     lambda d: d['attempts'][6].update(status='PASSED'),
                     lambda d: d['cases'].update({'MR-04': {'status': 'PASSED'}}),
                     lambda d: d['cases']['MR-03'].update(status='FAILED'),
                     lambda d: d['attempts'].append(copy.deepcopy(d['attempts'][6]))]
        for number, mutation in enumerate(mutations):
            with self.subTest(mutation=number):
                self.fixture.receipt = copy.deepcopy(original)
                mutation(self.fixture.receipt)
                self.fixture.write_receipt()
                self.assertRejected(self.fixture.validate)

    def test_core_hashes_comparator_and_nonproof_membership_must_remain_identical(self):
        original = copy.deepcopy(self.fixture.current)
        for path in ('workflow/engine.py', 'verify.py', 'data/scenario.json', 'README.md'):
            with self.subTest(path=path):
                self.fixture.current = copy.deepcopy(original)
                self.fixture.current['files'][path] = checksum(b'changed core source')
                self.assertRejected(self.fixture.validate)
        self.fixture.current = copy.deepcopy(original)
        self.fixture.current['files']['workflow/unregistered.py'] = checksum(b'unexpected new file')
        self.assertRejected(self.fixture.validate)
        self.fixture.current = copy.deepcopy(original)
        del self.fixture.current['files']['workflow/engine.py']
        self.assertRejected(self.fixture.validate)
        self.fixture.current = copy.deepcopy(original)
        self.fixture.receipt['comparison']['sha256'] = '0' * 64
        self.fixture.write_receipt()
        self.assertRejected(self.fixture.validate)

    def test_only_five_declared_proof_paths_may_change_or_change_membership(self):
        for path in PROOF:
            self.fixture.current['files'][path] = checksum(('allowed proof edit: ' + path).encode())
        self.fixture.validate()
        del self.fixture.current['files']['tests/test_multi_repository_continuation.py']
        self.fixture.validate()

    def test_actual_artifact_content_size_and_presence_are_verified(self):
        path = self.fixture.root / 'split-baseline/cpue_a/output.json'
        before = path.read_bytes()
        path.write_bytes(before.replace(b'cpue_a', b'cpue_b'))
        self.assertRejected(self.fixture.validate)
        path.write_bytes(before)
        entry = self.fixture.receipt['artifacts'][path.relative_to(self.fixture.root).as_posix()]
        entry['bytes'] += 1
        self.fixture.write_receipt()
        self.assertRejected(self.fixture.validate)
        entry['bytes'] -= 1
        self.fixture.write_receipt()
        path.unlink()
        self.assertRejected(self.fixture.validate)

    def test_unmanifested_file_or_missing_manifest_entry_is_rejected(self):
        path = self.fixture.root / 'cpue-fresh/unlisted.txt'
        path.write_text('actual unmanifested software fixture')
        self.assertRejected(self.fixture.validate)
        path.unlink()
        del self.fixture.receipt['artifacts']['cpue-fresh/state.json']
        self.fixture.write_receipt()
        self.assertRejected(self.fixture.validate)

    def test_rehashed_checkpoint_cannot_hide_changed_settings_records_or_outputs(self):
        state_path = self.fixture.root / 'buffer-selective/state.json'
        original = copy.deepcopy(self.fixture.states['buffer-selective'])
        changed = copy.deepcopy(original)
        changed['settings']['mse_buffer'] = 0.8
        write_json(state_path, changed)
        self.fixture.refresh_artifacts()
        self.fixture.write_receipt()
        self.assertRejected(self.fixture.validate)

        changed = copy.deepcopy(original)
        changed['records']['mse_buffered']['run_id'] = 'different fixture producing record'
        write_json(state_path, changed)
        self.fixture.refresh_artifacts()
        self.fixture.write_receipt()
        self.assertRejected(self.fixture.validate)
        write_json(state_path, original)
        output_path = self.fixture.root / 'buffer-selective/mse_buffered/output.json'
        output_path.write_text('{"software_only_fixture":"independent checksum mismatch"}\n')
        self.fixture.refresh_artifacts()
        self.fixture.write_receipt()
        self.assertRejected(self.fixture.validate)

    def test_rehashed_consistent_record_cannot_relabel_source_execution_code_or_data(self):
        original = copy.deepcopy(self.fixture.states['split-baseline'])
        mutations = [lambda r: r['source'].update(commit='e' * 40),
                     lambda r: r['execution'].update(container='different image'),
                     lambda r: r['code'].update({'workflow/engine.py': '0' * 64}),
                     lambda r: r['data_files'].update({'scenario.json': '0' * 64})]
        for number, mutation in enumerate(mutations):
            with self.subTest(mutation=number):
                state = copy.deepcopy(original)
                mutation(state['records']['cpue_a'])
                write_json(self.fixture.root / 'split-baseline/state.json', state)
                write_json(self.fixture.root / 'split-baseline/cpue_a/record.json', state['records']['cpue_a'])
                self.fixture.refresh_artifacts()
                self.fixture.write_receipt()
                self.assertRejected(self.fixture.validate)
    def test_unsafe_artifact_paths_and_symlink_substitutes_are_rejected(self):
        original = copy.deepcopy(self.fixture.receipt)
        for name in ('../outside.json', '/absolute.json', 'split-baseline/../outside.json'):
            with self.subTest(name=name):
                self.fixture.receipt = copy.deepcopy(original)
                self.fixture.receipt['artifacts'][name] = {'bytes': 0, 'sha256': checksum(b'')}
                self.fixture.write_receipt()
                self.assertRejected(self.fixture.validate)
        self.fixture.receipt = original
        self.fixture.write_receipt()
        path = self.fixture.root / 'split-baseline/cpue_a/output.json'
        substitute = self.fixture.root / 'same-bytes-outside-imported-directory.json'
        substitute.write_bytes(path.read_bytes())
        path.unlink()
        path.symlink_to(substitute)
        self.assertRejected(self.fixture.validate)

    def test_continuation_plan_declares_twelve_new_attempts_and_six_imported_attempts(self):
        full = check.plan(timeout=180, continuation=False)
        continuation = check.plan(timeout=180, continuation=True)
        self.assertEqual(full['maximum_attempts'], 18)
        self.assertEqual(full['maximum_new_attempts'], 18)
        self.assertEqual(full['imported_attempt_count'], 0)
        self.assertEqual(continuation['maximum_attempts'], 12)
        self.assertEqual(continuation['maximum_new_attempts'], 12)
        self.assertEqual(continuation['imported_attempt_count'], 6)
        self.assertEqual(continuation['total_declared_attempt_count'], 18)
        self.assertEqual([item['name'] for item in continuation['attempts']],
                         [item[1] for item in check.ATTEMPTS[6:]])
        self.assertNotIn('reference-baseline', [item['name'] for item in continuation['attempts']])
        self.assertFalse(continuation['automatic_retry'])


if __name__ == '__main__':
    unittest.main()
