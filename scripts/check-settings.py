"""Check settings-only reruns offline and at the mocked cloud dispatch boundary.

By default test docs/offline.html; --source embeds the current app and Python
sources into its preserved runtime payload without rebuilding generated files.
No live service or GitHub execution is contacted.
"""
import argparse
import base64
from copy import deepcopy
import json
import os
from pathlib import Path
import re
import tempfile
from urllib.parse import urlsplit

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[1]
JOBS = [
    'submission', 'qc', 'database', 'extract', 'cpue_a', 'cpue_b',
    'cpue_summary', 'cpue_report', 'prepare_a', 'prepare_b',
    'assessment_a1', 'assessment_a2', 'assessment_b1', 'assessment_b2',
    'assessment_summary', 'assessment_report',
]
CPUE = ['cpue_a', 'cpue_summary', 'cpue_report', 'prepare_a',
        'assessment_a1', 'assessment_a2', 'assessment_summary', 'assessment_report']
MORTALITY = ['assessment_a2', 'assessment_b2', 'assessment_summary', 'assessment_report']
MSE = ['mse_prepare', 'mse_constant', 'mse_index', 'mse_buffered', 'mse_summary', 'mse_report']
JOBS += MSE
CPUE += MSE
MORTALITY += MSE
COMBINED = [key for key in JOBS if key in CPUE or key in MORTALITY]
PREPARE_A = ['prepare_a', 'assessment_a1', 'assessment_a2',
             'assessment_summary', 'assessment_report']
PREPARE_A += MSE
CPUE_SUMMARY = ['cpue_summary', 'cpue_report']


def preview():
    saved = (ROOT / 'docs/offline.html').read_text()
    match = re.search(r'<script id="demo-payload" type="application/json">(.*?)</script>',
                      saved, re.S)
    if not match:
        raise ValueError('docs/offline.html has no preserved demo payload')
    payload = json.loads(match.group(1))
    for name in payload['files']:
        source = ROOT / name
        if source.is_file():
            payload['files'][name] = base64.b64encode(source.read_bytes()).decode()
    html = (ROOT / 'app/index.html').read_text()
    for key, source in {
        'PAYLOAD': json.dumps(payload, separators=(',', ':')).replace('</', '<\\/'),
        'CSS': (ROOT / 'app/style.css').read_text(),
        'WORKER': (ROOT / 'app/worker.js').read_text(),
        'APP': '\n'.join((ROOT / 'app' / name).read_text()
                         for name in ['cloud.js', 'lineage.js', 'app.js', 'record.js']),
    }.items():
        html = html.replace('/*__' + key + '__*/', source)
    return html


def observe_runs(page):
    # Observe the actual UI request and result, preserving both execution paths.
    page.evaluate("""() => {
      window.checkedRuns = [];
      window.checkedViews = [];
      window.checkedView = () => ({
        busy, pending: dispatchPending,
        nodes: [...document.querySelectorAll('.workflow-node')].map(node => ({
          key: node.dataset.job, inPath: node.classList.contains('in-path'),
          opacity: Number(getComputedStyle(node).opacity),
          state: states[node.dataset.job]
        })),
        edges: [...document.querySelectorAll('.connection[data-from]')].map(edge => ({
          from: edge.dataset.from, to: edge.dataset.to,
          kind: ['muted', 'selected', 'running', 'saved', 'handover']
            .find(kind => edge.classList.contains(kind))
        }))
      });
      const originalRender = render;
      render = function() {
        originalRender();
        if (busy) checkedViews.push(checkedView());
      };
      const original = call;
      call = async function(type, data) {
        const input = type === 'run' ? structuredClone(data) : null;
        const result = await original(type, data);
        if (input) checkedRuns.push({input, result: structuredClone(result)});
        return result;
      };
    }""")


def expect_highlight(page, run, label, view=None):
    view = view or page.evaluate('checkedView()')
    expected = set(run)
    highlighted = {node['key'] for node in view['nodes'] if node['inPath']}
    assert highlighted == expected, f'{label}: highlighted {sorted(highlighted)}'
    for node in view['nodes']:
        strong = node['state'] in ('running', 'failed', 'returned', 'handover')
        if not view['busy']:
            strong = node['key'] in expected
        assert (node['opacity'] == 1) == strong, (label, node)
    nodes = {node['key']: node for node in view['nodes']}
    for edge in view['edges']:
        in_path = edge['from'] in expected and edge['to'] in expected
        receiving = view['busy'] and nodes[edge['to']]['state'] == 'running'
        if receiving:
            assert edge['kind'] == ('running' if edge['from'] in expected else 'saved'), (label, edge)
        elif view['busy']:
            assert edge['kind'] in ('muted', 'handover'), (label, edge)
        else:
            assert edge['kind'] == ('selected' if in_path else 'muted'), (label, edge)
        if view['pending']:
            assert edge['kind'] not in ('running', 'saved'), (label, edge)


def expect_plan(page, start, run):
    page.wait_for_function("""({start, run}) => !busy && plan?.start === start &&
      JSON.stringify(plan.run) === JSON.stringify(run) && !document.querySelector('#run').disabled
    """, arg={'start': start, 'run': run}, timeout=30000)
    snapshot = page.evaluate("""() => {
      selectedTask = '';
      render();
      return {plan, title: byKey[plan.start].title,
        parents: byKey[plan.start].parents.filter(key => plan.retained.includes(key))
          .map(key => `${byKey[key].title} (${records[key].run_id})`)};
    }""")
    assert snapshot['plan']['retained'] == [key for key in JOBS if key not in run]
    assert page.locator('#selection-title').inner_text() == snapshot['title']
    assert page.locator('.workflow-node.selected').get_attribute('data-job') == start
    assert page.locator('#job-table-body tr.selected-job').get_attribute('data-job') == start
    assert page.locator('#run').inner_text() == (
        'Run full workflow →' if start == 'submission' else 'Run from this job →')
    if snapshot['parents']:
        expected_inputs = 'Uses saved inputs: ' + ' · '.join(snapshot['parents'])
        assert page.locator('#reuse-message').inner_text().startswith(expected_inputs)


def select_job(page, key, run):
    page.locator('[data-tab="workflow"]').click()
    page.locator(f'.job[data-job="{key}"]').click()
    expect_plan(page, key, run)
    expect_highlight(page, run, 'explicit job selection')


def run_and_check(page, start, expected, label):
    expect_plan(page, start, expected)
    expect_highlight(page, expected, label + ' planned')
    before = page.evaluate('records')
    count = page.evaluate('checkedRuns.length')
    view_count = page.evaluate('checkedViews.length')
    page.locator('#run').click()
    page.wait_for_function("""count => checkedRuns.length === count + 1 && !busy &&
      document.querySelector('#status-title').textContent === 'Results are ready' &&
      !document.querySelector('#run').disabled
    """, arg=count, timeout=90000)
    observed = page.evaluate('checkedRuns.at(-1)')
    result = observed['result']
    assert observed['input']['start'] == result['start'] == start, observed['input']
    assert result['run'] == expected, result['run']
    assert result['retained'] == [key for key in JOBS if key not in expected]
    assert set(result['records']) == set(JOBS)
    for key in expected:
        assert result['records'][key]['run_id'] == result['run_id'], key
        assert key not in before or before[key]['run_id'] != result['run_id'], key
    for key in result['retained']:
        # Includes original run ID, input identities and every output checksum.
        assert result['records'][key] == before[key], f'{label}: changed retained {key}'
    assert page.evaluate('records') == result['records']
    expect_highlight(page, expected, label + ' completed')
    views = page.evaluate('count => checkedViews.slice(count)', view_count)
    assert any(view['pending'] for view in views), label + ': no pending dispatch observed'
    for view in views:
        expect_highlight(page, expected, label + ' executing', view)
    if label.startswith('offline'):
        running = {node['key'] for view in views for node in view['nodes']
                   if node['state'] == 'running'}
        assert running == set(expected), (label, 'observed running', running)
    for node in page.evaluate('checkedView().nodes'):
        assert node['state'] == ('complete' if node['key'] in expected else 'retained'), (label, node)
    assert f'{len(expected)} jobs completed' in page.locator('#status-message').inner_text()
    assert page.evaluate('selected') == start
    print(f'PASS: {label}: {len(expected)} executed, {len(result["retained"])} retained', flush=True)
    return result


def offline_checks(page):
    page.wait_for_function("mode === 'live' && ready", timeout=90000)
    observe_runs(page)
    baseline = run_and_check(page, 'submission', JOBS, 'offline full baseline')['records']

    # The controls alone must override the previous full-workflow starting job.
    page.locator('#filter').select_option('1200')
    result = run_and_check(page, 'cpue_a', CPUE, 'offline dropdown-only CPUE')
    assert result['records']['cpue_a']['settings']['min_hooks'] == 1200
    expect_plan(page, 'cpue_a', CPUE)

    page.locator('#mortality').select_option('0.35')
    result = run_and_check(page, 'assessment_a2', MORTALITY, 'offline dropdown-only mortality')
    for key in ['assessment_a2', 'assessment_b2']:
        assert result['records'][key]['settings']['M'] == 0.35
    # The next executable plan has only A2; the completed diagram must retain B2.
    expect_plan(page, 'assessment_a2', [key for key in MORTALITY if key != 'assessment_b2'])
    expect_highlight(page, MORTALITY, 'completed mortality after next-plan refresh')
    page.locator('#mode').select_option('saved')
    page.locator('#mode').select_option('live')
    expect_plan(page, 'assessment_a2', [key for key in MORTALITY if key != 'assessment_b2'])
    expect_highlight(page, MORTALITY, 'completed mortality after mode restoration')

    page.locator('#filter').select_option('0')
    page.locator('#mortality').select_option('0.30')
    run_and_check(page, 'cpue_a', COMBINED, 'offline combined setting changes')

    select_job(page, 'cpue_summary', CPUE_SUMMARY)
    page.locator('#filter').select_option('1200')
    page.locator('#mortality').select_option('0.35')
    expect_plan(page, 'cpue_a', COMBINED)
    assert page.evaluate('selected') == 'cpue_summary'
    page.locator('#filter').select_option('0')
    expect_plan(page, 'assessment_a2', MORTALITY)

    page.locator('#mode').select_option('saved')
    assert page.locator('#run').is_hidden()
    assert page.locator('#mortality').input_value() == '0.30'
    page.locator('#mode').select_option('live')
    expect_plan(page, 'assessment_a2', MORTALITY)
    assert page.locator('#filter').input_value() == '0'
    assert page.locator('#mortality').input_value() == '0.35'
    assert page.evaluate('selected') == 'cpue_summary'

    page.locator('#mortality').select_option('0.30')
    expect_plan(page, 'cpue_summary', CPUE_SUMMARY)
    page.locator('#snapshot').select_option('2024')
    expect_plan(page, 'submission', JOBS)
    page.locator('#snapshot').select_option('2023')
    expect_plan(page, 'cpue_summary', CPUE_SUMMARY)
    print('PASS: partial/all reversion, snapshot changes and saved/live intent restoration', flush=True)

    page.locator('#filter').select_option('1200')
    page.locator('#mortality').select_option('0.35')
    expect_plan(page, 'cpue_a', COMBINED)
    select_job(page, 'submission', JOBS)
    run_and_check(page, 'submission', JOBS, 'offline explicit submission overrides settings')

    select_job(page, 'prepare_a', PREPARE_A)
    for number in range(1, 3):
        run_and_check(page, 'prepare_a', PREPARE_A, f'offline repeated intermediate run {number}')

    page.locator('#filter').select_option('0')
    expect_plan(page, 'cpue_a', CPUE)
    page.locator('#reset').click()
    expect_plan(page, 'submission', JOBS)
    assert page.evaluate('records') == {}
    assert page.locator('#filter').input_value() == '0'
    assert page.locator('#mortality').input_value() == '0.30'
    return baseline


class MockCloud:
    """Supply completion responses; keep the real CloudRun HTTP client/loop."""
    def __init__(self):
        self.records = {}
        self.dispatches = []
        self.run = []
        self.result = None

    def route(self, route):
        path = urlsplit(route.request.url).path.rsplit('/', 1)[-1]
        if path == 'info':
            value = {'configured': True}
        elif path == 'session':
            value = {'id': 'settings-test-session', 'token': 'settings-test-token'}
        elif path == 'run':
            data = route.request.post_data_json
            self.dispatches.append(data)
            run_id = f'Mock {len(self.dispatches):03d}'
            updated = deepcopy(self.records)
            for key in self.run:
                updated[key]['run_id'] = run_id
            updated['submission']['settings']['last_year'] = data['settings']['last_year']
            updated['cpue_a']['settings']['min_hooks'] = data['settings']['min_hooks_a']
            for key in ['assessment_a2', 'assessment_b2']:
                updated[key]['settings']['M'] = data['settings']['mortality_2']
            self.result = {
                'run_id': run_id, 'start': data['start'], 'run': self.run,
                'retained': [key for key in JOBS if key not in self.run], 'records': updated,
            }
            value = {'id': run_id}
        elif path == 'state':
            value = {
                'run': {'id': self.result['run_id'], 'status': 'complete', 'result': self.result},
                'events': [], 'state': {'records': self.result['records']},
            }
        else:
            raise AssertionError(f'Unexpected mocked cloud endpoint: {path}')
        route.fulfill(content_type='application/json', body=json.dumps(value))


def cloud_checks(page, mock, baseline):
    page.wait_for_function("mode === 'cloud' && ready", timeout=30000)
    observe_runs(page)
    for controls, start, run in [
        ({'filter': '1200'}, 'cpue_a', CPUE),
        ({'mortality': '0.35'}, 'assessment_a2', MORTALITY),
        ({'filter': '1200', 'mortality': '0.35'}, 'cpue_a', COMBINED),
    ]:
        # Supply already completed records without running a hosted calculation.
        mock.records = deepcopy(baseline)
        mock.run = run
        page.evaluate("""async baseline => {
          records = structuredClone(baseline);
          cloud.records = structuredClone(baseline);
          states = {};
          document.querySelector('#snapshot').value = '2023';
          document.querySelector('#filter').value = '0';
          document.querySelector('#mortality').value = '0.30';
          selectJob('submission');
          await refreshPlan();
        }""", baseline)
        for control, value in controls.items():
            page.locator(f'#{control}').select_option(value)
        expect_plan(page, start, run)
        run_and_check(page, start, run, f'mocked cloud dropdown-only {list(controls)}')
        assert mock.dispatches[-1]['start'] == start
        assert mock.dispatches[-1]['handover'] == 'connected'
        assert mock.dispatches[-1]['settings'] == {
            'last_year': 2023, 'min_hooks_a': int(controls.get('filter', '0')),
            'mortality_2': float(controls.get('mortality', '0.30')),
        }
    assert len(mock.dispatches) == 3


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', action='store_true', help='embed current sources in the preserved runtime')
    args = parser.parse_args()
    with tempfile.TemporaryDirectory() as directory, sync_playwright() as playwright:
        path = ROOT / 'docs/offline.html'
        if args.source:
            path = Path(directory) / 'settings-preview.html'
            path.write_text(preview())
        options = {'headless': True}
        if os.environ.get('CHROME_PATH'):
            options['executable_path'] = os.environ['CHROME_PATH']
        browser = playwright.chromium.launch(**options)
        errors = []
        offline = browser.new_context(offline=True, viewport={'width': 1440, 'height': 1000})
        offline.route('https://**/*', lambda route: route.abort())
        page = offline.new_page()
        page.on('pageerror', lambda error: errors.append(str(error)))
        page.goto(path.as_uri())
        baseline = offline_checks(page)
        offline.close()

        online = browser.new_context(offline=True, viewport={'width': 1440, 'height': 1000})
        online.route('https://**/*', lambda route: route.abort())
        mock = MockCloud()
        online.route('**/functions/v1/paper-api/**', mock.route)
        page = online.new_page()
        page.on('pageerror', lambda error: errors.append(str(error)))
        page.goto(path.as_uri())
        cloud_checks(page, mock, baseline)
        assert not errors, errors
        browser.close()
    print('PASS: settings reruns, planned/executed highlighting, retained records, selection intent and cloud dispatch. '
          + ('Current sources.' if args.source else 'Built offline artifact.'))


if __name__ == '__main__':
    main()
