"""Check the portable Saved view and Live controls with HTTP fixtures.

These cases test browsing and requests. Container checks test calculations.
"""
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import re
import tempfile
from urllib.parse import urlsplit
import zipfile

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[1]


def payload():
    text = (ROOT / 'docs/offline.html').read_text()
    return json.loads(re.search(r'<script id="demo-payload" type="application/json">(.*?)</script>', text, re.S).group(1))


class MockCloud:
    """Return fixture HTTP state without running calculations."""
    def __init__(self):
        self.fixture = payload()
        self.records = {}
        self.dispatches = []
        self.result = None
        self.reset_count = 0

    def route(self, route):
        path = urlsplit(route.request.url).path.rsplit('/', 1)[-1]
        if path == 'info':
            value = {'configured': True, 'repository': self.fixture['cloud']['repository']}
        elif path == 'session':
            value = {'id': 'mock-session', 'token': 'mock-token'}
        elif path == 'reset':
            self.records = {}
            self.reset_count += 1
            value = {}
        elif path == 'run':
            data = route.request.post_data_json
            self.dispatches.append(data)
            selected = route.request.frame.evaluate('(data) => cloud.plan(data.start, data.settings, data.scope)', data)
            run_id = f'Mock {len(self.dispatches):03d}'
            updated = deepcopy(self.records)
            for job in self.fixture['jobs']:
                key = job['key']
                if key not in selected['run']:
                    continue
                updated[key] = deepcopy(self.fixture['saved']['records'][key])
                record = updated[key]
                record['run_id'] = run_id
                record['outputs']['output.json'] = hashlib.sha256(f'{run_id}:{key}'.encode()).hexdigest()
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
            self.records = updated
            self.result = {**selected, 'run_id': run_id, 'records': updated}
            value = {'id': run_id}
        elif path == 'state':
            value = {'run': {'id': self.result['run_id'], 'status': 'complete', 'result': self.result},
                     'events': [], 'state': {'records': self.records}}
        elif path == 'output':
            key = route.request.url.split('job=')[1].split('&')[0]
            value = {**deepcopy(self.fixture['saved']['outputs'][key]), 'record': self.records[key]}
        elif path == 'transfer':
            value = {}
        else:
            raise AssertionError('Unexpected mocked endpoint: ' + path)
        route.fulfill(content_type='application/json', body=json.dumps(value))


def open_live(page, mock):
    page.route('https://**/*', lambda route: route.abort())
    page.route('**/functions/v1/paper-api/**', mock.route)
    page.route('https://ui.example.test/demo', lambda route: route.fulfill(
        content_type='text/html', body=(ROOT / 'docs/index.html').read_text()))
    page.goto('https://ui.example.test/demo')
    page.wait_for_function("mode === 'cloud' && ready")


def complete(page, expected):
    page.locator('#run:enabled').wait_for()
    assert page.evaluate('plan.run') == expected
    page.locator('#run').click()
    page.wait_for_function("!busy && $('status-title').textContent === 'Results are ready'")
    assert page.evaluate('completedRun.run') == expected
    return page.evaluate('records')


def main():
    with sync_playwright() as playwright, tempfile.TemporaryDirectory() as directory:
        browser = playwright.chromium.launch(headless=True)
        context = browser.new_context(offline=True, accept_downloads=True,
                                      viewport={'width': 1440, 'height': 1000})
        page = context.new_page()
        errors, requests = [], []
        page.on('pageerror', lambda error: errors.append(str(error)))
        page.on('request', lambda request: requests.append(request.url) if request.url.startswith('http') else None)
        page.goto((ROOT / 'docs/offline.html').as_uri())
        page.wait_for_function("mode === 'saved'")
        assert page.locator('#mode option').count() == 2
        # Inspect the option directly; Playwright follows the enclosing label.
        assert page.locator('#mode option[value="cloud"]').evaluate(
            "option => option.disabled && option.hasAttribute('disabled')")
        # Even a direct invocation cannot start Live from the portable file.
        assert page.evaluate("""async () => {
          await activateMode('cloud');
          return mode === 'saved' && !ready && cloud.session === null;
        }""")
        assert page.locator('#run').is_hidden()
        assert page.locator('#reset').is_disabled()
        assert page.locator('.workflow-node.complete').count() == 22
        assert page.locator('#download').is_enabled()
        assert 'does not run code' in page.locator('#mode-help').inner_text()
        assert page.evaluate('typeof Worker === "function" && !document.querySelector("#worker-source")')
        keys = page.evaluate('jobs.map(job => job.key)')
        for key in keys:
            page.evaluate('(key) => openOutput(key)', key)
            page.frame_locator('#output-frame').locator('h1').wait_for()
            assert page.evaluate('currentOutput.record.job') == key
            record = page.evaluate('currentOutput.record')
            assert 'jobs/' + key + '/run.R' in record['code'], key
            assert re.fullmatch(r'ghcr.io/pacificcommunity/fisheries-workflow@sha256:[a-f0-9]{64}', record['execution']['container'])
            assert record['software'].get('R') or record['software'].get('r'), key
            page.locator('[data-output="record"]').click()
            assert page.locator('.record-image-digest').inner_text() == record['execution']['container'].split('@')[1]
            assert page.locator('.record-source').count() >= 1
            assert page.locator('#reproduce-job').is_disabled()
            page.locator('#output-close').click()
        with page.expect_download() as download:
            page.locator('#download').click()
        path = Path(directory) / 'saved.zip'
        download.value.save_as(path)
        with zipfile.ZipFile(path) as archive:
            assert archive.testzip() is None
            names = archive.namelist()
            assert 'REPRODUCE.txt' in names
            assert any(name.endswith('report.qmd') for name in names)
            for key in keys:
                assert 'jobs/' + key + '/run.R' in names
        page.locator('[data-tab="jobs"]').click()
        assert page.locator('#tasks .task').count() == 4
        for task, count in [('data', 4), ('cpue', 4), ('assessment', 8), ('mse', 6)]:
            page.locator('#show-tasks').click()
            page.locator('#tasks .' + task).click()
            assert page.locator('#job-table-body tr').count() == count
        page.set_viewport_size({'width': 390, 'height': 844})
        assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')
        assert not errors and not requests, (errors, requests)
        browser.close()
    print('PASS: 22 saved R job outputs, immutable container records, downloadable sources/QMD, '
          'four task views and offline browsing without any calculation or network request.')


if __name__ == '__main__':
    main()
