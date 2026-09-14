"""Exercise MSE execution, peer barriers, reports and partial reruns offline."""
import json
from pathlib import Path

from playwright.sync_api import expect, sync_playwright

ROOT = Path(__file__).resolve().parents[1]
PEERS = ['mse_constant', 'mse_index', 'mse_buffered']
MSE = ['mse_prepare', *PEERS, 'mse_summary', 'mse_report']


def run(page, expected):
    page.wait_for_function('!busy && ready && !document.querySelector("#run").disabled')
    before = page.evaluate('structuredClone(records)')
    assert page.evaluate('plan.run') == expected
    page.evaluate('window.observedStates = []')
    page.locator('#run').click()
    page.wait_for_function('!busy && document.querySelector("#status-title").textContent === "Results are ready"', timeout=90000)
    after = page.evaluate('records')
    executed = page.evaluate('completedRun.run')
    assert executed == expected, executed
    for key, record in after.items():
        if key not in executed:
            assert record == before[key], f'Retained job changed: {key}'
    assert page.evaluate('completedRun.retained.length') == len(after) - len(executed)
    return page.evaluate('observedStates')


with sync_playwright() as playwright:
    browser = playwright.chromium.launch()
    page = browser.new_page(offline=True, viewport={'width': 1440, 'height': 1100})
    errors = []
    page.on('pageerror', lambda error: errors.append(str(error)))
    page.goto((ROOT / 'docs/offline.html').as_uri(), wait_until='domcontentloaded')
    page.wait_for_function('mode === "live" && ready', timeout=90000)
    page.evaluate('''() => {
      window.observedStates = [];
      const previous = render;
      render = function() {
        previous();
        if (busy) observedStates.push(structuredClone(states));
      };
    }''')
    all_jobs = page.evaluate('jobs.map(job => job.key)')
    assert len(all_jobs) == 22
    observed = run(page, all_jobs)
    assert all(any(state.get(key) == 'running' for state in observed) for key in MSE)
    assert any(all(state.get(key) == 'running' for key in PEERS) for state in observed)
    for state in observed:
        if state.get('mse_summary') == 'running':
            assert all(state.get(key) == 'complete' for key in PEERS), state
    assert page.locator('#task-count').inner_text() == '4'
    assert page.locator('#job-count').inner_text() == '22'
    page.locator('[data-tab="jobs"]').click()
    page.locator('#tasks .mse').click()
    assert page.locator('#job-table-body tr').count() == 6
    page.locator('tr[data-job="mse_prepare"] .open-job-record').click()
    page.locator('#output-record:visible').wait_for()
    assert page.locator('#output-record .record-input').count() == 4
    page.locator('#output-close').click()

    for key in PEERS:
        page.locator(f'tr[data-job="{key}"] .open-output').click()
        frame = page.frame_locator('#output-frame')
        trial = frame.locator('.trial-table').first
        expect(trial).to_be_visible()
        assert trial.locator('tbody tr').count() == 5
        first = page.evaluate('currentOutput.output.example.rows[0]')
        cells = trial.locator('tbody tr').first.locator('td').all_text_contents()
        assert cells == [str(first['year']), f'{first["index_ratio"]:.4g}',
                         f'{first["requested_catch_t"]:.4g}', f'{first["catch_t"]:.4g}',
                         f'{first["start_SB_over_SB0"]:.2f} → {first["SB_over_SB0"]:.2f}']
        page.locator('#output-close').click()

    reports = {}
    for key in ['mse_summary', 'mse_report']:
        page.locator(f'tr[data-job="{key}"] .open-output').click()
        frame = page.frame_locator('#output-frame')
        expect(frame.locator('h1')).to_have_text('MSE report' if key == 'mse_report' else 'MSE results summary')
        reports[key] = frame.locator('body').inner_text()
        assert reports[key].strip()
        if key == 'mse_summary':
            assert frame.locator('.mp-rule h3').all_text_contents() == [
                'Constant catch', 'Index rule', 'Buffered rule']
        page.locator('#output-close').click()
    assert reports['mse_report'] != reports['mse_summary'], 'MSE report repeats the summary'
    assert 'MSE report' in reports['mse_report']

    page.locator('[data-tab="workflow"]').click()
    page.locator('.workflow-node[data-job="mse_index"]').click()
    run(page, ['mse_index', 'mse_summary', 'mse_report'])
    for key in ['mse_constant', 'mse_buffered']:
        assert page.locator(f'.workflow-node[data-job="{key}"]').get_attribute('class').split().count('retained') == 1

    page.locator('#mortality').select_option('0.35')
    page.wait_for_function('plan?.changed.includes("assessment_b2")')
    expected = ['assessment_a2', 'assessment_b2', 'assessment_summary', 'assessment_report', *MSE]
    run(page, expected)
    highlighted = page.locator('.workflow-node.in-path').evaluate_all('(nodes) => nodes.map(n => n.dataset.job)')
    assert highlighted == expected

    page.locator('.workflow-node[data-job="cpue_summary"]').click()
    run(page, ['cpue_summary', 'cpue_report'])
    assert all(page.evaluate('(key) => states[key] === "retained"', key) for key in MSE)
    assert not errors, errors
    browser.close()
print(json.dumps({'mse': 'passed', 'jobs': 22, 'tasks': 4,
                  'checks': ['three peer strategies', 'summary barrier', 'separate report',
                             'four recorded assessment inputs', 'strategy-only rerun',
                             'mortality propagation', 'independent CPUE reporting']}))
