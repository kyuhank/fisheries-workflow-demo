"""Exercise handover identity and browser races without hosted dispatch or models.

Current UI sources are assembled with preserved payloads, so a pending native
report build does not make these interaction checks test old JavaScript.
"""
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import re
from urllib.parse import parse_qs, urlsplit

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[1]
ARTIFACT = ROOT / '.test-output/check-handover.json'
URL = 'https://ui.example.test/demo'
REQUEST_ID = '12345678-1234-4234-9234-123456789abc'


def preview():
    saved = (ROOT / 'docs/index.html').read_text()
    raw = re.search(r'<script id="demo-payload" type="application/json">(.*?)</script>',
                    saved, re.S).group(1)
    fixture = json.loads(raw)
    html = (ROOT / 'app/index.html').read_text()
    for key, source in {
        'PAYLOAD': raw,
        'CSS': (ROOT / 'app/style.css').read_text(),
        'APP': '\n'.join((ROOT / 'app' / name).read_text()
                         for name in ['cloud.js', 'lineage.js', 'app.js', 'record.js']),
        'WORKER': '',
    }.items():
        html = html.replace('/*__' + key + '__*/', source)
    return html, fixture


class HandoverCloud:
    """HTTP fixture implementing the owned-run/count compare-and-set contract."""

    def __init__(self, fixture, case='normal'):
        self.fixture = fixture
        self.case = case
        self.records = {}
        self.dispatches = []
        self.confirmations = []
        self.events = []
        self.held = []
        self.active = 0
        self.connected = False
        self.failed = False
        self.unknown = False
        self.visibility_limit = None
        self.boundaries = []

    def emit(self, event):
        self.events.append({'id': len(self.events) + 1, 'event': event})

    def current(self):
        return self.boundaries[self.active] if self.active < len(self.boundaries) else None

    def publish_boundary(self):
        if self.current() and not self.connected:
            self.emit({**self.current(), 'state': 'handover',
                       'request_id': REQUEST_ID, 'transfer_count': self.active,
                       'message': 'Simulated file transfer'})

    def advance(self, connect):
        self.emit({**self.current(), 'state': 'received', 'message': 'Simulated receipt'})
        self.active += 1
        self.connected = connect
        self.publish_boundary()

    def acknowledgement(self, replay=False):
        return {'ok': True, 'connected': self.connected,
                'transfer_count': self.active, 'replay': replay}

    def start(self, route):
        data = route.request.post_data_json
        self.dispatches.append(data)
        self.plan = route.request.frame.evaluate(
            '(data) => cloud.plan(data.start, data.settings, data.scope)', data)
        active = self.plan['run']
        handovers = json.loads((ROOT / 'workflow/jobs.json').read_text())['handovers']
        for boundary, recipients in handovers.items():
            group = [key for key, parents in recipients.items()
                     if key in active and any(parent in active for parent in parents)]
            if group:
                self.boundaries.append({'boundary': boundary, 'group': group, 'job': group[0]})
        self.connected = data['handover'] == 'connected'
        self.emit({'state': 'plan', **self.plan, 'run_id': 'Mock 001'})
        self.publish_boundary()
        updated = deepcopy(self.records)
        for job in self.fixture['jobs']:
            key = job['key']
            if key not in active:
                continue
            record = deepcopy(self.fixture['saved']['records'][key])
            record['run_id'] = 'Mock 001'
            record['outputs']['output.json'] = hashlib.sha256(('Mock 001:' + key).encode()).hexdigest()
            record['inputs'] = {parent: {'run_id': updated[parent]['run_id'],
                'checksum': updated[parent]['outputs']['output.json']} for parent in job['parents']}
            if key == 'submission':
                record['settings']['last_year'] = data['settings']['last_year']
            elif key == 'cpue_a':
                record['settings']['min_hooks'] = data['settings']['min_hooks_a']
            elif key in ('assessment_a2', 'assessment_b2'):
                record['settings']['r'] = data['settings']['growth_rate_2']
            elif key == 'mse_buffered':
                record['settings']['buffer'] = data['settings']['mse_buffer']
            updated[key] = record
        self.result = {**self.plan, 'run_id': 'Mock 001', 'records': updated}
        return {'id': REQUEST_ID}

    def release(self, index, failed=False):
        route, value = self.held[index]
        route.fulfill(status=503 if failed else 200, content_type='application/json',
                      body=json.dumps({'error': 'Delayed transfer response failed'} if failed else value))

    def route(self, route):
        parsed = urlsplit(route.request.url)
        path = parsed.path.rsplit('/', 1)[-1]
        status = 200
        if path == 'info':
            value = {'configured': True, **{key: self.fixture['cloud'][key]
                     for key in ['repository', 'data_kind', 'source_sha256']}}
        elif path == 'session':
            value = {'id': 'mock-session', 'token': 'mock-token'}
        elif path == 'run':
            value = self.start(route)
        elif path == 'state':
            if self.unknown:
                status, value = 503, {'error': 'Simulated status connection failure'}
            else:
                cursor = int(parse_qs(parsed.query)['after'][0])
                events = self.events[:self.visibility_limit] if self.visibility_limit else self.events
                terminal = self.connected or self.active == len(self.boundaries)
                value = {'run': {'id': REQUEST_ID,
                         'status': 'failed' if self.failed else 'complete' if terminal else 'handover',
                         'connected': self.connected, 'transfer_count': self.active,
                         'result': self.result,
                         'error': 'File transfer was not acknowledged within three minutes.' if self.failed else None},
                         'events': [event for event in events if event['id'] > cursor],
                         'state': {'records': self.records}}
        elif path == 'transfer':
            body = route.request.post_data_json
            before = self.active
            entry = {'body': body, 'count_before': before,
                     'server_boundary': self.current()['boundary'] if self.current() else None}
            self.confirmations.append(entry)
            if body['request_id'] != REQUEST_ID:
                status, value = 409, {'error': 'The transfer does not belong to this run.'}
            elif body['transfer_count'] < self.active:
                self.visibility_limit = None
                value = self.acknowledgement(replay=True)
            elif body['transfer_count'] != self.active or not self.current() or self.failed:
                status, value = 409, {'error': 'This transfer is no longer awaiting confirmation.'}
            elif self.case == 'before-failure' and len(self.confirmations) == 1:
                status, value = 503, {'error': 'Transient failure before commit'}
            elif self.case == 'late-boundary-error' and len(self.confirmations) == 2:
                self.held.append((route, None))
                entry['count_after'] = self.active
                return
            else:
                previous_visible = len(self.events)
                self.advance(body['connect'])
                value = self.acknowledgement()
                if self.case in ('lost-response', 'lost-response-connect-replay') and len(self.confirmations) == 1:
                    self.visibility_limit = previous_visible
                    status, value = 503, {'error': 'Response lost after committed transfer'}
                elif self.case in ('late-boundary-error', 'late-mode-error', 'late-mode-success') and len(self.confirmations) == 1:
                    self.held.append((route, value))
                    entry['count_after'] = self.active
                    return
            entry.update(count_after=self.active, replay=value.get('replay', False), status=status)
        else:
            raise AssertionError('Unexpected fixture endpoint: ' + path)
        route.fulfill(status=status, content_type='application/json', body=json.dumps(value))


def open_case(browser, html, fixture, case='normal', seed=False):
    page = browser.new_page(viewport={'width': 1440, 'height': 1000})
    mock = HandoverCloud(fixture, case)
    errors = []
    page.on('pageerror', lambda error: errors.append(str(error)))
    page.route('https://**/*', lambda route: route.abort())
    page.route('**/functions/v1/paper-api/**', mock.route)
    page.route(URL, lambda route: route.fulfill(content_type='text/html', body=html))
    page.goto(URL)
    page.wait_for_function("mode === 'cloud' && ready")
    if seed:
        mock.records = deepcopy(fixture['saved']['records'])
        page.evaluate("""async saved => {
          cloud.records = structuredClone(saved); records = structuredClone(saved);
          states = {}; await refreshPlan();
        }""", mock.records)
    return page, mock, errors


def wait_boundary(page, boundary):
    page.wait_for_function('boundary => waitingTransfer?.boundary === boundary', arg=boundary)
    assert page.locator('#handover-panel').is_visible()
    assert page.locator('#handover').is_disabled()


def finished(page):
    page.wait_for_function("!busy && $('status-title').textContent === 'Results are ready'")
    assert page.locator('#handover-panel').is_hidden()
    assert page.evaluate('waitingTransfer === null && !confirmingTransfer')


def remaining(page, mock):
    while mock.current() and not mock.connected:
        wait_boundary(page, mock.current()['boundary'])
        count = mock.active
        page.locator('#transfer-files').click()
        page.wait_for_function('count => cloud.run?.transfer_count > count', arg=count)
    finished(page)


def close(page, mock, errors, results, case, **evidence):
    assert not errors, errors
    assert len(mock.dispatches) == 1, mock.dispatches
    results.append({'case': case, 'dispatches': mock.dispatches,
                    'confirmations': mock.confirmations, **evidence})
    page.close()


def main():
    html, fixture = preview()
    results = []
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        for case, connect_at in [('manual-three-boundaries', None), ('connect-data', 0),
                                 ('connect-cpue', 1), ('connect-assessment', 2)]:
            page, mock, errors = open_case(browser, html, fixture)
            page.locator('#handover').select_option('manual')
            page.locator('#run').click()
            for index, boundary in enumerate(['data', 'cpue', 'assessment']):
                wait_boundary(page, boundary)
                page.locator('#connect-workflow' if index == connect_at else '#transfer-files').click()
                if index == connect_at:
                    break
            finished(page)
            expected = 3 if connect_at is None else connect_at + 1
            assert [row['body']['transfer_count'] for row in mock.confirmations] == list(range(expected))
            assert all(row['body']['request_id'] == REQUEST_ID for row in mock.confirmations)
            assert page.locator('#handover').input_value() == ('manual' if connect_at is None else 'connected')
            close(page, mock, errors, results, case, complete=True)

        page, mock, errors = open_case(browser, html, fixture)
        page.locator('#run').click()
        finished(page)
        malformed_refused = page.evaluate("""async request_id => {
          const invalid = [
            {connect: false},
            {connect: false, request_id, transfer_count: -1},
            {connect: false, request_id, transfer_count: 0.5},
            {connect: 'false', request_id, transfer_count: 0},
            {connect: false, request_id: 'missing-run', transfer_count: 0},
          ];
          for (const body of invalid) {
            try { await cloud.call('transfer', body); return false; }
            catch (error) { if (!error.message.includes('boundary identity')) return false; }
          }
          return true;
        }""", REQUEST_ID)
        assert malformed_refused
        assert not mock.confirmations
        close(page, mock, errors, results, 'automatic', complete=True, malformed_transfers_refused=True)

        page, mock, errors = open_case(browser, html, fixture)
        page.locator('#handover').select_option('manual')
        page.evaluate("() => { runFromJob('cpue_a', 'job'); }")
        wait_boundary(page, 'data')
        assert page.evaluate('waitingTransfer.group') == ['cpue_a']
        page.locator('#transfer-files').click()
        finished(page)
        assert mock.result['run'] == ['submission', 'qc', 'database', 'extract', 'cpue_a']
        assert len(mock.confirmations) == 1
        close(page, mock, errors, results, 'single-job-missing-inputs', complete=True)

        page, mock, errors = open_case(browser, html, fixture, seed=True)
        before = deepcopy(mock.records)
        page.locator('#handover').select_option('manual')
        page.evaluate("() => { runFromJob('cpue_report', 'job'); }")
        finished(page)
        assert mock.result['run'] == ['cpue_report'] and not mock.confirmations
        assert all(mock.result['records'][key] == value for key, value in before.items() if key != 'cpue_report')
        close(page, mock, errors, results, 'single-job-retained-inputs', complete=True)

        page, mock, errors = open_case(browser, html, fixture, seed=True)
        before = deepcopy(mock.records)
        page.locator('#handover').select_option('manual')
        page.locator('#growth-rate').select_option('0.35')
        page.wait_for_function("plan?.changed.includes('assessment_a2') && plan?.changed.includes('assessment_b2')")
        page.locator('#run').click()
        wait_boundary(page, 'assessment')
        page.locator('#transfer-files').click()
        finished(page)
        assert [row['server_boundary'] for row in mock.confirmations] == ['assessment']
        assert all(mock.result['records'][key] == value for key, value in before.items()
                   if key not in mock.result['run'])
        close(page, mock, errors, results, 'partial-growth-update', complete=True)

        for case in ['before-failure', 'lost-response', 'lost-response-connect-replay']:
            page, mock, errors = open_case(browser, html, fixture, case)
            page.locator('#handover').select_option('manual')
            page.locator('#run').click()
            wait_boundary(page, 'data')
            page.locator('#transfer-files').click()
            page.wait_for_function("$('status-title').textContent === 'Transfer not confirmed'")
            assert page.evaluate("waitingTransfer.boundary === 'data' && !confirmingTransfer")
            before = mock.active
            page.locator('#connect-workflow' if case.endswith('connect-replay') else '#transfer-files').click()
            wait_boundary(page, 'cpue')
            assert [row['body']['transfer_count'] for row in mock.confirmations[:2]] == [0, 0]
            if case.startswith('lost-response'):
                assert mock.active == before == 1
                assert mock.confirmations[1]['replay'] is True
                assert mock.confirmations[1]['count_before'] == mock.confirmations[1]['count_after']
                assert page.locator('#handover').input_value() == 'manual'
            remaining(page, mock)
            close(page, mock, errors, results, case, complete=True, retry_same_boundary=True)

        page, mock, errors = open_case(browser, html, fixture, 'late-boundary-error')
        page.locator('#handover').select_option('manual')
        page.locator('#run').click()
        wait_boundary(page, 'data')
        page.locator('#transfer-files').click()
        wait_boundary(page, 'cpue')
        page.locator('#transfer-files').click()
        page.wait_for_function('confirmingTransfer')
        page.wait_for_timeout(50)
        assert len(mock.held) == 2
        title = page.locator('#status-title').inner_text()
        mock.release(0, failed=True)
        page.wait_for_timeout(100)
        assert page.evaluate("waitingTransfer.boundary === 'cpue' && confirmingTransfer")
        assert page.locator('#status-title').inner_text() == title
        mock.advance(False)
        route, _ = mock.held[1]
        route.fulfill(content_type='application/json', body=json.dumps(mock.acknowledgement()))
        wait_boundary(page, 'assessment')
        remaining(page, mock)
        close(page, mock, errors, results, 'late-error-new-boundary', complete=True,
              newer_confirmation_preserved=True)

        for case in ['late-mode-error', 'late-mode-success']:
            page, mock, errors = open_case(browser, html, fixture, case)
            page.locator('#handover').select_option('manual')
            page.locator('#run').click()
            wait_boundary(page, 'data')
            page.locator('#connect-workflow').click()
            finished(page)
            assert len(mock.held) == 1
            page.evaluate("""async () => {
              await activateMode('saved');
              $('handover').value = 'manual';
              status('', 'Saved marker', 'Inspecting the saved example');
            }""")
            mock.release(0, failed=case.endswith('error'))
            page.wait_for_timeout(100)
            assert page.evaluate("mode === 'saved' && !confirmingTransfer")
            assert page.locator('#handover').input_value() == 'manual'
            assert page.locator('#status-title').inner_text() == 'Saved marker'
            close(page, mock, errors, results, case, saved_mode_preserved=True)

        page, mock, errors = open_case(browser, html, fixture)
        page.locator('#handover').select_option('manual')
        page.locator('#run').click()
        wait_boundary(page, 'data')
        mock.failed = True
        page.wait_for_function("!busy && $('status-title').textContent === 'The analysis stopped'")
        assert page.locator('#handover-panel').is_hidden()
        assert page.evaluate("waitingTransfer === null && states.cpue_a === 'failed' && states.cpue_b === 'failed'")
        assert 'Confirm file transfer' not in page.evaluate('jobProgress(byKey.cpue_a).detail')
        assert page.evaluate("Object.values(states).every(state => !['waiting','running','handover','received'].includes(state))")
        close(page, mock, errors, results, 'terminal-handover-timeout', pending_recipients_failed=True)

        page, mock, errors = open_case(browser, html, fixture)
        page.locator('#handover').select_option('manual')
        page.locator('#run').click()
        wait_boundary(page, 'data')
        mock.unknown = True
        page.wait_for_function("!busy && unresolvedLive && !ready", timeout=15000)
        assert page.locator('#handover-panel').is_hidden() and page.locator('#run').is_disabled()
        assert page.evaluate("states.cpue_a === 'unconfirmed' && waitingTransfer === null")
        refused = page.evaluate("""async () => {
          $('run').onclick();
          try { await call('run', {start: 'submission'}); return false; }
          catch (error) { return error.executionUnknown; }
        }""")
        assert refused and len(mock.dispatches) == 1
        close(page, mock, errors, results, 'status-outcome-unknown', repeat_dispatch_refused=True)

        browser.close()
    ARTIFACT.parent.mkdir(exist_ok=True)
    ARTIFACT.write_text(json.dumps({'ui_sha256': hashlib.sha256(html.encode()).hexdigest(),
        'source_files': ['app/cloud.js', 'app/app.js'], 'cases': results}, indent=2) + '\n')
    print(f'PASS: {len(results)} local HTTP fixture cases; frozen handover retries, three boundaries, '
          'connect/automatic/single-job/update paths, late callbacks, timeout and UNKNOWN dispatch lock. '
          'No hosted execution or model fitting.')


if __name__ == '__main__':
    main()
