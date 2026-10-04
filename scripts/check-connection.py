"""Check live connection recovery, saved fallback and unresolved-run identity."""
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import re
from threading import Thread
from urllib.parse import urlsplit

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[1]
REPOSITORY = json.loads((ROOT / "cloud/config.json").read_text())["repository"]


def preview():
    """Use current UI sources with the last generated container-result payload."""
    saved = (ROOT/'docs/index.html').read_text()
    payload = re.search(r'<script id="demo-payload" type="application/json">(.*?)</script>', saved, re.S).group(1)
    html = (ROOT/'app/index.html').read_text()
    for key, source in {
        'PAYLOAD': payload,
        'CSS': (ROOT/'app/style.css').read_text(),
        'APP': '\n'.join((ROOT/'app'/name).read_text()
                         for name in ['cloud.js', 'lineage.js', 'app.js', 'record.js']),
    }.items():
        html = html.replace('/*__' + key + '__*/', source)
    return html


class QuietHandler(SimpleHTTPRequestHandler):
    def log_message(self, *_):
        pass


server = ThreadingHTTPServer(('127.0.0.1', 0), partial(QuietHandler, directory=ROOT/'docs'))
Thread(target=server.serve_forever, daemon=True).start()
try:
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)

        # One shared deadline and one session request, including rapid mode changes.
        unit = browser.new_page()
        unit.clock.install()
        unit.add_script_tag(content=(ROOT/'app/cloud.js').read_text())
        unit.evaluate("""() => {
          window.calls = [];
          window.fetch = (url, options) => {
            calls.push({url, headers: options.headers});
            return new Promise((resolve, reject) => {
              options.signal.addEventListener('abort', () =>
                reject(new DOMException('Aborted', 'AbortError')));
            });
          };
          window.cloud = new CloudRun({url: 'https://example.test', repository: 'test/repo'}, [], () => {}, () => {});
          const first = cloud.initialise(), second = cloud.initialise();
          window.sameAttempt = first === second;
          window.attempt = first.catch(error => { window.failure = error.message; });
        }""")
        assert unit.evaluate('sameAttempt && calls.length === 1')
        unit.clock.fast_forward(8001)
        unit.wait_for_function("window.failure?.includes('8 seconds')")
        unit.evaluate("""async () => {
          calls.length = 0;
          window.fetch = async (url, options) => {
            calls.push({url, headers: options.headers});
            return new Response(JSON.stringify(url.endsWith('/info')
              ? {configured: true, repository: 'test/repo'} : {id: 'test-session', token: 'test-token'}));
          };
          await cloud.initialise();
        }""")
        assert unit.evaluate("calls.length === 2 && !calls[0].headers['Content-Type']")
        assert unit.evaluate("cloud.session.id === 'test-session'")

        # A gateway for another edition must not create a reader session.
        unit.evaluate("""async () => {
          calls.length = 0;
          cloud.session = null;
          window.fetch = async (url, options) => {
            calls.push({url, headers: options.headers});
            return Response.json({configured: true, repository: 'other/repo'});
          };
          window.mismatch = await cloud.initialise()
            .then(() => false, error => error.message.includes('being updated'));
        }""")
        assert unit.evaluate("mismatch && calls.length === 1 && cloud.session === null")
        unit.evaluate("cloud.session = {id: 'test-session', token: 'test-token'}")

        # Once a run is acknowledged, expiry or denial must never replay it.
        for status, code in [(410, 'session_expired'), (403, 'session_denied')]:
            unit.evaluate("""async ({status, code}) => {
              calls.length = 0;
              cloud.session = {id: 'test-session', token: 'test-token'};
              window.fetch = async (url, options) => {
                calls.push({url, headers: options.headers});
                return url.includes('/run?')
                  ? Response.json({id: 'accepted'})
                  : Response.json({code, error: 'Unavailable'}, {status});
              };
              window.expired = await cloud.call('run', {start: 'submission', settings: {}})
                .then(() => false, error => error.sessionUnavailable);
            }""", {'status': status, 'code': code})
            assert unit.evaluate("expired && calls.length === 2 && cloud.session === null")

        # Start afresh can discard a denied capability and create a new own session.
        unit.evaluate("""async () => {
          calls.length = 0;
          cloud.session = {id: 'denied', token: 'wrong-token'};
          cloud.records = {old: {}};
          window.fetch = async url => {
            calls.push(url);
            return url.includes('/reset?')
              ? Response.json({code: 'session_denied', error: 'Denied'}, {status: 403})
              : Response.json({id: 'replacement', token: 'new-token'});
          };
          await cloud.call('reset');
        }""")
        assert unit.evaluate("calls.length === 2 && cloud.session.id === 'replacement' && Object.keys(cloud.records).length === 0")

        # Other forbidden responses must not silently discard or renew a capability.
        unit.evaluate("""async () => {
          calls.length = 0;
          window.fetch = async url => {
            calls.push(url);
            return Response.json({code: 'permission_denied', error: 'Forbidden'}, {status: 403});
          };
          window.forbidden = await cloud.call('reset')
            .then(() => false, error => !error.sessionUnavailable);
        }""")
        assert unit.evaluate("forbidden && calls.length === 1 && cloud.session.id === 'replacement'")

        # A lost or malformed dispatch response has an unknown outcome. Do not
        # silently create a replacement session or send another dispatch.
        for failure in ["throw new TypeError('Lost response')", "return new Response('{')"]:
            unit.evaluate("""async failure => {
              calls.length = 0;
              cloud.session = {id: 'current', token: 'token'};
              window.fetch = async url => { calls.push(url); return new Function(failure)(); };
              window.unknown = await cloud.call('run', {start: 'submission', settings: {}})
                .then(() => false, error => error.executionUnknown);
            }""", failure)
            assert unit.evaluate("unknown && calls.length === 1 && cloud.session.id === 'current'")
        # Support the already deployed expiry response, but never repeat a lost
        # dispatch response from the replacement session.
        unit.evaluate("""async () => {
          calls.length = 0;
          cloud.session = {id: 'old', token: 'old'};
          window.fetch = async url => {
            calls.push(url);
            if (url.includes('/run?session=old')) return Response.json({
              error: 'This demonstration session is unavailable. Select Start afresh.'
            }, {status: 400});
            if (url.endsWith('/info')) return Response.json({configured: true, repository: 'test/repo'});
            if (url.endsWith('/session')) return Response.json({id: 'replacement', token: 'new'});
            throw new TypeError('Lost replacement response');
          };
          window.unknown = await cloud.call('run', {start: 'submission', settings: {}})
            .then(() => false, error => error.executionUnknown);
        }""")
        assert unit.evaluate("unknown && calls.length === 4 && cloud.session.id === 'replacement'")
        # An acknowledged run with a missing/mismatched state is unresolved,
        # rather than an invitation to send another calculation request.
        unit.evaluate("""async () => {
          calls.length = 0;
          cloud.session = {id: 'known-session', token: 'known-token'};
          window.fetch = async url => {
            calls.push(url);
            return url.includes('/run?') ? Response.json({id: 'known-run'})
              : Response.json({run: null, events: []});
          };
          window.unknown = await cloud.call('run', {start: 'submission', settings: {}})
            .then(() => false, error => error.executionUnknown);
        }""")
        assert unit.evaluate("unknown && calls.length === 2 && cloud.session.id === 'known-session'")
        unit.close()

        state = {'available': True, 'runtime_requests': 0}
        context = browser.new_context(viewport={'width': 1440, 'height': 1000})
        page = context.new_page()
        errors = []
        page.on('pageerror', lambda error: errors.append(str(error)))

        def service(route):
            if not state['available']:
                route.fulfill(status=503, content_type='application/json',
                              body=json.dumps({'error': 'The live service is unavailable.'}))
            else:
                value = ({'configured': True, 'repository': REPOSITORY} if urlsplit(route.request.url).path.endswith('/info')
                         else {'id': 'test-session', 'token': 'test-token'})
                route.fulfill(content_type='application/json', body=json.dumps(value))

        def runtime(route):
            state['runtime_requests'] += 1
            route.abort()

        page.route('**/functions/v1/paper-api/**', service)
        page.route('**/runtime-*.json', runtime)
        page.route('**/index.html', lambda route: route.fulfill(content_type='text/html', body=preview()))
        page.goto(f'http://127.0.0.1:{server.server_port}/index.html')
        page.locator('#run:enabled').wait_for()
        assert state['runtime_requests'] == 0
        assert page.locator('#mode').input_value() == 'cloud'
        assert page.locator('#offline-download').is_visible()
        assert page.locator('#offline-download').get_attribute('href') == 'offline.html'
        assert page.locator('#mode-notice').is_hidden()

        # A ten-minute cleanup is simulated by rejecting the old credential.
        # No real runner is dispatched and no wall-clock retention wait is needed.
        expiry = {'expired': True, 'renewal_failure': False, 'sessions': 0,
                  'accepted': 0, 'bodies': [], 'snapshots': []}
        fixture = page.evaluate("""() => {
          records = structuredClone(payload.saved.records);
          cloud.records = records;
          states = Object.fromEntries(jobs.map(job => [job.key, 'complete']));
          completedRun = {run: jobs.map(job => job.key), retained: []};
          latestRun = 'expired-run';
          return {records: structuredClone(records), keys: jobs.map(job => job.key)};
        }""")
        page.locator('#mse-buffer').select_option('0.6')
        page.locator('#handover').select_option('manual')
        page.evaluate("selectJob('mse_buffered')")
        page.wait_for_function('plan.run.length === 3 && plan.retained.length === 19')

        def expiring_service(route):
            path = urlsplit(route.request.url).path.rsplit('/', 1)[-1]
            code = 200
            if path == 'info':
                code = 503 if expiry['renewal_failure'] else 200
                value = {'error': 'Unavailable'} if code == 503 else {'configured': True, 'repository': REPOSITORY}
            elif path == 'session':
                expiry['snapshots'].append(page.evaluate("""() => ({
                  records: Object.keys(records).length,
                  cloudRecords: Object.keys(cloud.records).length,
                  plan, selected, settings: settings(), busy,
                  runId: $('run-id').textContent, executionHidden: $('github-run').hidden,
                  downloadDisabled: $('download').disabled, completedRun
                })"""))
                expiry['sessions'] += 1
                expiry['expired'] = False
                value = {'id': 'renewed-' + str(expiry['sessions']), 'token': 'new-token'}
            elif path == 'run':
                expiry['bodies'].append(route.request.post_data_json)
                if expiry['expired']:
                    code = 410
                    value = {'code': 'session_expired', 'error': 'Temporary results expired'}
                else:
                    expiry['accepted'] += 1
                    value = {'id': 'fresh-request'}
            elif path == 'state':
                result_records = json.loads(json.dumps(fixture['records']))
                for record in result_records.values():
                    record['run_id'] = 'fresh-run'
                result_records['mse_buffered']['settings']['buffer'] = 0.6
                result = {'run_id': 'fresh-run', 'run': fixture['keys'], 'retained': [],
                          'records': result_records}
                value = {'run': {'id': 'fresh-request', 'status': 'complete', 'result': result},
                         'state': {'records': result_records},
                         'events': [{'id': 1, 'event': {
                             'state': 'plan', 'start': 'mse_buffered', 'changed': fixture['keys'],
                             'run': fixture['keys'], 'retained': [], 'run_id': 'fresh-run'}}]}
            else:
                raise AssertionError('Unexpected expiry route: ' + path)
            route.fulfill(status=code, content_type='application/json', body=json.dumps(value))

        page.route('**/functions/v1/paper-api/**', expiring_service)
        page.evaluate("() => { $('run').click(); $('run').click(); }")
        page.wait_for_function("$('status-title').textContent === 'Results are ready'")
        assert expiry['sessions'] == 1 and expiry['accepted'] == 1
        assert len(expiry['bodies']) == 2 and expiry['bodies'][0] == expiry['bodies'][1]
        assert expiry['bodies'][1]['start'] == 'mse_buffered'
        assert expiry['bodies'][1]['settings']['mse_buffer'] == 0.6
        assert expiry['bodies'][1]['handover'] == 'manual'
        snapshot = expiry['snapshots'][0]
        assert snapshot['records'] == snapshot['cloudRecords'] == 0
        assert snapshot['plan']['run'] == fixture['keys'] and snapshot['plan']['retained'] == []
        assert snapshot['selected'] == 'mse_buffered' and snapshot['settings']['mse_buffer'] == 0.6
        assert snapshot['busy'] and snapshot['downloadDisabled'] and snapshot['executionHidden']
        assert snapshot['runId'] == '' and snapshot['completedRun'] is None
        assert page.evaluate("!busy && !dispatchPending && completedRun.retained.length === 0")
        assert page.evaluate("Object.values(records).every(record => record.run_id === 'fresh-run')")
        assert page.locator('#run').is_enabled()

        # Failure to renew clears the busy state, and an explicit retry keeps the
        # same chosen analysis while starting just one accepted run.
        expiry['expired'] = True
        expiry['renewal_failure'] = True
        page.locator('#run').click()
        page.wait_for_function("$('status-title').textContent === 'The analysis stopped'")
        assert page.evaluate("!busy && !dispatchPending && cloud.session === null && Object.keys(records).length === 0")
        assert page.locator('#run').is_enabled()
        assert page.evaluate("selected === 'mse_buffered' && settings().mse_buffer === 0.6")
        assert expiry['accepted'] == 1
        expiry['renewal_failure'] = False
        page.locator('#run').click()
        page.wait_for_function("$('status-title').textContent === 'Results are ready'")
        assert expiry['sessions'] == 2 and expiry['accepted'] == 2
        assert expiry['bodies'][-1] == expiry['bodies'][0]
        page.unroute('**/functions/v1/paper-api/**', expiring_service)
        # Leave the original connection scenarios with their original empty state.
        page.evaluate("""() => {
          records = {}; cloud.records = {}; states = {}; completedRun = null;
          latestRun = ''; $('mse-buffer').value = '0.8'; render();
        }""")

        # Unavailable Live falls back to the saved container results. The chosen
        # Live settings, handover and starting job survive a later reconnect.
        state['available'] = False
        page.locator('#snapshot').select_option('2024')
        page.locator('#filter').select_option('1200')
        page.locator('#handover').select_option('manual')
        page.locator('.job[data-job="cpue_a"]').click()
        page.evaluate("() => { cloudReady = false; return activateMode('cloud'); }")
        page.wait_for_function("mode === 'saved'")
        assert page.locator('#mode-notice').is_visible()
        assert 'No new analysis has started' in page.locator('#mode-notice').inner_text()
        assert page.locator('#status-title').inner_text() == 'Saved results'
        assert page.evaluate("selected === 'cpue_a' && Object.keys(records).length === 22 && !busy")
        assert page.locator('#run').is_hidden()
        assert page.locator('#mode option').count() == 2
        assert state['runtime_requests'] == 0
        page.locator('#dismiss-mode-notice').click()
        page.evaluate('render()')
        assert page.locator('#mode-notice').is_hidden()
        state['available'] = True
        page.locator('#mode').select_option('cloud')
        page.locator('#run:enabled').wait_for()
        assert page.locator('#snapshot').input_value() == '2024'
        assert page.locator('#filter').input_value() == '1200'
        assert page.locator('#handover').input_value() == 'manual'
        assert page.evaluate("selected === 'cpue_a'")

        # Status loss must keep the original capability, acknowledged run and
        # execution link. Switching to Saved and back never unlocks another run.
        page.evaluate("""() => {
          window.originalRequest = cloud.request.bind(cloud);
          window.dispatchCount = 0;
          window.originalSession = structuredClone(cloud.session);
          cloud.request = async (path, ...args) => {
            if (path === '/run') {
              dispatchCount++;
              cloud.run = {id: 'dispatched', github_run: 12345, status: 'running'};
              cloud.onPhase(null, null, 12345);
              return {id: 'dispatched'};
            }
            if (path.startsWith('/state')) throw new TypeError('Failed to fetch');
            return originalRequest(path, ...args);
          };
        }""")
        page.locator('#run').click()
        page.wait_for_function("document.querySelector('#status-title').textContent === 'Live run status unavailable'")
        assert page.locator('#run').is_disabled()
        assert page.locator('#reset').is_disabled()
        assert page.evaluate('dispatchCount === 1 && !busy && unresolvedLive')
        assert page.evaluate('JSON.stringify(cloud.session) === JSON.stringify(originalSession) && cloud.run.id === "dispatched"')
        assert page.locator('#github-run').get_attribute('href').endswith('/actions/runs/12345')
        page.locator('#saved-fallback').click()
        assert page.locator('#run').is_hidden()
        page.locator('#mode').select_option('cloud')
        assert page.locator('#status-title').inner_text() == 'Live run status unavailable'
        assert page.locator('#run').is_disabled() and page.locator('#reset').is_disabled()
        assert page.locator('#github-run').is_visible()
        assert page.evaluate('dispatchCount === 1 && cloud.run.id === "dispatched" && !ready')
        assert state['runtime_requests'] == 0
        assert not errors, errors
        context.close()

        # Late connection results never overwrite an explicitly selected Saved
        # view. No run is sent in either the success or failure race.
        for success in (False, True):
            race = browser.new_context(viewport={'width': 390, 'height': 844})
            race_page = race.new_page()
            race_errors, pending_info, race_runs = [], [], []
            race_page.on('pageerror', lambda error: race_errors.append(str(error)))
            race_page.route('**/index.html', lambda route: route.fulfill(content_type='text/html', body=preview()))
            def held_service(route):
                if route.request.url.endswith('/info'):
                    pending_info.append(route)
                elif '/run?' in route.request.url:
                    race_runs.append(route.request.url)
                    route.abort()
                else:
                    route.fulfill(content_type='application/json', body=json.dumps({'id': 'late-session', 'token': 'test-token'}))
            race_page.route('**/functions/v1/paper-api/**', held_service)
            race_page.goto(f'http://127.0.0.1:{server.server_port}/index.html')
            race_page.wait_for_function("$('mode').value === 'cloud'")
            assert pending_info
            race_page.locator('#mode').select_option('saved')
            value = {'configured': True, 'repository': REPOSITORY} if success else {'error': 'Unavailable'}
            pending_info.pop().fulfill(status=200 if success else 503, content_type='application/json', body=json.dumps(value))
            race_page.wait_for_timeout(100)
            assert race_page.locator('#mode').input_value() == 'saved'
            assert race_page.locator('#mode-notice').is_hidden()
            assert race_page.evaluate('!busy && Object.keys(records).length === 22')
            assert race_page.evaluate('document.documentElement.scrollWidth <= innerWidth')
            assert not race_runs and not race_errors
            race.close()
        browser.close()
    print('PASS: bounded Live connection, capability expiry/renewal and missing-input rebuild, '
          'saved-result fallback, preserved Live context, no dispatch replay, unresolved identity '
          'locked across modes, late-response races and mobile layout. No browser model execution.')
finally:
    server.shutdown()
    server.server_close()
