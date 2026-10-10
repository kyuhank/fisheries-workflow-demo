"""Check actual hosted execution, recorded identities and portable reproduction.

This manual check creates temporary reader sessions and dispatches real runs.
POST requests are never retried: a lost response leaves the outcome uncertain.
Reader capabilities stay in .state with mode 0600 and are never in the report.
"""
import base64
import hashlib
import io
import json
import os
from pathlib import Path, PurePosixPath
import platform
import re
import sqlite3
import stat
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request
import zipfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from workflow.spec import HANDOVERS, SPEC, STAGES
from workflow.r_bridge import RBridge
from workflow.engine import source_payload, FROZEN_SOURCE

CONFIG = json.loads((ROOT / 'cloud/config.json').read_text())
BASE = CONFIG['url'].rstrip('/')
REPOSITORY = 'kyuhank/fisheries-workflow-demo'
IMAGE = os.environ.get('PAPER_RUNTIME_IMAGE')
EXPECTED_COMMIT = os.environ.get('PAPER_EXPECTED_COMMIT')
SETTINGS = {'last_year': 2023, 'min_hooks_a': 0, 'growth_rate_2': .3,
            'mse': True, 'mse_buffer': .8}
CHECKS = []
VERIFIED_RUNS = {}
REPORT = {
    'status': 'running',
    'scope': 'Hosted synthetic example and numerical reproduction; no scientific-validity claim.',
    'repository': REPOSITORY,
    'container': IMAGE,
    'comparison_tolerances': {'relative': 1e-6, 'absolute': 1e-9},
    'checks': CHECKS,
}


class APIError(RuntimeError):
    def __init__(self, path, status, code=None):
        self.status, self.code = status, code
        super().__init__(f'API {path.split("?")[0]} returned HTTP {status}.')


def request(path, body=None, session=None, target_session=None):
    headers = {'Content-Type': 'application/json'}
    if session:
        parts = urllib.parse.urlsplit(path)
        query = urllib.parse.parse_qsl(parts.query, keep_blank_values=True)
        if any(key == 'session' for key, _ in query):
            raise ValueError('Pass the target reader through target_session.')
        query.append(('session', target_session or session['id']))
        path = urllib.parse.urlunsplit(('', '', parts.path,
                                      urllib.parse.urlencode(query), ''))
        headers['Authorization'] = 'Bearer ' + session['token']
    payload = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(BASE + path, data=payload, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=40) as response:
            return json.load(response)
    except urllib.error.HTTPError as error:
        try:
            code = json.load(error).get('code')
        except (ValueError, AttributeError):
            code = None
        raise APIError(path, error.code, code) from None
    except (urllib.error.URLError, TimeoutError, ConnectionError, json.JSONDecodeError):
        detail = ' Outcome may be unknown; do not repeat this dispatch.' if body is not None else ''
        raise RuntimeError('API connection interrupted.' + detail) from None


def poll(path, session):
    """Retry only reads; an HTTP failure never counts as an isolation pass."""
    for attempt in range(3):
        try:
            return request(path, session=session)
        except APIError as error:
            if error.status not in (408, 429, 500, 502, 503, 504) or attempt == 2:
                raise
        except RuntimeError:
            if attempt == 2:
                raise
        time.sleep(2 ** attempt)


def github(path):
    req = urllib.request.Request('https://api.github.com/repos/' + REPOSITORY + '/' + path,
                                 headers={'Accept': 'application/vnd.github+json',
                                          'User-Agent': 'fisheries-workflow-online-check'})
    try:
        with urllib.request.urlopen(req, timeout=40) as response:
            return json.load(response)
    except (urllib.error.URLError, TimeoutError, ConnectionError, json.JSONDecodeError):
        raise RuntimeError('Public GitHub execution verification failed.') from None


def check_identity(run, value, previous):
    commit, run_id = run['commit_sha'], str(run['github_run'])
    assert re.fullmatch(r'[a-f0-9]{40}', commit), 'Missing real source commit.'
    assert run_id.isdigit() and int(run_id) > 0, 'Missing real GitHub run identity.'
    if EXPECTED_COMMIT:
        assert commit == EXPECTED_COMMIT, 'Hosted run used a different source commit.'
    assert github('commits/' + commit)['sha'] == commit, 'Source commit unavailable.'
    deadline = time.monotonic() + 120
    while True:
        remote = github('actions/runs/' + run_id)
        assert remote['repository']['full_name'] == REPOSITORY, 'Wrong execution repository.'
        assert remote['head_sha'] == commit, 'GitHub source commit differs.'
        assert remote['head_branch'] == 'main', 'Execution did not use main.'
        assert remote['event'] == 'workflow_dispatch', 'Unexpected execution trigger.'
        assert remote['path'] == '.github/workflows/live.yml', 'Wrong execution workflow.'
        if remote['status'] == 'completed':
            assert remote['conclusion'] == 'success', 'GitHub execution did not succeed.'
            break
        if time.monotonic() >= deadline:
            raise TimeoutError('GitHub has not confirmed the completed execution.')
        time.sleep(5)
    VERIFIED_RUNS[run_id] = commit
    for key in value['run']:
        record = value['records'][key]
        execution = record['execution']
        assert execution['provider'] == 'GitHub Actions', 'Wrong execution provider.'
        assert execution['repository'] == REPOSITORY, 'Record has the old repository.'
        assert execution['container'] == IMAGE, 'Record has the wrong container digest.'
        assert record['software']['container'] == IMAGE, 'Software image differs from execution.'
        assert record['software']['runtime'] == 'Rscript (container)', 'Calculation backend differs.'
        assert record['software'].get('RTMB'), 'Missing actual RTMB package version.'
        assert execution['commit'] == commit, 'Record has a different source commit.'
        assert str(execution['github_run']) == run_id, 'Record has a different execution identity.'
        assert record['run_id'] == value['run_id'], 'Job has a different analysis run identity.'
        assert record['source'] == {'repository': 'https://github.com/' + REPOSITORY,
                                    'commit': commit}, 'Recorded source differs.'
        if record.get('analysis_source'):
            from workflow.sources import SourceResolver
            resolver = SourceResolver(ROOT)
            assert record['analysis_source'] == resolver.origin(key), 'Component source differs.'
            for name, origin in resolver.code_sources(key).items():
                assert record['code_sources'][name] == origin, 'Loaded component source bytes differ.'
    for key in value['retained']:
        assert previous is not None, 'Fresh session unexpectedly retained a result.'
        assert value['records'][key] == previous['records'][key], 'Retained record changed: ' + key
    for record in value['records'].values():
        execution = record['execution']
        assert execution['repository'] == REPOSITORY, 'A saved record has the old repository.'
        assert execution['container'] == IMAGE, 'A saved record has the wrong container digest.'
        assert VERIFIED_RUNS.get(str(execution['github_run'])) == execution['commit'], 'Unverified saved execution identity.'


def execute(session, start, expected_run, handover='connected', previous=None,
            expected_boundaries=None, scope='workflow'):
    result = request('/run', {'start': start, 'settings': SETTINGS,
                             'handover': handover, 'scope': scope}, session)
    print('Requested', start, scope, flush=True)
    cursor, deadline = 0, time.monotonic() + 600
    transferred, pending, status_deadline = False, None, None
    events, boundaries, confirmed, reports_before_transfer = [], [], [], []
    while time.monotonic() < deadline:
        update = poll('/state?after=' + str(cursor), session)
        run = update['run']
        assert run is not None and run['id'] == result['id'], 'State belongs to a different request.'
        for row in update['events']:
            cursor = row['id']
            event = row['event']
            events.append(event)
            print(event.get('job', 'workflow'), event['state'], flush=True)
            if event['state'] == 'handover':
                pending = event
                boundaries.append(event['boundary'])
                planned = next(e['run'] for e in events if e['state'] == 'plan')
                expected = [key for key, parents in HANDOVERS[event['boundary']].items()
                            if key in planned and any(parent in planned for parent in parents)]
                assert event['group'] == expected, 'Wrong file-transfer recipients.'
        if run['status'] in ('failed', 'expired'):
            raise RuntimeError('Hosted execution ended with status ' + run['status'] + '.')
        report = {'cpue': 'cpue_report', 'assessment': 'assessment_report'}.get(pending['boundary']) if pending else None
        if pending and (report is None or any(e.get('job') == report and e['state'] == 'complete' for e in events)):
            # State and events can straddle the database's handover update.
            if run['status'] != 'handover':
                if status_deadline is None:
                    status_deadline = time.monotonic() + 15
                if run['status'] == 'complete' or time.monotonic() >= status_deadline:
                    raise AssertionError('Reporting did not preserve the pending transfer.')
                time.sleep(1)
                continue
            assert not any(e.get('job') in pending['group'] and e['state'] == 'running' for e in events), 'A recipient started before file transfer.'
            if pending['boundary'] == 'assessment':
                planned = next(e['run'] for e in events if e['state'] == 'plan')
                completed = {e.get('job') for e in events if e['state'] == 'complete'}
                assert all(key in completed for key in SPEC['mse_prepare']['parents'] if key in planned), 'MSE transfer preceded its assessment inputs.'
                assert not any(SPEC.get(e.get('job'), {}).get('module') == 'mse' and e['state'] == 'running' for e in events), 'MSE started before transfer.'
            if previous:
                key = 'mse_prepare' if pending['boundary'] == 'assessment' else 'assessment_a1'
                old = request('/output?job=' + key, session=session)
                assert old['record'] == previous['records'][key], 'Previous result changed before transfer.'
            confirmed.append(pending['boundary'])
            if report:
                reports_before_transfer.append(pending['boundary'])
            request('/transfer', {'connect': False}, session)
            transferred, pending, status_deadline = True, None, None
        if run['status'] == 'complete':
            if handover == 'manual':
                assert transferred, 'Manual execution did not require confirmation.'
            if expected_boundaries is not None:
                received = [e['boundary'] for e in events if e['state'] == 'received']
                assert boundaries == confirmed == received == expected_boundaries, 'Transfer boundaries differ.'
            running, completed = {}, {}
            for key in expected_run:
                running[key] = [i for i, e in enumerate(events)
                                if e.get('job') == key and e['state'] == 'running']
                completed[key] = [i for i, e in enumerate(events)
                                  if e.get('job') == key and e['state'] == 'complete']
                assert running[key], 'Missing running event: ' + key
                assert completed[key], 'Missing complete event: ' + key
                assert (running[key][0] < completed[key][0] and
                        running[key][-1] < completed[key][-1]), 'Job event order failed: ' + key
                # The QC example deliberately returns the first submission and
                # starts submission/QC again. Other jobs execute once per run.
                if key not in ('submission', 'qc'):
                    assert len(running[key]) == len(completed[key]) == 1, 'Repeated job events: ' + key
            assert {e.get('job') for e in events if e['state'] == 'running'} == set(expected_run), 'Unexpected running jobs.'
            assert {e.get('job') for e in events if e['state'] == 'complete'} == set(expected_run), 'Unexpected completed jobs.'
            for group in STAGES:
                peer_completions = [completed[key][-1] for key in group if key in completed]
                for key, job in SPEC.items():
                    if peer_completions and set(job['parents']).intersection(group) and key in running:
                        if key == 'qc' and group == ['submission']:
                            # Initial QC starts after the initial submission;
                            # restarted QC waits for the corrected submission.
                            assert completed['submission'][0] < running[key][0], 'Initial QC input barrier failed.'
                            assert completed['submission'][-1] < running[key][-1], 'Corrected QC input barrier failed.'
                        else:
                            assert max(peer_completions) < running[key][0], 'Peer-group barrier failed.'
            value = run['result']
            assert value['run'] == expected_run, 'Unexpected executed jobs for ' + start + '.'
            retained = [key for key in SPEC if key not in expected_run and previous and key in previous['records']]
            assert value['retained'] == retained, 'Unexpected retained jobs for ' + start + '.'
            assert value['scope'] == scope and value['start'] == start, 'Execution scope differs.'
            plans = [e for e in events if e['state'] == 'plan']
            assert len(plans) == 1 and plans[0]['run'] == expected_run, 'Recorded plan differs.'
            check_identity(run, value, previous)
            CHECKS.append({'start': start, 'scope': scope, 'handover': handover,
                           'github_run': str(run['github_run']), 'commit': run['commit_sha'],
                           'executed': value['run'], 'retained': value['retained'],
                           'retained_records_preserved': True,
                           'execution_identity_verified': True,
                           'manual_transfer_checked': transferred,
                           'peer_barriers_checked': True,
                           'manual_transfer_boundaries': confirmed,
                           'report_completed_before_cpue_transfer': 'cpue' in reports_before_transfer,
                           'report_completed_before_assessment_transfer': 'assessment' in reports_before_transfer,
                           'events': [{key: e[key] for key in ('job', 'state', 'group', 'boundary') if key in e} for e in events]})
            print('Completed GitHub run', run['github_run'], 'jobs', len(value['run']), flush=True)
            return value
        time.sleep(1)
    raise TimeoutError('Online execution timed out; inspect the existing run before another dispatch.')


def reader(name):
    session = request('/session', {})
    directory = ROOT / '.state'
    directory.mkdir(mode=0o700, exist_ok=True)
    path = directory / name
    flags = os.O_WRONLY | os.O_CREAT | os.O_TRUNC | getattr(os, 'O_NOFOLLOW', 0)
    descriptor = os.open(path, flags, 0o600)
    os.fchmod(descriptor, 0o600)
    with os.fdopen(descriptor, 'w') as output:
        json.dump(session, output)
    return session


def reproduce(session, value, job=None):
    payload = request('/bundle', session=session)['bundle']
    data = base64.b64decode(payload, validate=True)
    with tempfile.TemporaryDirectory(prefix='fisheries-online-') as temporary:
        destination = Path(temporary)
        with zipfile.ZipFile(io.BytesIO(data)) as archive:
            members = archive.infolist()
            names = [member.filename for member in members]
            assert len(names) == len(set(names)) and len(names) <= 500, 'Invalid bundle member list.'
            assert sum(member.file_size for member in members) <= 64_000_000, 'Bundle exceeds size limit.'
            for member in members:
                path = PurePosixPath(member.filename)
                assert not path.is_absolute() and '..' not in path.parts and '\\' not in member.filename, 'Unsafe bundle member.'
                assert not stat.S_ISLNK(member.external_attr >> 16), 'Bundle contains a symbolic link.'
                assert member.file_size <= 8_000_000 and not member.is_dir(), 'Invalid bundle file.'
            manifest = json.loads(archive.read('SHA256SUMS.json'))
            assert set(manifest) == set(names) - {'SHA256SUMS.json', 'REPRODUCE.txt'}, 'Checksum manifest is incomplete.'
            for name, checksum in manifest.items():
                assert hashlib.sha256(archive.read(name)).hexdigest() == checksum, 'Bundle checksum mismatch.'
                if not name.startswith('reference/') and name not in ('settings.json', FROZEN_SOURCE):
                    source = source_payload().get(name)
                    assert source is not None and hashlib.sha256(source).hexdigest() == checksum, 'Bundle source differs from the checked checkout.'
            state = json.loads(archive.read('reference/state.json'))
            assert state['records'] == value['records'], 'Bundle records differ from completed execution.'
            assert state['settings'] == value['settings'], 'Bundle settings differ from completed execution.'
            supplied = state['records']['submission']['execution']['data_checksum']
            assert isinstance(supplied, str) and re.fullmatch(r'[a-f0-9]{64}', supplied), 'Invalid original hosted input checksum.'
            assert manifest.get(FROZEN_SOURCE) == supplied, 'Frozen input differs from the original hosted submission.'
            for key, record in state['records'].items():
                for name, checksum in record['outputs'].items():
                    assert manifest['reference/' + key + '/' + name] == checksum, 'Recorded output checksum differs.'
            archive.extractall(destination)
        command = ['make', '--no-print-directory', '--silent', 'inside-reproduce']
        comparison = ['make', '--no-print-directory', '--silent', 'inside-compare']
        if job:
            command += ['JOB=' + job]
            comparison += ['JOB=' + job]
        diagnostics = REPORT.setdefault('reproduction_diagnostics', [])
        for stage, argv in (('calculate', command), ('compare', comparison)):
            detail = {'selected_job': job, 'stage': stage, 'bundle_sha256': hashlib.sha256(data).hexdigest()}
            try:
                completed = subprocess.run(argv, cwd=destination, capture_output=True, text=True, timeout=360)
            except subprocess.TimeoutExpired as error:
                # These local children read the public synthetic bundle only;
                # reader capabilities and HTTP credentials are never arguments.
                def tail(value):
                    return (value.decode(errors='replace') if isinstance(value, bytes) else value or '')[-4096:]
                detail.update(returncode=None, timed_out=True,
                              stdout=tail(error.stdout), stderr=tail(error.stderr))
                diagnostics.append(detail)
                raise RuntimeError(f'Fresh native bundle {stage} timed out.') from None
            detail.update(returncode=completed.returncode, timed_out=False,
                          stdout=completed.stdout[-4096:], stderr=completed.stderr[-4096:])
            diagnostics.append(detail)
            assert completed.returncode == 0, f'Fresh native bundle {stage} failed (exit {completed.returncode}); see reproduction diagnostics.'
        return {'bundle_sha256': hashlib.sha256(data).hexdigest(),
                'checksummed_files': len(manifest), 'source_files_match_checkout': True,
                'frozen_input_matches_original_submission': True,
                'native_outputs_compared': 1 if job else len(state['records']),
                'selected_job': job, 'result': 'passed'}


def isolation(owner, other):
    own = request('/state', session=owner)
    assert own['state'] and own['state']['records'], 'Owner cannot read its own completed state.'
    own_other = request('/state', session=other)
    assert own_other['state'] and own_other['state']['records'], 'Second reader cannot read its own completed state.'
    request('/output?job=cpue_a', session=owner)
    request('/bundle', session=owner)
    denied = {}
    for path in ('/state', '/output?job=cpue_a', '/bundle'):
        try:
            request(path, session=other, target_session=owner['id'])
        except APIError as error:
            assert error.status == 403 and error.code == 'session_denied', 'Cross-reader request failed without an explicit access denial.'
            denied[path.split('?')[0]] = error.status
        else:
            raise AssertionError('Cross-reader access was allowed.')
    return {'own_state_output_bundle': 'passed', 'second_reader_own_state': 'passed',
            'cross_reader_denials': denied, 'result': 'passed'}


def main():
    assert RBridge.require_container() == IMAGE, 'Checker requires the actual declared calculation container.'
    assert CONFIG['repository'] == REPOSITORY, 'Local configuration has the wrong repository.'
    assert urllib.parse.urlsplit(BASE).scheme == 'https', 'Hosted endpoint must use HTTPS.'
    if EXPECTED_COMMIT:
        assert re.fullmatch(r'[a-f0-9]{40}', EXPECTED_COMMIT), 'Invalid expected source commit.'
    info = request('/info')
    assert info.get('configured') is True, 'Hosted execution is not configured.'
    assert info.get('repository') == CONFIG['repository'], 'Hosted endpoint points to a different repository.'
    REPORT['service_info_repository_verified'] = True
    session = reader('test-reader.json')
    full = execute(session, 'submission', list(SPEC), 'manual', expected_boundaries=['data', 'cpue', 'assessment'])
    partial = execute(session, 'cpue_summary', ['cpue_summary', 'cpue_report'], previous=full, expected_boundaries=[])
    prepare_jobs = ['prepare_a', 'assessment_a1', 'assessment_a2', 'assessment_summary', 'assessment_report',
                    'mse_prepare', 'mse_constant', 'mse_index', 'mse_buffered', 'mse_summary', 'mse_report']
    prepared = execute(session, 'prepare_a', prepare_jobs, previous=partial, expected_boundaries=[])
    SETTINGS['min_hooks_a'] = 1200
    changed_jobs = ['cpue_a', 'cpue_summary', 'cpue_report', *prepare_jobs]
    changed = execute(session, 'cpue_a', changed_jobs, 'manual', prepared, ['cpue', 'assessment'])
    SETTINGS['mse_buffer'] = .6
    buffered = execute(session, 'mse_report', ['mse_buffered', 'mse_summary', 'mse_report'],
                       previous=changed, expected_boundaries=[])
    assert buffered['records']['mse_buffered']['settings'] == {'buffer': .6}, 'Changed MSE buffer was not used.'
    REPORT['workflow_bundle'] = reproduce(session, buffered)
    other = reader('test-reader-job.json')
    job_inputs = ['submission', 'qc', 'database', 'extract', 'cpue_a']
    selected = execute(other, 'cpue_a', job_inputs, scope='job', expected_boundaries=[])
    assert selected['retained'] == [], 'Fresh selected job retained unexpected results.'
    REPORT['selected_job_bundle'] = reproduce(other, selected, job='cpue_a')
    REPORT['session_isolation'] = isolation(session, other)
    REPORT['runtime'] = {**RBridge().software(), 'python': platform.python_version(),
                         'platform': sys.platform, 'sqlite': sqlite3.sqlite_version}
    REPORT['status'] = 'passed'
    print('PASS: real hosted execution, selected-job inputs, retained identities, bundle reproduction and reader isolation.', flush=True)


if __name__ == '__main__':
    try:
        main()
    except Exception as error:
        REPORT['status'] = 'failed'
        REPORT['error'] = str(error)
        print('FAIL:', str(error), flush=True)
        raise SystemExit(1)
    finally:
        destination = ROOT / '.test-output/online-checks.json'
        destination.parent.mkdir(exist_ok=True)
        destination.write_text(json.dumps(REPORT, indent=2) + '\n')
