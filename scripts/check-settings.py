"""Check settings, reuse and highlighting at the mocked Live HTTP boundary.

All calculations now run in a recorded R container. These cases check UI request
contracts only; native and hosted checks validate scientific outputs separately.
"""
import argparse
from copy import deepcopy
import json
import os
from pathlib import Path
import re
import runpy

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
GROWTH = ['assessment_a2', 'assessment_b2', 'assessment_summary', 'assessment_report']
MSE = ['mse_prepare', 'mse_constant', 'mse_index', 'mse_buffered', 'mse_summary', 'mse_report']
JOBS += MSE
CPUE += MSE
GROWTH += MSE
COMBINED = [key for key in JOBS if key in CPUE or key in GROWTH]
PREPARE_A = ['prepare_a', 'assessment_a1', 'assessment_a2',
             'assessment_summary', 'assessment_report']
PREPARE_A += MSE
CPUE_SUMMARY = ['cpue_summary', 'cpue_report']
BUFFER = ['mse_buffered', 'mse_summary', 'mse_report']


def preview():
    saved = (ROOT / 'docs/offline.html').read_text()
    match = re.search(r'<script id="demo-payload" type="application/json">(.*?)</script>',
                      saved, re.S)
    if not match:
        raise ValueError('docs/offline.html has no preserved demo payload')
    payload = json.loads(match.group(1))
    html = (ROOT / 'app/index.html').read_text()
    for key, source in {
        'PAYLOAD': json.dumps(payload, separators=(',', ':')).replace('</', '<\\/'),
        'CSS': (ROOT / 'app/style.css').read_text(),
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
    for node in page.evaluate('checkedView().nodes'):
        assert node['state'] == ('complete' if node['key'] in expected else 'retained'), (label, node)
    assert f'{len(expected)} jobs completed' in page.locator('#status-message').inner_text()
    assert page.evaluate('selected') == start
    print(f'PASS: {label}: {len(expected)} executed, {len(result["retained"])} retained', flush=True)
    return result


def cloud_checks(page, mock, baseline):
    page.wait_for_function("mode === 'cloud' && ready", timeout=30000)
    observe_runs(page)
    for controls, start, run in [
        ({'filter': '1200'}, 'cpue_a', CPUE),
        ({'growth-rate': '0.35'}, 'assessment_a2', GROWTH),
        ({'filter': '1200', 'growth-rate': '0.35'}, 'cpue_a', COMBINED),
        ({'mse-buffer': '0.6'}, 'mse_buffered', BUFFER),
        ({'mse-buffer': '1'}, 'mse_buffered', BUFFER),
        ({'growth-rate': '0.35', 'mse-buffer': '0.6'}, 'assessment_a2', GROWTH),
    ]:
        # Supply already completed records without running a hosted calculation.
        mock.records = deepcopy(baseline)
        page.evaluate("""async baseline => {
          records = structuredClone(baseline);
          cloud.records = structuredClone(baseline);
          states = {};
          document.querySelector('#snapshot').value = '2023';
          document.querySelector('#filter').value = '0';
          document.querySelector('#growth-rate').value = '0.30';
          document.querySelector('#mse-buffer').value = '0.8';
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
            'growth_rate_2': float(controls.get('growth-rate', '0.30')), 'mse': True,
            'mse_buffer': float(controls.get('mse-buffer', '0.8')),
        }
    assert len(mock.dispatches) == 6


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', action='store_true', help='embed current UI sources with saved results')
    args = parser.parse_args()
    ui = runpy.run_path(str(ROOT / 'scripts/check-browser.py'))
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        errors = []
        page = browser.new_page(viewport={'width': 1440, 'height': 1000})
        page.on('pageerror', lambda error: errors.append(str(error)))
        mock = ui['MockCloud']()
        ui['open_live'](page, mock)
        if args.source:
            page.route('https://ui.example.test/demo', lambda route: route.fulfill(content_type='text/html', body=preview()))
            page.reload()
            page.wait_for_function("mode === 'cloud' && ready")
        baseline = mock.fixture['saved']['records']
        cloud_checks(page, mock, baseline)

        # Reverting settings restores explicit selection; Saved uses its actual
        # baseline and Live restores its own pending intent and settings.
        mock.records = deepcopy(baseline)
        page.evaluate("""async baseline => {
          records = structuredClone(baseline); cloud.records = structuredClone(baseline);
          states = {}; completedRun = null; settingsIntent = false;
          $('filter').value = '0'; $('growth-rate').value = '0.30'; $('mse-buffer').value = '0.8';
          selectJob('cpue_summary'); await refreshPlan();
        }""", baseline)
        expect_plan(page, 'cpue_summary', CPUE_SUMMARY)
        page.locator('#filter').select_option('1200')
        page.locator('#growth-rate').select_option('0.35')
        expect_plan(page, 'cpue_a', COMBINED)
        page.locator('#filter').select_option('0')
        expect_plan(page, 'assessment_a2', GROWTH)
        page.locator('#mode').select_option('saved')
        assert page.locator('#run').is_hidden()
        assert page.locator('#growth-rate').input_value() == '0.30'
        page.locator('#mode').select_option('cloud')
        expect_plan(page, 'assessment_a2', GROWTH)
        assert page.locator('#growth-rate').input_value() == '0.35'
        assert page.evaluate('selected') == 'cpue_summary'
        page.locator('#growth-rate').select_option('0.30')
        expect_plan(page, 'cpue_summary', CPUE_SUMMARY)
        page.locator('#snapshot').select_option('2024')
        expect_plan(page, 'submission', JOBS)
        page.locator('#snapshot').select_option('2023')
        expect_plan(page, 'cpue_summary', CPUE_SUMMARY)
        page.locator('#mse-buffer').select_option('0.6')
        expect_plan(page, 'mse_buffered', BUFFER)
        # Hold actual HTTP reset responses to check the UI while they are in
        # flight. A failed reset keeps the previous records and never replays.
        pending_resets = []
        def held_reset(route):
            if route.request.url.split('?')[0].endswith('/reset'):
                pending_resets.append(route)
                route.request.frame.evaluate('window.resetHeld = true')
            else:
                mock.route(route)
        page.route('**/functions/v1/paper-api/**', held_reset)
        previous_records = page.evaluate('records')
        previous_dispatches = len(mock.dispatches)
        previous_session = page.evaluate('cloud.session')
        page.locator('#reset').click()
        page.wait_for_function("busy && window.resetHeld && $('status-title').textContent === 'Starting afresh'")
        assert len(pending_resets) == 1
        assert page.locator('#run').is_disabled() and page.locator('#reset').is_disabled()
        assert page.locator('#mode').is_disabled() and page.locator('#growth-rate').is_disabled()
        assert page.evaluate('records') == previous_records
        # Explicit direct invocation also obeys the guard; it sends no request.
        page.evaluate("$('reset').onclick()")
        assert len(pending_resets) == 1
        pending_resets.pop().fulfill(status=503, content_type='application/json', body='{"error":"Reset unavailable"}')
        page.wait_for_function("!busy && $('status-title').textContent === 'Reset unavailable'")
        assert page.evaluate('records') == previous_records
        assert page.evaluate('cloud.session') == previous_session
        assert len(mock.dispatches) == previous_dispatches and mock.reset_count == 0
        assert page.locator('#run').is_enabled() and page.locator('#mode').is_enabled()
        resets = mock.reset_count
        page.evaluate('window.resetHeld = false')
        page.locator('#reset').click()
        page.wait_for_function("busy && window.resetHeld && $('status-title').textContent === 'Starting afresh'")
        assert len(pending_resets) == 1
        assert page.evaluate('records') == previous_records
        mock.route(pending_resets.pop())
        page.wait_for_function("""() => !busy && Object.keys(records).length === 0 &&
          selected === 'submission' && plan?.run.length === jobs.length &&
          !$('run').disabled && $('status-title').textContent === 'Ready to run'
        """)
        assert mock.reset_count == resets + 1
        assert page.evaluate('Object.keys(records).length') == 0
        assert page.locator('#growth-rate').input_value() == '0.30'
        assert page.locator('#mse-buffer').input_value() == '0.8'
        assert not errors, errors
        browser.close()
    print('PASS: mocked Live settings propagation, planned/completed highlighting, exact retained '
          'records, explicit selection, reversion, saved/Live restoration and reset. No model computation.')


if __name__ == '__main__':
    main()
