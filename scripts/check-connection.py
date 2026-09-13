"""Check live connection recovery and the on-demand offline runtime in a browser."""
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import re
from threading import Thread
from urllib.parse import urlsplit

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[1]


def preview():
    """Use current UI sources with the last generated payload and runtime URL."""
    saved = (ROOT/'docs/index.html').read_text()
    payload = re.search(r'<script id="demo-payload" type="application/json">(.*?)</script>', saved, re.S).group(1)
    html = (ROOT/'app/index.html').read_text()
    for key, source in {
        'PAYLOAD': payload,
        'CSS': (ROOT/'app/style.css').read_text(),
        'WORKER': (ROOT/'app/worker.js').read_text(),
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
          window.cloud = new CloudRun({url: 'https://example.test'}, [], () => {}, () => {});
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
              ? {configured: true} : {id: 'test-session', token: 'test-token'}));
          };
          await cloud.initialise();
        }""")
        assert unit.evaluate("calls.length === 2 && !calls[0].headers['Content-Type']")
        assert unit.evaluate("cloud.session.id === 'test-session'")
        unit.close()

        state = {'available': True, 'runtime_failure': True, 'runtime_requests': 0}
        context = browser.new_context(viewport={'width': 1440, 'height': 1000})
        page = context.new_page()
        errors = []
        page.on('pageerror', lambda error: errors.append(str(error)))

        def service(route):
            if not state['available']:
                route.fulfill(status=503, content_type='application/json',
                              body=json.dumps({'error': 'The live service is unavailable.'}))
            else:
                value = ({'configured': True} if urlsplit(route.request.url).path.endswith('/info')
                         else {'id': 'test-session', 'token': 'test-token'})
                route.fulfill(content_type='application/json', body=json.dumps(value))

        def runtime(route):
            state['runtime_requests'] += 1
            if state['runtime_failure']:
                route.abort()
            else:
                route.continue_()

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

        # A failed reconnect switches mode, preserves chosen settings, and does
        # not claim readiness if the Python download also fails.
        state['available'] = False
        page.locator('#snapshot').select_option('2024')
        page.locator('#filter').select_option('1200')
        page.locator('#handover').select_option('manual')
        page.locator('.job[data-job="cpue_a"]').click()
        page.evaluate("() => { cloudReady = false; return activateMode('cloud'); }")
        page.locator('#retry-connection:visible').wait_for()
        assert page.locator('#mode').input_value() == 'live'
        assert page.locator('#mode-notice').is_visible()
        assert 'could not load' in page.locator('#mode-notice').inner_text()
        assert page.locator('#status-title').inner_text() == 'Offline run could not start'
        assert page.locator('#snapshot').input_value() == '2024'
        assert page.locator('#filter').input_value() == '1200'
        assert page.locator('#handover').input_value() == 'manual'
        assert page.evaluate("selected === 'cpue_a' && Object.keys(records).length === 0 && !busy")
        assert page.locator('#run').is_disabled()
        assert state['runtime_requests'] == 1
        page.set_viewport_size({'width': 390, 'height': 844})
        assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')
        page.locator('#dismiss-mode-notice').click()
        page.evaluate('render()')
        assert page.locator('#mode-notice').is_hidden()
        page.set_viewport_size({'width': 1440, 'height': 1000})
        state['runtime_failure'] = False
        page.evaluate("""() => {
          window.progressMessages = [];
          new MutationObserver(() => progressMessages.push(
            document.querySelector('#status-message').textContent))
            .observe(document.querySelector('#status-message'), {childList: true});
        }""")
        page.locator('#retry-connection').click()
        page.locator('#run:enabled').wait_for(timeout=90000)
        assert state['runtime_requests'] == 2
        assert page.evaluate("progressMessages.some(message => /Downloading Python.*MB/.test(message))")
        assert 'without internet' in page.locator('#mode-help').inner_text()
        page.locator('#handover').select_option('connected')
        page.locator('.job[data-job="submission"]').click()
        page.locator('#run').click()
        page.wait_for_function("document.querySelector('#status-title').textContent === 'Results are ready'", timeout=90000)
        previous = page.evaluate('JSON.stringify(records)')
        page.evaluate("() => { cloudReady = false; return activateMode('cloud'); }")
        page.locator('#run:enabled').wait_for()
        assert page.locator('#mode').input_value() == 'live'
        assert page.locator('#mode-notice').is_visible()
        assert page.evaluate('JSON.stringify(records)') == previous
        assert page.evaluate('!busy')

        # A dispatched run with lost status stays in live mode. It must neither
        # announce completion nor start a second run in the browser.
        state['available'] = True
        page.locator('#mode').select_option('cloud')
        page.locator('#run:enabled').wait_for()
        page.evaluate("""() => {
          window.originalRequest = cloud.request.bind(cloud);
          window.dispatchCount = 0;
          cloud.request = async (path, ...args) => {
            if (path === '/run') { dispatchCount++; return {id: 'dispatched'}; }
            if (path.startsWith('/state')) throw new TypeError('Failed to fetch');
            return originalRequest(path, ...args);
          };
        }""")
        page.locator('#run').click()
        page.wait_for_function("document.querySelector('#status-title').textContent === 'Live run status unavailable'")
        assert page.locator('#mode').input_value() == 'cloud'
        assert page.locator('#mode-notice').is_hidden()
        assert page.locator('#run').is_disabled()
        assert page.evaluate('dispatchCount === 1 && !busy')
        page.locator('#offline-fallback').click()
        page.locator('#run:enabled').wait_for()
        assert page.evaluate('JSON.stringify(records)') == previous

        context.set_offline(True)
        page.locator('#mode').select_option('saved')
        page.locator('#mode').select_option('live')
        page.locator('#run:enabled').wait_for()
        assert state['runtime_requests'] == 2
        assert not errors, errors
        context.close()

        # Changing mode during connection takes precedence over late failure or
        # late success. Neither case may replace the selected view or start work.
        race = browser.new_context(viewport={'width': 390, 'height': 844})
        race_page = race.new_page()
        race_errors, pending_info = [], []
        race_page.on('pageerror', lambda error: race_errors.append(str(error)))
        race_page.route('**/index.html', lambda route: route.fulfill(content_type='text/html', body=preview()))
        def held_service(route):
            if route.request.url.endswith('/info'):
                pending_info.append(route)
            else:
                route.fulfill(content_type='application/json', body=json.dumps({'id': 'late-session', 'token': 'test-token'}))
        race_page.route('**/functions/v1/paper-api/**', held_service)
        race_page.goto(f'http://127.0.0.1:{server.server_port}/index.html')
        race_page.wait_for_timeout(50)
        assert pending_info
        race_page.locator('#mode').select_option('saved')
        pending_info.pop().fulfill(status=503, content_type='application/json', body='{"error":"Unavailable"}')
        race_page.wait_for_timeout(100)
        assert race_page.locator('#mode').input_value() == 'saved'
        assert race_page.locator('#mode-notice').is_hidden()
        assert race_page.evaluate('!offlineInit && !busy')
        race_page.locator('#mode').select_option('cloud')
        race_page.wait_for_timeout(50)
        race_page.locator('#mode').select_option('live')
        pending_info.pop().fulfill(content_type='application/json', body='{"configured":true}')
        race_page.locator('#run:enabled').wait_for(timeout=90000)
        assert race_page.locator('#mode').input_value() == 'live'
        assert race_page.locator('#mode-notice').is_hidden()
        assert race_page.evaluate('!busy && Object.keys(records).length === 0')
        assert race_page.evaluate('document.documentElement.scrollWidth <= innerWidth')
        assert not race_errors, race_errors
        race.close()
        assert (ROOT/'docs/index.html').stat().st_size < (ROOT/'docs/offline.html').stat().st_size / 5
        browser.close()
    print('PASS: live default, bounded connection, automatic offline fallback, failed runtime recovery, '
          'settings/records retained, no duplicate run after status loss, late-response races and mobile layout.')
finally:
    server.shutdown()
    server.server_close()
