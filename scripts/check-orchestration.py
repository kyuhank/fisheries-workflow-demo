"""Check saved orchestration views and mocked Live job/scope contracts."""
from pathlib import Path
import json
import tempfile
import runpy

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[1]
ARTIFACTS = ROOT / '.test-output'
ARTIFACTS.mkdir(exist_ok=True)


def preview():
    # Build first: the graph, saved examples and executable code must match.
    return (ROOT / 'docs/offline.html').read_text()


def run_selection(page):
    return page.evaluate('({selected, settingsIntent, completedRun, plan, settings: settings()})')


def switch_with_guide(page, target):
    """Changing the explanatory view must preserve the selected execution."""
    before = run_selection(page)
    assert page.locator('#view-guide-link').get_attribute('href') == '#' + target
    page.locator('#view-guide-link').click()
    page.wait_for_url('**#' + target)
    active, inactive = ('jobs', 'workflow') if target == 'orchestration' else ('workflow', 'jobs')
    # The URL changes before the hashchange handler updates the shared view.
    # Wait for that observable UI transition, then retain the invariant checks.
    page.locator(f'#{active}-view').wait_for(state='visible')
    page.locator(f'#{inactive}-view').wait_for(state='hidden')
    assert page.locator(f'#{active}-view').is_visible()
    assert page.locator(f'#{inactive}-view').is_hidden()
    assert page.locator(f'[data-tab="{active}"]').get_attribute('aria-selected') == 'true'
    assert page.locator('#run-controls').count() == 1
    assert page.locator('#jobs-view #run-controls').count() == int(target == 'orchestration')
    assert run_selection(page) == before, 'View guide changed the run selection or plan'


def expect_run(page, previous, expected, scope):
    # A completed single job may leave an unrelated setting pending, which
    # refreshPlan correctly reports instead of the generic completion message.
    page.wait_for_function("""({previous, expected}) => !busy &&
      orchestrationRuns.length === previous + 1 && completedRun &&
      JSON.stringify(completedRun.run) === JSON.stringify(expected)
    """, arg={'previous': previous, 'expected': expected}, timeout=90000)
    page.locator('#run:enabled').wait_for()
    run = page.evaluate('orchestrationRuns.at(-1)')
    assert run['input']['scope'] == scope, run['input']
    assert run['result']['run'] == expected, run['result']['run']
    assert page.evaluate('completedRun.run') == expected
    assert page.evaluate('records') == run['result']['records']
    for key in expected:
        assert run['result']['records'][key]['run_id'] == run['result']['run_id']
        assert run['result']['records'][key]['outputs']['output.json']
    return run


def unchanged_records(page, before, executed):
    after = page.evaluate('records')
    for key, record in before.items():
        if key not in executed:
            assert after[key] == record, f'Unexpected change to {key}'


def connections(page, key, parents, children):
    page.locator('#dependency-job').select_option(key)
    for group, expected in [('inputs', parents), ('current', [key]), ('outputs', children)]:
        actual = page.locator(f'[data-group="{group}"] .dependency-card').evaluate_all(
            'cards => cards.map(card => card.dataset.job)')
        assert actual == expected, (key, group, actual)
        for member in expected:
            number = page.evaluate('(key) => jobNumber(key)', member)
            assert page.locator(f'[data-group="{group}"] [data-job="{member}"] .job-number').inner_text() == number
    assert not page.locator('#output-dialog').is_visible()


def browse_dependencies(page):
    before = run_selection(page)
    page.locator('#show-dependencies').click()
    connections(page, 'prepare_a', ['extract', 'cpue_a'], ['assessment_a1', 'assessment_a2'])
    connections(page, 'mse_prepare', ['assessment_a1', 'assessment_a2', 'assessment_b1', 'assessment_b2'],
                ['mse_constant', 'mse_index', 'mse_buffered'])
    page.locator('[data-group="inputs"] [data-job="assessment_a1"] .dependency-inspect').click()
    assert page.locator('#dependency-job').input_value() == 'assessment_a1'
    assert page.locator('[data-group="current"] .dependency-title').inner_text() == 'Assessment A1'
    connections(page, 'submission', [], ['qc'])
    assert 'No upstream jobs' in page.locator('[data-group="inputs"] .dependency-empty').inner_text()
    connections(page, 'mse_report', ['mse_summary'], [])
    assert 'No downstream jobs' in page.locator('[data-group="outputs"] .dependency-empty').inner_text()
    assert run_selection(page) == before, 'Dependency browsing changed the run selection or plan'


with tempfile.TemporaryDirectory() as directory, sync_playwright() as playwright:
    path = Path(directory) / 'preview.html'
    path.write_text(preview())
    browser = playwright.chromium.launch(headless=True)
    page = browser.new_page(offline=True, viewport={'width': 1440, 'height': 1000}, device_scale_factor=2)
    errors = []
    page.on('pageerror', lambda error: errors.append(str(error)))
    page.goto(path.as_uri() + '#orchestration')
    page.evaluate("""() => {
      window.orchestrationRuns = [];
      const originalCall = call;
      call = async (type, data) => {
        const input = type === 'run' ? structuredClone(data) : null;
        const result = await originalCall(type, data);
        if (input) orchestrationRuns.push({input, result: structuredClone(result)});
        return result;
      };
    }""")
    assert page.locator('#jobs-view').is_visible()
    assert page.locator('#workflow-view').is_hidden()
    assert page.locator('#jobs-view #run').count() == 1
    page.wait_for_function("document.querySelector('#mode').value === 'saved'")
    page.locator('#mode').select_option('saved')
    assert 'saved' in page.locator('#view-guide-description').inner_text()
    assert 'Output and Record' in page.locator('#view-guide-description').inner_text()
    switch_with_guide(page, 'workflow')
    assert 'saved jobs' in page.locator('#view-guide-description').inner_text()
    switch_with_guide(page, 'orchestration')
    assert page.locator('#show-tasks').inner_text().startswith('Tasks')
    assert page.locator('#workspace-title').inner_text() == 'Tasks'
    assert page.locator('.task-responsibility').count() == page.evaluate('taskGroups.length')
    page.locator('#tasks .cpue').click()
    assert page.locator('#job-table-body tr').count() == 4
    assert page.locator('tr[data-job="cpue_a"] .job-number').inner_text() == 'Job 05'
    assert page.locator('tr[data-job="cpue_report"] .job-number').inner_text() == 'Job 08'
    page.locator('tr[data-job="cpue_a"] .open-output').click()
    assert page.locator('#output-kind').text_content().startswith('Job 05 · ')
    assert page.frame_locator('#output-frame').locator('h1').inner_text() == 'CPUE analysis A'
    page.locator('#output-close').click()
    page.locator('tr[data-job="cpue_a"] .open-job-record').click()
    page.locator('#output-record:visible').wait_for()
    assert page.locator('#output-record').is_visible()
    assert page.locator('#output-record .record-heading h3').inner_text() == 'Job 05 · CPUE analysis A · Run 001'
    assert page.locator('#output-record .record-input').count() == 1
    page.locator('#output-close').click()
    page.locator('tr[data-job="cpue_report"] [data-input-job="cpue_summary"]').click()
    page.locator('#output-record:visible').wait_for()
    assert page.locator('#output-title').inner_text() == 'Compare CPUE results'
    assert page.locator('#output-record').is_visible()
    page.locator('#output-close').click()

    browse_dependencies(page)
    page.locator('#dependency-job').select_option('mse_prepare')
    card = page.locator('[data-group="current"] .dependency-card')
    assert card.locator('.job-number').inner_text() == 'Job 17'
    assert card.locator('.dependency-owner').inner_text() == 'MSE analyst'
    assert card.locator('.run-label').inner_text() == 'Run 001'
    assert card.locator('.state').inner_text() == 'Complete'
    assert 'exact input versions' in page.locator('.dependency-record-note').inner_text()
    before = run_selection(page)
    card.locator('.open-output').click()
    assert page.frame_locator('#output-frame').locator('h1').inner_text() == 'Prepare MSE'
    page.locator('#output-close').click()
    card.locator('.open-job-record').click()
    page.locator('#output-record:visible').wait_for()
    assert page.locator('#output-title').inner_text() == 'Prepare MSE'
    assert page.locator('#output-record .record-input').count() == 4
    page.locator('#output-close').click()
    assert run_selection(page) == before, 'Inspecting dependency output/record changed the run selection'

    # The saved file executes nothing. Live UI contracts use the actual HTTP
    # client with synthetic completion states, independently of model tests.
    ui = runpy.run_path(str(ROOT / 'scripts/check-browser.py'))
    mock = ui['MockCloud']()
    ui['open_live'](page, mock)
    page.locator('[data-tab="jobs"]').click()
    page.evaluate("""() => {
      window.orchestrationRuns = [];
      const originalCall = call;
      call = async (type, data) => {
        const input = type === 'run' ? structuredClone(data) : null;
        const result = await originalCall(type, data);
        if (input) orchestrationRuns.push({input, result: structuredClone(result)});
        return result;
      };
    }""")
    page.locator('#all-tasks').click()
    assert page.locator('tr[data-job="submission"] .state').inner_text() == 'Ready'
    page.locator('tr[data-job="cpue_a"] .job-name').click()
    assert page.frame_locator('#output-frame').locator('h1').inner_text() == 'No output yet'
    assert page.locator('#output-run').is_enabled()
    page.locator('#output-close').click()
    page.locator('#run').click()
    expect_run(page, 0, page.evaluate('jobs.map(job => job.key)'), 'workflow')

    # Manual handover views expose all three boundaries and preserve busy state.
    # These are UI events, explicitly not evidence of an executed transfer.
    page.locator('#handover').select_option('manual')
    for boundary, key, title, size in [
        ('data', 'cpue_a', 'Data manager → CPUE analyst', 2),
        ('cpue', 'prepare_a', 'CPUE analyst → Assessment analyst', 2),
        ('assessment', 'mse_prepare', 'Assessment analyst → MSE analyst', 1),
    ]:
        group = ['cpue_a', 'cpue_b'] if boundary == 'data' else ['prepare_a', 'prepare_b'] if boundary == 'cpue' else ['mse_prepare']
        page.evaluate("""event => {
          busy = true;
          handleEvent({...event, state: 'handover', message: 'Mocked transfer boundary'});
        }""", {'job': key, 'boundary': boundary, 'group': group})
        assert page.locator('#handover-title').inner_text() == title
        assert page.locator('#handover-panel').is_visible()
        assert page.locator('.handover-marker.active').count() == size
        assert page.locator('#run').is_disabled()
        assert page.locator('#mode').is_disabled()
        page.locator('#transfer-files').click()
        page.wait_for_function('confirmingTransfer')
        page.evaluate("""event => {
          handleEvent({...event, state: 'received', message: 'Mocked receipt'});
          busy = false; render();
        }""", {'job': key, 'group': group})
        assert page.locator('#handover-panel').is_hidden()
    page.locator('#handover').select_option('connected')
    page.evaluate("states = {}; render()")

    # A job request has different scope from the full workflow and preserves
    # all unrelated identities. Dependency browsing must never change that scope.
    page.locator('#all-tasks').click()
    before = page.evaluate('records')
    previous = page.evaluate('orchestrationRuns.length')
    page.locator('tr[data-job="cpue_summary"] .run-job').click()
    expect_run(page, previous, ['cpue_summary'], 'job')
    unchanged_records(page, before, ['cpue_summary'])
    assert page.evaluate('records.cpue_report.run_id') == 'Mock 001'
    assert page.evaluate('records.cpue_summary.run_id') == 'Mock 002'
    browse_dependencies(page)
    page.locator('#all-tasks').click()
    previous = page.evaluate('orchestrationRuns.length')
    page.locator('tr[data-job="cpue_report"] .run-job').click()
    expect_run(page, previous, ['cpue_report'], 'job')
    assert page.evaluate('records.cpue_report.inputs.cpue_summary.run_id') == 'Mock 002'

    page.locator('[data-tab="workflow"]').click()
    page.locator('.workflow-node[data-job="cpue_summary"]').click()
    page.wait_for_function("plan?.scope === 'workflow' && plan.run.length === 2")
    switch_with_guide(page, 'orchestration')
    previous = page.evaluate('orchestrationRuns.length')
    page.locator('#run').click()
    expect_run(page, previous, ['cpue_summary', 'cpue_report'], 'workflow')
    browse_dependencies(page)
    page.locator('#growth-rate').select_option('0.35')
    page.wait_for_function("settingsIntent && plan.changed.includes('assessment_a2')")
    browse_dependencies(page)
    assert page.evaluate("selected === 'cpue_summary' && currentStart() === 'assessment_a2'")
    page.locator('#growth-rate').select_option('0.30')
    page.wait_for_function('plan.changed.length === 0')

    # Unrelated settings must not be applied by a single-job request.
    page.locator('#all-tasks').click()
    page.locator('#growth-rate').select_option('0.35')
    page.wait_for_function("plan.changed.includes('assessment_a2')")
    before = page.evaluate('records')
    previous = page.evaluate('orchestrationRuns.length')
    page.locator('tr[data-job="cpue_a"] .run-job').click()
    expect_run(page, previous, ['cpue_a'], 'job')
    unchanged_records(page, before, ['cpue_a'])
    assert page.evaluate('records.assessment_a2.settings.r') == .30
    assert page.locator('#status-title').inner_text() == 'New settings · previous results kept'

    page.locator('#growth-rate').select_option('0.30')
    page.locator('#filter').select_option('1200')
    page.wait_for_function("plan.changed.includes('cpue_a')")
    previous = page.evaluate('orchestrationRuns.length')
    page.locator('tr[data-job="cpue_a"] .run-job').click()
    expect_run(page, previous, ['cpue_a'], 'job')
    for key in ['cpue_summary', 'prepare_a', 'assessment_a1', 'mse_prepare']:
        assert page.locator(f'.workflow-node[data-job="{key}"].outdated').count() == 1, key
    assert page.locator('#run-workflow').inner_text() == 'Update workflow'
    previous = page.evaluate('orchestrationRuns.length')
    descendants = ['cpue_summary', 'cpue_report', 'prepare_a', 'assessment_a1',
                   'assessment_a2', 'assessment_summary', 'assessment_report',
                   'mse_prepare', 'mse_constant', 'mse_index', 'mse_buffered', 'mse_summary', 'mse_report']
    page.locator('#run-workflow').click()
    expect_run(page, previous, descendants, 'workflow')

    resets = mock.reset_count
    page.locator('#reset').click()
    page.wait_for_function("""() => !busy && Object.keys(records).length === 0 &&
      selected === 'submission' && plan?.run.length === jobs.length && !$('run').disabled
    """)
    assert mock.reset_count == resets + 1
    page.locator('#all-tasks').click()
    previous = page.evaluate('orchestrationRuns.length')
    page.locator('tr[data-job="prepare_a"] .run-job').click()
    ancestors = ['submission', 'qc', 'database', 'extract', 'cpue_a', 'prepare_a']
    expect_run(page, previous, ancestors, 'job')
    assert set(page.evaluate('Object.keys(records)')) == set(ancestors)
    page.locator('#filter').select_option('1200')
    page.wait_for_function("plan.changed.includes('cpue_a')")
    previous = page.evaluate('orchestrationRuns.length')
    page.locator('tr[data-job="prepare_a"] .run-job').click()
    expect_run(page, previous, ['cpue_a', 'prepare_a'], 'job')
    assert set(page.evaluate('Object.keys(records)')) == set(ancestors)
    browse_dependencies(page)
    for width in [1440, 1100, 900, 768, 650, 390, 320]:
        page.set_viewport_size({'width': width, 'height': 1000})
        assert page.evaluate("document.querySelector('#jobs-view').scrollWidth <= document.querySelector('#jobs-view').clientWidth"), width
        assert page.evaluate("""() => {
          const cards = [...document.querySelectorAll('.dependency-card')].map(card => card.getBoundingClientRect());
          return cards.every((a, i) => cards.every((b, j) => i === j ||
            a.right <= b.left || b.right <= a.left || a.bottom <= b.top || b.bottom <= a.top));
        }"""), width
    assert not errors, errors
    browser.close()
print('PASS: saved orchestration/dependency records; mocked Live scopes, retained lineage, '
      'missing/stale ancestors, setting isolation, three handover views and mobile reflow. '
      'Native/hosted gates independently validate actual container calculations.')
