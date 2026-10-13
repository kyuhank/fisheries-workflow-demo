"""Source-built browser regressions for full-bundle publication and identity.

HTTP fixtures exercise controls and returned bytes; no hosted dispatch/models.
"""
import base64
from copy import deepcopy
import hashlib
import io
import json
from pathlib import Path
import runpy
import tempfile
from urllib.parse import urlsplit
import zipfile

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[1]
preview = runpy.run_path(str(ROOT / 'scripts/check-handover.py'))['preview']


class PublicationCloud:
    def __init__(self, fixture, existing=False):
        self.fixture = fixture
        self.records = deepcopy(fixture['saved']['records']) if existing else {}
        self.current = None
        self.events = []
        self.dispatches = []
        self.bundle_calls = 0
        self.next_status = 'complete'
        self.bundle_reply = None
        self.bundle_bytes = None
        self.reply_identity = 'correct'
        self.defer_bundle = False
        self.pending_bundle = None
        if existing:
            result = {'run_id': self.records['submission']['run_id'], 'run': list(self.records),
                      'retained': [], 'records': self.records, 'start': 'submission', 'scope': 'workflow'}
            self.current = {'id': '11111111-1111-4111-8111-111111111111',
                            'status': 'complete', 'result': result}
            self.publish_bundle()

    def publish_bundle(self):
        raw = io.BytesIO()
        with zipfile.ZipFile(raw, 'w') as archive:
            archive.writestr('state.json', json.dumps({'request_id': self.current['id'], 'records': self.records}))
        self.bundle_bytes = raw.getvalue()
        self.bundle_reply = {'request_id': self.current['id'],
                             'bundle': base64.b64encode(self.bundle_bytes).decode()}

    def route(self, route):
        path = urlsplit(route.request.url).path.rsplit('/', 1)[-1]
        status = 200
        if path == 'info':
            value = {'configured': True, **{key: self.fixture['cloud'][key]
                     for key in ('repository', 'data_kind', 'source_sha256')}}
        elif path == 'session':
            value = {'id': 'fixture-session', 'token': 'fixture-token'}
        elif path == 'run':
            data = route.request.post_data_json
            self.dispatches.append(data)
            plan = route.request.frame.evaluate('(data) => cloud.plan(data.start,data.settings,data.scope)', data)
            run_id = f'Mock {len(self.dispatches):03d}'
            request_id = f'{len(self.dispatches):08x}-0000-4000-8000-000000000000'
            updated = deepcopy(self.records)
            for job in self.fixture['jobs']:
                key = job['key']
                if key not in plan['run']:
                    continue
                record = deepcopy(self.fixture['saved']['records'][key])
                record['run_id'] = run_id
                record['outputs']['output.json'] = hashlib.sha256(f'{run_id}:{key}'.encode()).hexdigest()
                record['inputs'] = {parent: {'run_id': updated[parent]['run_id'],
                    'checksum': updated[parent]['outputs']['output.json']} for parent in job['parents']}
                if key == 'submission': record['settings']['last_year'] = data['settings']['last_year']
                elif key == 'cpue_a': record['settings']['min_hooks'] = data['settings']['min_hooks_a']
                elif key in ('assessment_a2','assessment_b2'): record['settings']['r'] = data['settings']['growth_rate_2']
                elif key == 'mse_buffered': record['settings']['buffer'] = data['settings']['mse_buffer']
                updated[key] = record
            self.records = updated
            result = {**plan, 'run_id': run_id, 'records': updated}
            self.current = {'id': request_id, 'status': self.next_status,
                            'result': result if self.next_status == 'complete' else None,
                            'error': 'Final database publication failed'}
            self.events = []
            if self.next_status == 'failed':
                self.events.append({'id': 1, 'event': {'state': 'plan', **plan, 'run_id': run_id}})
                for key in plan['run']:
                    self.events.append({'id': len(self.events)+1, 'event': {
                        'state': 'running', 'job': key, 'message': 'Fixture calculation'}})
                    self.events.append({'id': len(self.events)+1, 'event': {
                        'state': 'complete', 'job': key, 'record': updated[key], 'message': 'Fixture output saved'}})
            if self.next_status == 'complete': self.publish_bundle()
            if self.next_status == 'unknown': route.abort(); return
            value = {'id': request_id}
        elif path == 'state':
            value = {'run': self.current, 'events': self.events, 'state': {'records': self.records}}
        elif path == 'bundle':
            self.bundle_calls += 1
            value = deepcopy(self.bundle_reply)
            if self.reply_identity == 'stale': value['request_id'] = 'ffffffff-ffff-4fff-8fff-ffffffffffff'
            elif self.reply_identity == 'missing': value.pop('request_id')
            if self.defer_bundle:
                self.pending_bundle = (route, value)
                return
        elif path == 'output':
            key = route.request.url.split('job=')[1].split('&')[0]
            value = {**deepcopy(self.fixture['saved']['outputs'][key]), 'record': self.records[key]}
        else:
            raise AssertionError('Unexpected fixture request: ' + path)
        route.fulfill(status=status, content_type='application/json', body=json.dumps(value))


def open_case(browser, html, fixture, existing=False):
    page = browser.new_page(viewport={'width':1440,'height':1000},accept_downloads=True)
    mock = PublicationCloud(fixture, existing)
    if existing:
        # A restored-reader adapter supplies authoritative state before UI activation.
        # This exercises initial publication detection without manually setting its flag.
        bootstrap = """CloudRun.prototype.connect = async function() {
          await this.request('/info', undefined, true);
          this.session = await this.request('/session', {}, true);
          const current = await this.request('/state?after=0');
          this.run=current.run;this.records=current.state.records;
          return {records:this.records};
        };\n"""
        html = html.replace('const payload = JSON.parse', bootstrap + 'const payload = JSON.parse', 1)
    errors = []
    page.on('pageerror', lambda e: errors.append(str(e)))
    page.route('https://**/*', lambda r:r.abort())
    page.route('**/functions/v1/paper-api/**', mock.route)
    page.route('https://ui.example.test/demo', lambda r:r.fulfill(content_type='text/html',body=html))
    page.goto('https://ui.example.test/demo')
    page.wait_for_function("mode==='cloud' && ready")
    return page, mock, errors


def finish(page):
    page.wait_for_function("!busy && $('status-title').textContent==='Results are ready'")
    assert page.locator('#download').is_enabled()


def download(page, path, expected):
    with page.expect_download() as pending:page.locator('#download').click()
    pending.value.save_as(str(path))
    assert path.read_bytes() == expected


def main():
    html, fixture = preview()
    results = []
    with tempfile.TemporaryDirectory() as directory, sync_playwright() as pw:
        directory = Path(directory)
        browser = pw.chromium.launch(headless=True)
        page, mock, errors = open_case(browser, html, fixture)
        assert page.locator('#download').is_disabled()
        page.locator('#run').click();finish(page)
        download(page,directory/'full.zip',mock.bundle_bytes)
        page.locator('#growth-rate').select_option('0.35')
        page.wait_for_function("plan.changed.includes('assessment_a2')")
        assert page.locator('#download').is_enabled(), 'Selecting pending settings invalidated a published bundle'
        page.locator('#run').click();finish(page)
        assert len(mock.current['result']['run'])==10
        download(page,directory/'partial.zip',mock.bundle_bytes)
        page.locator('[data-tab="jobs"]').click();page.locator('#all-tasks').click()
        page.locator('tr[data-job="cpue_summary"] .run-job').click();finish(page)
        assert mock.current['result']['run']==['cpue_summary']
        download(page,directory/'single.zip',mock.bundle_bytes)
        results.append('Successful full, partial10 and single1 publish matching Live bytes; pending settings/selection remain downloadable')

        # Completed package survives Saved/Live switching, while Saved uses its own bytes.
        before = mock.bundle_calls
        page.locator('#mode').select_option('saved');page.wait_for_function("mode==='saved'")
        download(page,directory/'saved.zip',base64.b64decode(fixture['saved']['bundle']))
        assert mock.bundle_calls==before
        page.locator('#mode').select_option('cloud');page.wait_for_function("mode==='cloud' && ready")
        assert page.locator('#download').is_enabled()
        download(page,directory/'returned-live.zip',mock.bundle_bytes)
        results.append('Saved bytes and Live publication restored correctly across mode switching')

        # A delayed old response cannot be labelled as a newly completed request.
        received=[];page.on('download',lambda d:received.append(d))
        mock.defer_bundle=True;page.locator('#download').click()
        page.wait_for_timeout(100);assert mock.pending_bundle
        mock.defer_bundle=False
        page.locator('tr[data-job="cpue_report"] .run-job').click();finish(page)
        route,value=mock.pending_bundle;route.fulfill(content_type='application/json',body=json.dumps(value))
        page.wait_for_timeout(100)
        assert not received and page.locator('#status-title').inner_text()=='Results are ready'
        results.append('Late prior-request bundle discarded without overwriting newer completion')

        # An unchanged record count is insufficient: three new outputs, old bundle.
        prior_bytes=mock.bundle_bytes
        mock.next_status='failed'
        page.locator('#mse-buffer').select_option('0.6')
        page.wait_for_function("plan.changed.includes('mse_buffered')")
        page.locator('#run').click()
        page.wait_for_function("!busy && $('status-title').textContent==='The analysis stopped'")
        assert page.evaluate("records.mse_buffered.settings.buffer===0.6 && Object.keys(records).length===22")
        assert mock.bundle_bytes==prior_bytes
        assert page.locator('#download').is_disabled()
        assert page.locator('#download').get_attribute('title')=='Download after a successful run'
        before=mock.bundle_calls;page.evaluate("$('download').onclick()")
        assert mock.bundle_calls==before and not received
        page.locator('#all-tasks').click()
        page.locator('tr[data-job="mse_buffered"] .open-output').click()
        with page.expect_download() as individual:page.locator('#save-output').click()
        individual.value.save_as(str(directory/'individual.html'))
        assert (directory/'individual.html').read_text()==fixture['saved']['outputs']['mse_buffered']['html']
        page.locator('[data-output="record"]').click()
        with page.expect_download() as individual_json:page.locator('#download-job-record').click()
        individual_json.value.save_as(str(directory/'individual.json'))
        json.loads((directory/'individual.json').read_text())
        assert 'mse_buffered' in (directory/'individual.json').read_text()
        assert '"buffer": 0.6' in (directory/'individual.json').read_text()
        page.locator('#output-close').click()
        page.locator('#mode').select_option('saved');page.wait_for_function("mode==='saved'")
        assert page.locator('#download').is_enabled()
        page.locator('#mode').select_option('cloud');page.wait_for_function("mode==='cloud' && ready")
        assert page.locator('#download').is_disabled()
        results.append('Failed partial outputs0.6 plus old full bundle blocked; no /bundle call; individual HTML/JSON still downloadable; Saved/Live switch preserves block')
        assert not errors, errors
        page.close()

        # Fresh UI activation with an authoritative existing complete request.
        page,mock,errors=open_case(browser,html,fixture,existing=True)
        assert page.evaluate('completedRun===null')
        assert page.locator('#download').is_enabled()
        download(page,directory/'existing.zip',mock.bundle_bytes)
        for identity in ['stale','missing']:
            mock.reply_identity=identity
            files=[];page.on('download',lambda d:files.append(d))
            page.evaluate("status('', 'Checking download', 'Fixture identity check')")
            page.locator('#download').click()
            page.wait_for_function("$('status-title').textContent==='Download unavailable'")
            assert not files
            assert 'completed run' in page.locator('#status-message').inner_text()
        mock.reply_identity='correct'
        results.append('Existing completed reader enables matching UUID bundle; stale and unbound replies rejected')
        mock.next_status='unknown';page.locator('#run').click()
        page.wait_for_function('unresolvedLive && !busy')
        assert page.locator('#download').is_disabled() and page.locator('#run').is_disabled()
        before=mock.bundle_calls;page.evaluate("$('download').onclick()")
        assert mock.bundle_calls==before
        results.append('UNKNOWN dispatch blocks prior package and retains execution lock')
        assert not errors,errors
        page.close();browser.close()
    artifact=ROOT/'.test-output/download-regressions.json';artifact.parent.mkdir(exist_ok=True)
    artifact.write_text(json.dumps({'status':'passed_local_http_fixtures','checks':results,
        'source_sha256':{name:hashlib.sha256((ROOT/name).read_bytes()).hexdigest()
                         for name in ['app/app.js','app/cloud.js','scripts/check-download.py']},
        'hosted_dispatches':0,'model_fits':0},indent=2)+'\n')
    print('PASS: published Live/Saved bundle bytes, full/partial/single/existing reader, failed/UNKNOWN block, UUID binding and late-response guard; local fixtures only.')


if __name__=='__main__':main()
