"""Check live connection recovery and the on-demand offline runtime in a browser."""
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
from threading import Thread
from urllib.parse import urlsplit

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[1]


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
        unit.clock.fast_forward(10001)
        unit.wait_for_function("window.failure?.includes('10 seconds')")
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

        state = {'available': False, 'runtime_failure': True, 'runtime_requests': 0}
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
        page.goto(f'http://127.0.0.1:{server.server_port}/index.html')
        page.locator('#retry-connection:visible').wait_for()
        assert state['runtime_requests'] == 0
        assert page.locator('#offline-download').is_visible()
        assert page.locator('#offline-download').get_attribute('href') == 'offline.html'
        assert page.locator('#run').is_disabled()
        state['available'] = True
        page.locator('#retry-connection').click()
        page.locator('#run:enabled').wait_for()
        assert page.locator('#status-title').inner_text() == 'Ready to run'

        page.locator('#mode').select_option('live')
        page.locator('#retry-connection:visible').wait_for()
        assert page.locator('#mode').input_value() == 'live'
        assert state['runtime_requests'] == 1
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
        context.set_offline(True)
        page.locator('#mode').select_option('saved')
        page.locator('#mode').select_option('live')
        page.locator('#run:enabled').wait_for()
        assert state['runtime_requests'] == 2
        assert not errors, errors
        assert (ROOT/'docs/index.html').stat().st_size < (ROOT/'docs/offline.html').stat().st_size / 5
        browser.close()
    print('PASS: bounded live connection, retry, no initial runtime download, offline download progress and reuse.')
finally:
    server.shutdown()
    server.server_close()
