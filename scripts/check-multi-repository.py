"""Finite MR-01--08 conformance evidence; execute only in the pinned container.

The --plan operation performs no calculations. The numerical operation uses the
real Workflow/R/Quarto paths, including deliberate invalid inputs and one actual
R failure. Its fixtures are kept in the evidence directory; source checkouts are
never edited. Software tests of these helpers are separate from execution proof.
"""
import argparse
import asyncio
import copy
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import time
import traceback

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from workflow.engine import Workflow
from workflow.r_bridge import RBridge
from workflow.spec import SPEC, DEFAULTS
from verify import compare, verify

BUFFER = ('mse_buffered', 'mse_summary', 'mse_report')
CPUE = ('cpue_a', 'cpue_summary', 'cpue_report', 'prepare_a',
        'assessment_a1', 'assessment_a2', 'assessment_summary',
        'assessment_report', 'mse_prepare', 'mse_constant', 'mse_index',
        'mse_buffered', 'mse_summary', 'mse_report')
ALL = tuple(SPEC)
REFERENCE_COMMIT = 'b6dc067d5346d3809edf0ad66a0f6c7e7d07ce93'
CODE_OLD = 'buffer = context$settings$mse_buffer'
CODE_NEW = 'buffer = min(context$settings$mse_buffer, 0.6)'
FAILURE_TEXT = 'MR08 intentional Buffered simulation failure'
ATTEMPTS = (
    ('MR-01', 'reference-baseline', 'reference subprocess', ALL),
    ('MR-01', 'split-baseline', 'workflow', ALL),
    ('MR-02', 'cpue-selective', 'workflow', CPUE),
    ('MR-02', 'cpue-fresh', 'workflow', ALL),
    ('MR-03', 'buffer-selective', 'workflow', BUFFER),
    ('MR-03', 'buffer-fresh', 'workflow', ALL),
    ('MR-04', 'code-selective', 'workflow', BUFFER),
    ('MR-04', 'code-fresh', 'workflow', ALL),
    ('MR-05', 'invalid-cpue', 'direct calculation; expected contract rejection', ('prepare_a',)),
    ('MR-05', 'valid-cpue', 'direct calculation', ('prepare_a',)),
    ('MR-05', 'invalid-assessment', 'direct calculation; expected contract rejection', ('mse_prepare',)),
    ('MR-05', 'valid-assessment', 'direct calculation', ('mse_prepare',)),
    ('MR-06', 'missing-transfer', 'workflow', CPUE),
    ('MR-06', 'tampered-transfer', 'workflow', CPUE),
    ('MR-07', 'stale-transfer', 'direct calculation; expected transfer rejection', ('prepare_a',)),
    ('MR-07', 'stale-corrected', 'workflow', CPUE),
    ('MR-08', 'failed-rule', 'workflow; expected actual R failure', BUFFER),
    ('MR-08', 'recovered-rule', 'workflow', BUFFER),
)


def sha256(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def require(condition, message):
    if not condition:
        raise AssertionError(message)


def plan(timeout=180, continuation=False):
    return {'schema_version': 1, 'status': 'PLANNED_NOT_EXECUTED',
            'case_ids': [f'MR-{number:02d}' for number in range(1, 9)],
            'maximum_attempts': len(ATTEMPTS[6:] if continuation else ATTEMPTS),
            'maximum_new_attempts': len(ATTEMPTS[6:] if continuation else ATTEMPTS),
            'imported_attempt_count': 6 if continuation else 0,
            'total_declared_attempt_count': len(ATTEMPTS),
            'timeout_seconds_per_attempt': timeout,
            'timeout_mechanism': 'cooperative asyncio cancellation; R/Quarto subprocess limits retained; parent enforces outer container wall bound',
            'attempts': [{'case': case, 'name': name, 'kind': kind,
                          'expected_selected': list(selected)}
                         for case, name, kind, selected in (ATTEMPTS[6:] if continuation else ATTEMPTS)],
            'code_edit': {'path': 'jobs/mse_buffered/run.R', 'before': CODE_OLD,
                          'after': CODE_NEW, 'fixed_mse_buffer': 0.8,
                          'expected_selected': list(BUFFER)},
            'failure_edit': {'path': 'jobs/mse_buffered/run.R',
                             'error': FAILURE_TEXT},
            'comparison': {'source': 'verify.py', 'sha256': sha256(ROOT / 'verify.py'),
                           'relative': 1e-6, 'absolute': 1e-9,
                           'successful_matching_fit_log_residual_absolute': 1e-8,
                           'near_zero_gradient_magnitude_and_difference': 1e-7,
                           'residual_formula_absolute': 1e-12,
                           'copied_values': 'exact equality with each own source',
                           'fit_diagnostics': 'existing verify.py conditions retained'},
            'scope': 'Synthetic 22-job conformance; no scientific approval or speed claim',
            'test_doubles': False, 'automatic_retry': False}


def git(checkout, *arguments):
    process = subprocess.run(['git', '-C', str(checkout), *arguments],
                             text=True, capture_output=True, timeout=15)
    if process.returncode:
        raise RuntimeError('Git source prerequisite failed: ' + process.stderr.strip())
    return process.stdout.strip()


def pinned_git(checkout, commit):
    require(re.fullmatch(r'[0-9a-f]{40}', commit) is not None, 'Expected a full Git commit.')
    require(git(checkout, 'rev-parse', 'HEAD') == commit, 'Reference Git HEAD differs from its pin.')
    require(not git(checkout, 'status', '--porcelain', '--untracked-files=all'),
            'Pinned reference/component checkout must be clean.')


def expected_update(runner, outcome, before, selected):
    require(outcome['run'] == list(selected),
            f"Wrong selected set: {outcome['run']} != {list(selected)}")
    retained = [key for key in ALL if key not in selected]
    require(outcome['retained'] == retained, 'Wrong retained job set.')
    for key in retained:
        require(runner.records[key] == before[key], f'Retained producing record changed: {key}')
    completed = {event['job'] for event in runner.events if event['state'] == 'complete'}
    require(completed == set(selected), 'Selected jobs lack actual completion events.')
    return {'executed': list(selected), 'retained': retained,
            'retained_records_equal': True, 'completion_events_match': True}


def paired_rules(runner):
    first = runner.output('mse_constant')
    for key in ('mse_index', 'mse_buffered'):
        other = runner.output(key)
        for field in ('assumptions', 'operating_models', 'error_streams'):
            require(other[field] == first[field], f'{key} changed paired {field}.')
    return {'rules': ['constant', 'index', 'buffered'],
            'assumptions_operating_models_and_actual_error_streams_equal': True}


def set_local_execution(runner):
    """Attach verified coordinator/image identity and explicitly supplied refs."""
    origin = runner.sources.coordinator_identity()
    require(origin.get('repository') == 'https://github.com/kyuhank/fisheries-workflow-demo'
            and isinstance(origin.get('commit'), str)
            and re.fullmatch(r'[0-9a-f]{40}', origin['commit']) is not None,
            'Local numerical validation requires the verified full coordinator commit.')
    execution = {'provider': 'Local Docker validation', 'repository': 'kyuhank/fisheries-workflow-demo',
                 'commit': origin['commit'], 'container': RBridge.require_container()}
    for variable, field in (('PAPER_EXECUTION_HOST', 'execution_host'),
                            ('PAPER_COMPUTE_SELECTION_RECEIPT', 'compute_selection_receipt')):
        value = os.environ.get(variable)
        if value:
            execution[field] = value
            execution[field + '_source'] = variable + ' (explicit parent-provided value)'
    runner.execution = execution
    return execution


def sources_and_lineage(runner, produced=ALL, retained_records=None):
    evidence = {}
    coordinator = runner.sources.coordinator_identity()
    for key in ALL:
        record = runner.records[key]
        expected = runner.sources.code_sources(key)
        actual = record.get('code_sources', {})
        required = runner.sources.required_files(key)
        for name, origin in expected.items():
            saved = actual.get(name, {})
            require(all(saved.get(field) == origin[field] for field in ('repository', 'path', 'sha256')),
                    f'Missing/different declared code origin: {key}/{name}')
            if key in produced:
                require(saved.get('commit') == origin['commit'], f'New execution used a stale source pin: {key}/{name}')
            require(name in required and sha256(required[name]) == origin['sha256'],
                    f'Actual analysis source bytes differ: {key}/{name}')
        job = runner.sources.job_path(key)
        origins = [origin for origin in expected.values()
                   if origin.get('path') == f'jobs/{key}/run.R']
        require(len(origins) == 1, f'Missing unique component entrypoint origin: {key}')
        saved_origin = record.get('analysis_source', {})
        require(all(saved_origin.get(field) == origins[0][field] for field in ('repository', 'path', 'sha256')),
                f'Wrong responsible analysis source: {key}')
        if key in produced:
            require(saved_origin.get('commit') == origins[0]['commit'], f'New job used stale component commit: {key}')
        require(origins[0]['sha256'] == sha256(job), f'Entrypoint byte hash differs: {key}')
        for parent, transfer in record['inputs'].items():
            producer = runner.records[parent]
            require(transfer['run_id'] == producer['run_id'], f'Stale producer run: {key}/{parent}')
            require(transfer['checksum'] == producer['outputs']['output.json'],
                    f'Wrong input checksum: {key}/{parent}')
        for name, checksum in record['outputs'].items():
            require(sha256(runner.directory / key / name) == checksum,
                    f'Output checksum differs: {key}/{name}')
        require(runner.valid(key), f'Invalid final producing record: {key}')
        if key not in produced:
            require(retained_records is not None and record == retained_records.get(key),
                    f'Retained producing record differs from its verified checkpoint: {key}')
            require(record.get('execution', {}).get('container') == RBridge.require_container(),
                    f'Retained record uses a different preserved image: {key}')
        if runner.execution and key in produced:
            require(record.get('source') == coordinator,
                    f'Producing record has a different coordinator source identity: {key}')
            for field, value in runner.execution.items():
                require(record.get('execution', {}).get(field) == value,
                        f'Producing record has a different actual execution reference: {key}/{field}')
        evidence[key] = {'run_id': record['run_id'], 'analysis_source': saved_origin,
                         'code_sources': actual, 'inputs': record['inputs'],
                         'outputs': record['outputs'], 'source': record.get('source'),
                         'execution': record.get('execution')}
    return evidence


def supplied_variant(original, variant, edit):
    """Validate parent-precommitted hydrated variants without requiring Git in Docker."""
    from workflow.sources import SourceResolver
    original = SourceResolver(root=ROOT, lock_path=original)
    variant = SourceResolver(root=ROOT, lock_path=variant)
    before = original.job_path('mse_buffered').read_bytes()
    after = variant.job_path('mse_buffered').read_bytes()
    if edit == 'code':
        require(before.decode().count(CODE_OLD) == 1, 'Expected exactly one declared Buffered expression.')
        require(after == before.decode().replace(CODE_OLD, CODE_NEW).encode(),
                'Supplied source variant differs from the declared executable edit.')
    elif edit == 'failure':
        require(after.decode() == '# Deliberate actual R failure for MR-08, not a scientific model change.\n'
                + f'calculate <- function(context) stop("{FAILURE_TEXT}")\n',
                'Supplied failure variant differs from the declared R failure.')
    else:
        raise ValueError('Unknown source variant.')
    require(original.origin('mse_buffered')['commit'] != variant.origin('mse_buffered')['commit'],
            'The code variant must declare its actual distinct source revision.')
    original_files, variant_files = original.archive_files(), variant.archive_files()
    require(original_files.keys() == variant_files.keys(), 'Variant changed component source membership.')
    for name, path in original_files.items():
        if name != 'components/mse/jobs/mse_buffered/run.R':
            require(path.read_bytes() == variant_files[name].read_bytes(),
                    'Variant changed undeclared component source: ' + name)
    return Path(variant.lock_path), {'edit': edit, 'before_sha256': hashlib.sha256(before).hexdigest(),
                                    'after_sha256': hashlib.sha256(after).hexdigest(),
                                    **{field: variant.origin('mse_buffered')[field]
                                       for field in ('repository', 'commit', 'path')},
                                    'lock_sha256': sha256(variant.lock_path),
                                    'source_verification': 'explicit precommitted source snapshot; byte verified'}


def mismatched_pin_fixture(resolver, destination):
    """Reject a declared revision that differs from preserved snapshot origins."""
    from workflow.sources import SourceResolver
    destination = Path(destination)
    destination.mkdir(parents=True, exist_ok=False)
    for name, data in resolver.archive_payload().items():
        path = destination / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
    path = destination / 'source-lock.json'
    lock = json.loads(path.read_text())
    original = lock['repositories']['cpue']['commit']
    lock['repositories']['cpue']['commit'] = '0' * 40 if original != '0' * 40 else '1' * 40
    path.write_text(json.dumps(lock, indent=2) + '\n')
    try:
        SourceResolver(root=resolver.root, lock_path=path)
    except ValueError as error:
        require('origin' in str(error).lower() or 'revision' in str(error).lower(),
                'Source-pin fixture failed for an unrelated prerequisite.')
        return {'status': 'EXPECTED_REJECTION', 'error': str(error),
                'original_commit': original, 'mismatched_commit': lock['repositories']['cpue']['commit'],
                'source_lock_sha256': sha256(path), 'calculation_attempted': False}
    raise AssertionError('A source lock with inconsistent pinned origins was accepted.')


def variant_lock(original, destination, edit):
    """Copy clean local Git checkouts and commit one declared fixture edit."""
    original, destination = Path(original).resolve(), Path(destination).resolve()
    lock = json.loads(original.read_text())
    destination.mkdir(parents=True, exist_ok=False)
    for name, info in lock['repositories'].items():
        checkout = (original.parent / info['checkout']).resolve()
        pinned_git(checkout, info['commit'])
        target = destination / 'repositories' / name
        shutil.copytree(checkout, target)
        info['checkout'] = target.relative_to(destination).as_posix()
        # Derived evidence is a real clean Git revision, never a fabricated snapshot.
        info.pop('files', None)
        info.pop('verification', None)
    mse = destination / lock['repositories']['mse']['checkout']
    source = mse / 'jobs/mse_buffered/run.R'
    before = source.read_text()
    if edit == 'code':
        require(before.count(CODE_OLD) == 1, 'Expected exactly one declared Buffered expression.')
        after = before.replace(CODE_OLD, CODE_NEW)
    elif edit == 'failure':
        after = '# Deliberate actual R failure for MR-08, not a scientific model change.\n'
        after += f'calculate <- function(context) stop("{FAILURE_TEXT}")\n'
    else:
        raise ValueError('Unknown source variant.')
    source.write_text(after)
    git(mse, 'add', 'jobs/mse_buffered/run.R')
    git(mse, '-c', 'user.name=Conformance fixture', '-c', 'user.email=fixture@invalid.example',
        'commit', '-m', f'Declared MR conformance fixture: {edit}')
    lock['repositories']['mse']['commit'] = git(mse, 'rev-parse', 'HEAD')
    for name in ('verification', 'source_snapshot', 'origin_receipt', 'snapshot_manifest'):
        lock.pop(name, None)
    path = destination / 'source-lock.json'
    path.write_text(json.dumps(lock, indent=2) + '\n')
    return path, {'edit': edit, 'before_sha256': hashlib.sha256(before.encode()).hexdigest(),
                  'after_sha256': sha256(source), 'repository': lock['repositories']['mse']['repository'],
                  'commit': lock['repositories']['mse']['commit'],
                  'lock_sha256': sha256(path), 'path': 'jobs/mse_buffered/run.R'}


CHECKPOINT_COMMIT = '5cca42bedf3ea61027b282799400adf8483980b9'
ALLOWED_PROOF_CHANGES = {
    'scripts/check-multi-repository.py', 'scripts/MULTI_REPOSITORY.md',
    'tests/test_multi_repository.py', 'tests/test_multi_repository_continuation.py', 'Dockerfile',
}


def validate_checkpoint(receipt_path, expected_sha256, origin_path, current_origin, image,
                        *, expected_origin_sha256=None):
    """Read immutable prior material; never calculate, repair or rewrite it."""
    from workflow.sources import contained
    receipt_path, origin_path = Path(receipt_path).resolve(), Path(origin_path).resolve()
    require(re.fullmatch(r'[0-9a-f]{64}', expected_sha256 or '') is not None
            and sha256(receipt_path) == expected_sha256, 'Checkpoint receipt SHA256 differs.')
    if expected_origin_sha256 is not None:
        require(re.fullmatch(r'[0-9a-f]{64}', expected_origin_sha256) is not None
                and sha256(origin_path) == expected_origin_sha256, 'Checkpoint origin SHA256 differs.')
    prior = json.loads(receipt_path.read_text())
    origin = json.loads(origin_path.read_text())
    require(origin.get('schema_version') == 1 and origin.get('commit') == CHECKPOINT_COMMIT
            and origin.get('repository') == 'https://github.com/kyuhank/fisheries-workflow-demo',
            'Checkpoint coordinator origin differs from the exact original executable commit.')
    require(current_origin.get('schema_version') == 1
            and current_origin.get('repository') == origin['repository']
            and re.fullmatch(r'[0-9a-f]{40}', current_origin.get('commit', '')) is not None
            and current_origin['commit'] != CHECKPOINT_COMMIT,
            'Current committed coordinator origin is invalid.')
    old_files, current_files = origin.get('files', {}), current_origin.get('files', {})
    require(isinstance(old_files, dict) and isinstance(current_files, dict)
            and 'workflow/engine.py' in old_files and 'verify.py' in old_files,
            'Checkpoint core source hashes are missing.')
    require((set(old_files) ^ set(current_files)) <= ALLOWED_PROOF_CHANGES,
            'Coordinator source membership changed beyond the proof-only correction.')
    for name in set(old_files) | set(current_files):
        for files in (old_files, current_files):
            if name in files:
                require(re.fullmatch(r'[0-9a-f]{64}', files[name]) is not None,
                        'Invalid coordinator source checksum: ' + name)
        if name not in ALLOWED_PROOF_CHANGES:
            require(old_files.get(name) == current_files.get(name),
                    'Analytical/core coordinator source bytes changed: ' + name)
    require(prior.get('status') == 'FAILED' and prior.get('actual_client') == 'codex'
            and prior.get('automatic_retry') is False and prior.get('test_doubles') is False,
            'Continuation requires the preserved actual FAILED receipt, without retry/doubles.')
    require(prior.get('runtime_image') == image, 'Checkpoint runtime image differs.')
    execution = prior.get('execution_identity', {})
    require(execution.get('provider') == 'Local Docker validation'
            and execution.get('repository') == 'kyuhank/fisheries-workflow-demo'
            and execution.get('commit') == CHECKPOINT_COMMIT and execution.get('container') == image,
            'Checkpoint actual executable/image identity differs.')
    require(prior.get('comparison', {}).get('sha256') == old_files['verify.py']
            and prior.get('comparison', {}).get('source') == 'verify.py',
            'Checkpoint comparison policy differs.')
    attempts = prior.get('attempts', [])
    require(len(attempts) == 7 and attempts[-1].get('case') == 'MR-04'
            and attempts[-1].get('name') == 'code-selective'
            and attempts[-1].get('kind') == ATTEMPTS[6][2]
            and attempts[-1].get('expected_selected') == list(BUFFER)
            and attempts[-1].get('status') == 'FAILED', 'Checkpoint failed MR-04 attempt is missing/different.')
    names = []
    for entry, (case, name, kind, selected) in zip(attempts[:6], ATTEMPTS[:6]):
        require(entry.get('case') == case and entry.get('name') == name
                and entry.get('kind') == kind and entry.get('expected_selected') == list(selected)
                and entry.get('status') == 'PASSED', 'Checkpoint first six completed attempts differ.')
        names.append(name)
    cases = prior.get('cases', {})
    require(set(cases) == {'MR-01', 'MR-02', 'MR-03'}
            and all(value.get('status') == 'PASSED' for value in cases.values()),
            'Checkpoint completed case inventory differs.')
    root, manifest = receipt_path.parent, prior.get('artifacts', {})
    require(isinstance(manifest, dict) and manifest, 'Checkpoint artifact manifest is missing.')
    for name, item in manifest.items():
        path = contained(root, name)
        require(path.is_file() and type(item.get('bytes')) is int
                and path.stat().st_size == item['bytes'] and sha256(path) == item.get('sha256'),
                'Checkpoint artifact checksum/size differs: ' + name)
    states = {}
    verified = {}
    for name in names:
        directory = contained(root, name)
        require(directory.is_dir(), 'Checkpoint completed output directory is missing: ' + name)
        entries = list(directory.rglob('*'))
        require(not any(path.is_symlink() for path in entries), 'Checkpoint output contains a symlink: ' + name)
        actual = {path.relative_to(root).as_posix() for path in entries if path.is_file()}
        declared = {path for path in manifest if path.startswith(name + '/')}
        require(actual == declared, 'Checkpoint output membership differs: ' + name)
        require(name + '/state.json' in manifest, 'Checkpoint saved state is missing: ' + name)
        state = json.loads((directory / 'state.json').read_text())
        settings = {**DEFAULTS, 'mse': True}
        if name.startswith('cpue-'):
            settings['min_hooks_a'] = 1200
        if name.startswith('buffer-'):
            settings['mse_buffer'] = 0.6
        require(state.get('settings') == settings and set(state.get('records', {})) == set(ALL),
                'Checkpoint configuration or complete job inventory differs: ' + name)
        for key, record in state['records'].items():
            record_file = contained(directory, key + '/record.json')
            require(record_file.is_file() and json.loads(record_file.read_text()) == record,
                    'Checkpoint state/producing record differs: ' + name + '/' + key)
            require(re.fullmatch(r'[0-9a-f]{64}', record.get('signature', '')) is not None
                    and 'output.json' in record.get('outputs', {}), 'Checkpoint signature/output pin missing.')
            for output, checksum in record['outputs'].items():
                require(sha256(contained(directory, key + '/' + output)) == checksum,
                        'Checkpoint producing output differs: ' + name + '/' + key + '/' + output)
            if name != 'reference-baseline':
                require(record.get('source') == {'repository': origin['repository'], 'commit': CHECKPOINT_COMMIT}
                        and record.get('execution') == execution,
                        'Checkpoint record has a different genuine producing coordinator/execution.')
                for path, checksum in record.get('code', {}).items():
                    if path in old_files:
                        require(checksum == old_files[path], 'Checkpoint loaded core source differs: ' + path)
                for path, checksum in record.get('data_files', {}).items():
                    source = path if path.startswith('data/') else 'data/' + path
                    require(source in old_files and checksum == old_files[source],
                            'Checkpoint input source differs: ' + source)
        states[name] = state
        verified.update({path: manifest[path] for path in declared})
    return {'receipt': prior, 'root': root, 'imported_names': names,
            'imported_cases': ['MR-01', 'MR-02', 'MR-03'], 'verified_artifacts': verified,
            'states': states, 'origin': origin, 'origin_sha256': sha256(origin_path)}


class EvidenceSuite:
    def __init__(self, output, source_lock, reference_root, reference_commit, timeout,
                 reference_manifest=None, code_source_lock=None, failure_source_lock=None,
                 continue_from=None, continue_sha256=None, checkpoint_origin=None,
                 checkpoint_origin_sha256=None):
        self.output = Path(output).resolve()
        self.lock = Path(source_lock).resolve()
        self.reference_root = Path(reference_root).resolve()
        self.reference_commit = reference_commit
        self.timeout = timeout
        self.reference_manifest = reference_manifest
        self.variant_locks = {'code': code_source_lock, 'failure': failure_source_lock}
        self.continuation = {'path': str(Path(continue_from).resolve()), 'sha256': continue_sha256,
                             'origin': str(Path(checkpoint_origin).resolve()),
                             'origin_sha256': checkpoint_origin_sha256} if continue_from else None
        self.invocation_attempts = ATTEMPTS[6:] if self.continuation else ATTEMPTS
        self.output.mkdir(parents=True, exist_ok=False)
        self.receipt = {**plan(timeout, bool(self.continuation)), 'status': 'RUNNING',
                        'attempts': [], 'imported_attempts': [], 'cases': {},
                        'imported_attempt_count': 0,
                        'source_lock': {'path': str(self.lock), 'sha256': sha256(self.lock)},
                        'coordinator_script_sha256': sha256(Path(__file__)),
                        'reference': {'path': str(self.reference_root), 'commit': reference_commit},
                        'actual_client': os.environ.get('PAPER_VALIDATION_CLIENT', 'unspecified reader'),
                        'client_identity_verification': 'caller-supplied label; not independently attested',
                        'runtime_image': RBridge.require_container()}
        if self.continuation:
            self.receipt['continuation_request'] = {**self.continuation,
                                                     'status': 'REQUESTED_NOT_YET_VERIFIED'}
        self.persist()

    def persist(self):
        path = self.output / 'evidence.json'
        temporary = path.with_suffix('.json.tmp')
        temporary.write_text(json.dumps(self.receipt, indent=2, allow_nan=False) + '\n')
        temporary.replace(path)

    def artifact_manifest(self):
        names = {entry[1] for entry in ATTEMPTS} | {'contract-fixtures'}
        artifacts = {}
        for child in self.output.iterdir():
            if child.is_dir() and child.name in names:
                paths = [path for path in child.rglob('*') if path.is_file()]
            elif child.is_file() and child.name != 'evidence.json' and not child.name.endswith('.tmp'):
                paths = [child]
            else:
                continue
            for path in paths:
                artifacts[path.relative_to(self.output).as_posix()] = {
                    'bytes': path.stat().st_size, 'sha256': sha256(path)}
        return artifacts

    async def attempt(self, name, action, expected_error=None):
        allowed = getattr(self, 'invocation_attempts', ATTEMPTS)
        declared = next((entry for entry in allowed if entry[1] == name), None)
        require(declared is not None, 'Undeclared execution attempt.')
        require(not any(item['name'] == name for item in self.receipt['attempts']),
                'An attempt may execute once; automatic replay is prohibited.')
        require(len(self.receipt['attempts']) < len(allowed), 'Finite attempt budget exhausted.')
        entry = {'case': declared[0], 'name': name, 'kind': declared[2],
                 'expected_selected': list(declared[3]), 'status': 'STARTED'}
        self.receipt['attempts'].append(entry)
        self.persist()
        print(json.dumps({'attempt': name, 'status': 'STARTED'}), flush=True)
        started = time.monotonic()
        try:
            value = await asyncio.wait_for(action(), timeout=self.timeout)
        except Exception as error:
            entry.update(status='EXPECTED_REJECTION' if expected_error and expected_error(error) else 'FAILED',
                         error_type=type(error).__name__, error=str(error),
                         wall_seconds=time.monotonic() - started)
            self.persist()
            print(json.dumps({'attempt': name, 'status': entry['status'], 'error': entry['error']}), flush=True)
            if entry['status'] != 'EXPECTED_REJECTION':
                raise
            return entry
        entry.update(status='PASSED', wall_seconds=time.monotonic() - started)
        self.persist()
        if expected_error:
            entry['status'] = 'FAILED'
            entry['error'] = 'Expected rejection did not occur.'
            self.persist()
            raise AssertionError(entry['error'])
        print(json.dumps({'attempt': name, 'status': 'PASSED'}), flush=True)
        return value

    def runner(self, name, source_lock=None, baseline=None):
        destination = self.output / name
        if baseline is not None:
            shutil.copytree(baseline.directory, destination)
        runner = Workflow(destination, source_lock=source_lock or self.lock)
        runner.configure({'mse': True})
        identity = set_local_execution(runner)
        expected = self.receipt.setdefault('execution_identity', copy.deepcopy(identity))
        require(identity == expected, 'Local execution identity changed within the frozen validation suite.')
        self.persist()
        return runner

    async def execute(self, name, runner, start='submission', error=None):
        value = await self.attempt(name, lambda: runner.run(start), error)
        entry = self.receipt['attempts'][-1]
        entry['running_job_events'] = [event['job'] for event in runner.events if event['state'] == 'running']
        entry['complete_job_events'] = [event['job'] for event in runner.events if event['state'] == 'complete']
        if error is None:
            declared = next(item for item in ATTEMPTS if item[1] == name)
            require(value['run'] == list(declared[3]), 'Execution differs from its frozen expected selected set: ' + name)
            require({event['job'] for event in runner.events if event['state'] == 'complete'} == set(declared[3]),
                    'Execution lacks actual completion events: ' + name)
            entry.update(executed=value['run'], retained=value['retained'], producing_run=value['run_id'])
        self.persist()
        return value

    def compare(self, reference, result):
        count = verify(reference.directory, result.directory)
        require(count == 22, 'Expected all 22 analytical outputs to agree.')
        return {'agreeing_outputs': count, 'comparison_policy_sha256': sha256(ROOT / 'verify.py')}

    def finish_case(self, case, details):
        self.receipt['cases'][case] = {'status': 'PASSED', **details}
        self.persist()

    def verify_reference_sources(self):
        if self.reference_manifest is None:
            pinned_git(self.reference_root, self.reference_commit)
            self.receipt['reference']['verification'] = 'clean pinned Git checkout'
        else:
            manifest_path = Path(self.reference_manifest)
            manifest = json.loads(manifest_path.read_text())
            require(manifest.get('schema_version') == 1 and manifest.get('commit') == self.reference_commit
                    and manifest.get('repository') == 'https://github.com/kyuhank/fisheries-workflow-demo',
                    'Reference snapshot manifest has a different source identity.')
            required = {'run.py', 'verify.py', 'Makefile'}
            for directory in ('workflow', 'jobs', 'data'):
                required.update(path.relative_to(self.reference_root).as_posix()
                                for path in (self.reference_root / directory).rglob('*')
                                if path.is_file() and path.suffix in ('.py', '.R', '.sql', '.qmd', '.json', '.sqlite'))
            require(required <= set(manifest.get('files', {})), 'Reference manifest omits required execution/input bytes.')
            from workflow.sources import contained
            for name, checksum in manifest['files'].items():
                require(sha256(contained(self.reference_root, name)) == checksum,
                        'Pinned reference byte mismatch: ' + name)
            self.receipt['reference'].update(verification='parent-pinned snapshot; actual byte hashes verified',
                                            manifest_sha256=sha256(manifest_path))

    async def reference(self):
        self.verify_reference_sources()
        settings = self.output / 'reference-settings.json'
        settings.write_text(json.dumps({'mse': True}) + '\n')
        destination = self.output / 'reference-baseline'
        command = [sys.executable, str(self.reference_root / 'run.py'), '--output', str(destination),
                   '--settings', str(settings)]
        environment = dict(os.environ)
        environment.pop('PAPER_SOURCE_LOCK', None)
        process = await asyncio.create_subprocess_exec(*command, cwd=self.reference_root, env=environment,
                                                      stdout=asyncio.subprocess.PIPE,
                                                      stderr=asyncio.subprocess.PIPE, start_new_session=True)
        try:
            stdout, stderr = await process.communicate()
        except BaseException:
            from workflow.r_bridge import kill_process_group
            kill_process_group(process)
            stdout, stderr = await process.communicate()
            (self.output / 'reference.stdout.log').write_bytes(stdout)
            (self.output / 'reference.stderr.log').write_bytes(stderr)
            raise
        (self.output / 'reference.stdout.log').write_bytes(stdout)
        (self.output / 'reference.stderr.log').write_bytes(stderr)
        self.receipt['reference']['argv'] = command
        self.receipt['reference']['exit_code'] = process.returncode
        self.persist()
        require(process.returncode == 0, 'Pinned mono-repository reference failed; see preserved logs.')
        state = json.loads((destination / 'state.json').read_text())
        require(state['last_plan']['run'] == list(ALL), 'Reference did not execute all 22 jobs.')
        self.receipt['reference'].update(executed=state['last_plan']['run'],
                                         retained=state['last_plan']['retained'],
                                         producing_run=f"Run {state['run_number']:03d}")
        self.persist()
        return destination

    def variant(self, edit):
        if self.variant_locks[edit] is not None:
            return supplied_variant(self.lock, self.variant_locks[edit], edit)
        return variant_lock(self.lock, self.output / (edit + '-variant'), edit)

    async def contract_fixture(self, name, runner, recipient, parent, malformed):
        path = runner.directory / parent / 'output.json'
        original_bytes = path.read_bytes()
        original_record = copy.deepcopy(runner.records[parent])
        payload = malformed(json.loads(original_bytes))
        bad_bytes = json.dumps(payload, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()
        # An explicitly recorded fault changes the actual transfer bytes and its
        # fixture checkpoint checksum, so the semantic contract is exercised.
        # Neither altered content nor altered metadata is attributed to a real
        # producing calculation; the original record and bytes are restored.
        altered_record = copy.deepcopy(original_record)
        altered_record['outputs']['output.json'] = hashlib.sha256(bad_bytes).hexdigest()
        fixture = runner.directory / (name + '.json')
        fixture.write_text(json.dumps({'recipient': recipient, 'parent': parent, 'payload': payload,
                                       'fault_injection': 'malformed actual file and fixture-only checkpoint checksum; no producing R calculation',
                                       'original_producer_record': original_record,
                                       'altered_fixture_record': altered_record}, indent=2) + '\n')
        adapter = runner.calculator.calculate
        invoked = []
        async def observe(context):
            invoked.append(context['key'])
            return await adapter(context)
        path.write_bytes(bad_bytes)
        runner.records[parent] = altered_record
        runner.calculator.calculate = observe
        try:
            result = await self.attempt(name, lambda: runner.calculate(recipient, 'Contract fixture'),
                                        lambda error: isinstance(error, ValueError) and 'contract:' in str(error).lower())
            require(not invoked, 'An incompatible transfer reached the R calculation adapter.')
            result.update(adapter_invoked=False, fixture_sha256=sha256(fixture),
                          fixture=fixture.relative_to(self.output).as_posix())
            self.persist()
            return result
        finally:
            path.write_bytes(original_bytes)
            runner.records[parent] = original_record
            runner.calculator.calculate = adapter

    def import_checkpoint(self):
        """Validate/copy six completed attempts, without running their calculations."""
        from workflow.sources import SourceResolver, contained
        resolver = SourceResolver(root=ROOT, lock_path=self.lock)
        resolver.verify(); resolver.coordinator_identity()
        current = json.loads((ROOT / 'coordinator-origin.json').read_text())
        data = validate_checkpoint(self.continuation['path'], self.continuation['sha256'],
                                   self.continuation['origin'], current, RBridge.require_container(),
                                   expected_origin_sha256=self.continuation['origin_sha256'])
        prior = data['receipt']
        require(sha256(self.lock) == prior['source_lock']['sha256'],
                'Continuation baseline component lock differs from the actual prior run.')
        require(self.reference_manifest is not None
                and sha256(self.reference_manifest) == prior['reference']['manifest_sha256']
                and self.reference_commit == prior['reference']['commit'],
                'Continuation monorepo reference identity differs.')
        self.verify_reference_sources()
        provenance = {'receipt_sha256': self.continuation['sha256'],
                      'receipt_path': str(Path(self.continuation['path']).resolve()),
                      'original_coordinator_commit': CHECKPOINT_COMMIT,
                      'origin_sha256': data['origin_sha256'],
                      'imported_without_recalculation': True}
        for name in data['imported_names']:
            shutil.copytree(contained(data['root'], name), self.output / name)
        for name, item in data['verified_artifacts'].items():
            copied = contained(self.output, name)
            require(copied.stat().st_size == item['bytes'] and sha256(copied) == item['sha256'],
                    'Imported checkpoint copy differs: ' + name)
        for name in ('reference-settings.json', 'reference.stdout.log', 'reference.stderr.log'):
            if name in prior['artifacts']:
                shutil.copyfile(contained(data['root'], name), self.output / name)
                require(sha256(self.output / name) == prior['artifacts'][name]['sha256'],
                        'Imported reference log/settings copy differs: ' + name)
        loaded = {}
        for name in data['imported_names'][1:]:
            runner = self.runner(name)
            require(runner.records == data['states'][name]['records']
                    and runner.settings == data['states'][name]['settings'],
                    'Imported checkpoint state changed during loading: ' + name)
            sources_and_lineage(runner, produced=(), retained_records=data['states'][name]['records'])
            loaded[name] = runner
        # Rechecking copied existing output bytes is not an analytical rerun.
        require(verify(self.output / 'reference-baseline', loaded['split-baseline'].directory) == 22,
                'Imported mono/split output comparison differs.')
        self.compare(loaded['cpue-fresh'], loaded['cpue-selective'])
        self.compare(loaded['buffer-fresh'], loaded['buffer-selective'])
        self.receipt['imported_attempts'] = [{**copy.deepcopy(entry), 'import_provenance': provenance}
                                           for entry in prior['attempts'][:6]]
        self.receipt['imported_attempt_count'] = 6
        self.receipt['cases'] = {case: {**copy.deepcopy(prior['cases'][case]),
                                      'import_provenance': provenance} for case in data['imported_cases']}
        self.receipt['continuation'] = {**provenance, 'prior_status': prior['status'],
                                        'preserved_failed_attempt': copy.deepcopy(prior['attempts'][6]),
                                        'verified_imported_artifacts': data['verified_artifacts'],
                                        'analytical_core_and_input_sources_unchanged': True,
                                        'remaining_actual_attempts': 12}
        self.receipt['continuation_request']['status'] = 'VERIFIED_IMPORTED'
        self.persist()
        return loaded['split-baseline'], loaded['cpue-selective']

    async def run(self):
        from workflow.sources import SourceResolver
        SourceResolver(root=ROOT, lock_path=self.lock).verify()
        if self.continuation:
            baseline, cpue = self.import_checkpoint()
        else:
            mono = await self.attempt('reference-baseline', self.reference)
            baseline = self.runner('split-baseline')
            full = await self.execute('split-baseline', baseline)
            require(full['run'] == list(ALL) and not full['retained'], 'Split baseline was not a fresh full run.')
            require(verify(mono, baseline.directory) == 22, 'Split baseline differs from mono reference.')
            self.finish_case('MR-01', {'executed': full['run'], 'retained': full['retained'],
                                     'agreeing_reference_outputs': 22, 'records': sources_and_lineage(baseline),
                                     'paired_rules': paired_rules(baseline)})

            cpue = self.runner('cpue-selective', baseline=baseline)
            before = copy.deepcopy(cpue.records)
            cpue.configure({'min_hooks_a': 1200})
            changed = await self.execute('cpue-selective', cpue, 'cpue_a')
            update = expected_update(cpue, changed, before, CPUE)
            fresh = self.runner('cpue-fresh')
            fresh.configure({'min_hooks_a': 1200})
            await self.execute('cpue-fresh', fresh)
            self.finish_case('MR-02', {**update, **self.compare(fresh, cpue),
                                     'records': sources_and_lineage(cpue, CPUE, before)})

            buffered = self.runner('buffer-selective', baseline=baseline)
            before = copy.deepcopy(buffered.records)
            buffered.configure({'mse_buffer': 0.6})
            changed = await self.execute('buffer-selective', buffered, 'mse_report')
            update = expected_update(buffered, changed, before, BUFFER)
            fresh_buffer = self.runner('buffer-fresh')
            fresh_buffer.configure({'mse_buffer': 0.6})
            await self.execute('buffer-fresh', fresh_buffer)
            self.finish_case('MR-03', {**update, **self.compare(fresh_buffer, buffered),
                                     'paired_rules': paired_rules(buffered),
                                     'records': sources_and_lineage(buffered, BUFFER, before)})

        code_lock, edit = self.variant('code')
        code = self.runner('code-selective', source_lock=code_lock, baseline=baseline)
        before = copy.deepcopy(code.records)
        require(code.settings['mse_buffer'] == 0.8, 'MR-04 configuration must remain fixed.')
        changed = await self.execute('code-selective', code, 'mse_report')
        update = expected_update(code, changed, before, BUFFER)
        require(code.output('mse_buffered')['metrics']['mean_catch_t'] !=
                baseline.output('mse_buffered')['metrics']['mean_catch_t'],
                'Executable component code edit did not change the Buffered result.')
        fresh_code = self.runner('code-fresh', source_lock=code_lock)
        await self.execute('code-fresh', fresh_code)
        self.finish_case('MR-04', {**update, **self.compare(fresh_code, code), 'edit': edit,
                                 'paired_rules': paired_rules(code), 'records': sources_and_lineage(code, BUFFER, before)})

        invalid = self.runner('contract-fixtures', baseline=baseline)
        bad_cpue = await self.contract_fixture('invalid-cpue', invalid, 'prepare_a', 'cpue_a',
                                               lambda value: {**value, 'series': []})
        valid_cpue = await self.attempt('valid-cpue', lambda: invalid.calculate('prepare_a', 'Contract recovery'))
        compare(baseline.output('prepare_a'), valid_cpue, 'prepare_a')
        (invalid.directory / 'valid-cpue.json').write_text(json.dumps(valid_cpue, indent=2) + '\n')
        bad_assessment = await self.contract_fixture('invalid-assessment', invalid, 'mse_prepare',
                                                     'assessment_a1', lambda value: {**value, 'K': -1})
        valid_assessment = await self.attempt('valid-assessment', lambda: invalid.calculate('mse_prepare', 'Contract recovery'))
        compare(baseline.output('mse_prepare'), valid_assessment, 'mse_prepare')
        (invalid.directory / 'valid-assessment.json').write_text(json.dumps(valid_assessment, indent=2) + '\n')
        require(invalid.records == baseline.records, 'Direct contract fixtures changed saved producing records.')
        self.finish_case('MR-05', {'cpue_rejection': bad_cpue, 'assessment_rejection': bad_assessment,
                                 'corrected_real_calculation_calls': ['prepare_a', 'mse_prepare'],
                                 'corrected_outputs_agree_with_valid_baseline': True,
                                 'saved_records_unchanged': invalid.records == baseline.records})

        integrity = []
        for name, missing in (('missing-transfer', True), ('tampered-transfer', False)):
            runner = self.runner(name, baseline=baseline)
            before = copy.deepcopy(runner.records)
            path = runner.directory / 'cpue_a/output.json'
            if missing:
                path.unlink()
            else:
                value = runner.output('cpue_a')
                value['series'][0]['index'] *= 1.01
                path.write_text(json.dumps(value))
            require(not runner.valid('cpue_a'), 'Transferred output damage did not block reuse.')
            changed = await self.execute(name, runner, 'assessment_report')
            integrity.append({'fixture': name, **expected_update(runner, changed, before, CPUE),
                              **self.compare(baseline, runner), 'records': sources_and_lineage(runner, CPUE, before)})
        self.finish_case('MR-06', {'checks': integrity})

        stale = self.runner('stale-corrected', baseline=baseline)
        pin_rejection = mismatched_pin_fixture(stale.sources, self.output / 'mismatched-source-pin')
        before = copy.deepcopy(stale.records)
        stale.configure({'min_hooks_a': 1200})
        require(not stale.valid('cpue_a'), 'Old well-formed CPUE output was accepted under changed settings.')
        rejection = await self.attempt('stale-transfer', lambda: stale.calculate('prepare_a', 'Stale fixture'),
                                       lambda error: any(word in str(error).lower()
                                                         for word in ('stale', 'contract', 'invalid', 'revision')))
        changed = await self.execute('stale-corrected', stale, 'cpue_a')
        self.finish_case('MR-07', {'rejection': rejection,
                                 'source_pin_rejection': pin_rejection,
                                 'older_well_formed_producer_record': before['cpue_a'],
                                 **expected_update(stale, changed, before, CPUE), **self.compare(cpue, stale),
                                 'unchanged_branch_historical_run': stale.records['cpue_b']['run_id'],
                                 'records': sources_and_lineage(stale, CPUE, before)})

        failure_lock, edit = self.variant('failure')
        failed = self.runner('failed-rule', source_lock=failure_lock, baseline=baseline)
        before = copy.deepcopy(failed.records)
        old_report_bytes = (failed.directory / 'mse_report/report.html').read_bytes()
        rejection = await self.execute('failed-rule', failed, 'mse_report',
                                        lambda error: FAILURE_TEXT in str(error) and 'R job mse_buffered failed' in str(error))
        require(failed.records['mse_summary'] == before['mse_summary'] and
                failed.records['mse_report'] == before['mse_report'], 'Failed case replaced earlier summary/report.')
        require((failed.directory / 'mse_report/report.html').read_bytes() == old_report_bytes,
                'Failed case replaced earlier report bytes.')
        require(not any(event['job'] in ('mse_summary', 'mse_report') and event['state'] == 'running'
                        for event in failed.events), 'Summary/report started despite a failed required case.')
        failed_events = copy.deepcopy(failed.events)
        recovered = Workflow(failed.directory, source_lock=self.lock)
        require(set_local_execution(recovered) == self.receipt['execution_identity'],
                'Recovered workflow has a different actual local execution identity.')
        changed = await self.execute('recovered-rule', recovered, 'mse_report')
        self.finish_case('MR-08', {'failure': rejection, 'edit': edit,
                                 'failure_events': failed_events,
                                 'earlier_summary_record': before['mse_summary'],
                                 'earlier_report_record': before['mse_report'],
                                 'previous_summary_and_report_retained_during_failure': True,
                                 **expected_update(recovered, changed, before, BUFFER),
                                 **self.compare(baseline, recovered), 'records': sources_and_lineage(recovered, BUFFER, before)})
        require(len(self.receipt['attempts']) == len(self.invocation_attempts),
                'Declared new actual attempt inventory was not completed.')
        require(len(self.receipt['attempts']) + len(self.receipt['imported_attempts']) == len(ATTEMPTS),
                'Combined actual/imported case inventory differs.')
        self.receipt.update(status='PASSED', completed_new_attempts=len(self.receipt['attempts']),
                            completed_imported_attempts=len(self.receipt['imported_attempts']),
                            software=baseline.software(),
                            artifacts=self.artifact_manifest(),
                            scientific_status='UNREVIEWED; technical conformance only')
        self.persist()
        return self.receipt


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--plan', action='store_true', help='Print frozen finite case inventory; no calculations.')
    parser.add_argument('--source-lock', type=Path, default=ROOT / 'source-lock.json')
    parser.add_argument('--reference-root', type=Path)
    parser.add_argument('--reference-commit', default=REFERENCE_COMMIT)
    parser.add_argument('--reference-manifest', type=Path, help='Explicit parent-pinned mono snapshot manifest, when Git is absent.')
    parser.add_argument('--code-source-lock', type=Path, help='Parent-precommitted and hydrated MR-04 source variant.')
    parser.add_argument('--failure-source-lock', type=Path, help='Parent-precommitted and hydrated MR-08 source variant.')
    parser.add_argument('--continue-from', type=Path, help='Explicit immutable first FAILED evidence.json; import only completed MR-01--03.')
    parser.add_argument('--continue-sha256', help='Required full SHA256 of that preserved FAILED receipt.')
    parser.add_argument('--checkpoint-origin', type=Path, help='Preserved original coordinator-origin.json at the first executable commit.')
    parser.add_argument('--checkpoint-origin-sha256', help='Required full SHA256 of the preserved original coordinator origin.')
    parser.add_argument('--output', type=Path)
    parser.add_argument('--timeout', type=int, default=180)
    args = parser.parse_args()
    if not 1 <= args.timeout <= 1800:
        parser.error('--timeout must be a finite 1--1800 seconds; changing it requires a newly pinned invocation.')
    if args.plan:
        print(json.dumps(plan(args.timeout, bool(args.continue_from)), indent=2))
        return 0
    if args.reference_root is None or args.output is None:
        parser.error('Numerical execution requires --reference-root and a fresh --output directory.')
    continuation_fields = (args.continue_sha256, args.checkpoint_origin, args.checkpoint_origin_sha256)
    if args.continue_from:
        if (not all(continuation_fields) or args.reference_manifest is None
                or args.code_source_lock is None or args.failure_source_lock is None):
            parser.error('Explicit continuation requires both receipt/origin SHA pins, the preserved origin, reference manifest and both supplied variant locks.')
    elif any(continuation_fields):
        parser.error('Checkpoint pins require explicit --continue-from; no automatic continuation is allowed.')
    suite = None
    try:
        suite = EvidenceSuite(args.output, args.source_lock, args.reference_root,
                              args.reference_commit, args.timeout, args.reference_manifest,
                              args.code_source_lock, args.failure_source_lock,
                              args.continue_from, args.continue_sha256,
                              args.checkpoint_origin, args.checkpoint_origin_sha256)
        asyncio.run(suite.run())
    except Exception as error:
        if suite is not None:
            suite.receipt.update(status='FAILED', error_type=type(error).__name__, error=str(error),
                                 traceback=traceback.format_exc(), artifacts=suite.artifact_manifest())
            suite.persist()
        print(json.dumps({'status': 'FAILED', 'error_type': type(error).__name__, 'error': str(error)}), file=sys.stderr)
        return 1
    print(json.dumps({'status': 'PASSED', 'cases': 8, 'new_attempts': len(suite.receipt['attempts']),
                      'imported_attempts': len(suite.receipt['imported_attempts']),
                      'receipt': str(suite.output / 'evidence.json')}))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
