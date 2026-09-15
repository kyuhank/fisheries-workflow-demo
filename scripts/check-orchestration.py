"""Check the built offline demo, shared job views and recorded input links."""
from pathlib import Path
import json
import tempfile

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[1]
ARTIFACTS = ROOT / '.test-output'
ARTIFACTS.mkdir(exist_ok=True)


def preview():
    # Build first: the graph, saved examples and executable code must match.
    return (ROOT / 'docs/offline.html').read_text()


def run_selection(page):
    return page.evaluate('({selected, settingsIntent, completedRun, plan, settings: settings()})')


def expect_run(page, previous, expected, scope):
    page.wait_for_function("""previous => !busy && orchestrationRuns.length === previous + 1 &&
      document.querySelector('#status-title').textContent === 'Results are ready'
    """, arg=previous, timeout=90000)
    page.locator('#run:enabled').wait_for()
    run = page.evaluate('orchestrationRuns.at(-1)')
    assert run['input']['scope'] == scope, run['input']
    assert run['result']['run'] == expected, run['result']['run']
    assert page.evaluate('completedRun.run') == expected
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
    page.wait_for_function("document.querySelector('#mode').value === 'live'")
    page.locator('#mode').select_option('saved')
    page.locator('[data-tab="jobs"]').click()
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

    page.locator('#mode').select_option('live')
    page.locator('#run:enabled').wait_for(timeout=90000)
    assert page.locator('[data-group="current"] .open-output').is_disabled()
    assert page.locator('[data-group="current"] .open-job-record').is_disabled()
    assert page.locator('[data-group="current"] .state').inner_text() == 'Waiting'
    page.locator('#all-tasks').click()
    assert page.locator('tr[data-job="submission"] .state').inner_text() == 'Ready'
    page.locator('tr[data-job="cpue_a"] .job-name').click()
    assert 'Job 05' in page.locator('#output-kind').text_content()
    assert page.frame_locator('#output-frame').locator('h1').inner_text() == 'No output yet'
    assert page.locator('#output-run').is_enabled()
    page.locator('#output-close').click()
    assert 'Extract data' in page.locator('tr[data-job="cpue_a"] .progress-detail').inner_text()
    page.locator('#handover').select_option('manual')
    assert page.locator('[data-tab="jobs"]').inner_text() == 'Job outputs'
    assert 'without shared orchestration' in page.locator('#workspace-description').inner_text()
    assert page.locator('.handover-marker').count() == 5
    page.locator('#run').click()
    page.locator('#handover-panel:visible').wait_for(timeout=30000)
    page.locator('#task-filter').select_option('cpue')
    for key in ['cpue_a', 'cpue_b']:
        assert page.locator(f'tr[data-job="{key}"] .state').inner_text() == 'Awaiting file'
        assert 'Confirm file transfer' in page.locator(f'tr[data-job="{key}"] .progress-detail').inner_text()
    page.locator('tr[data-job="cpue_a"] [data-input-job="extract"]').click()
    page.locator('#output-record:visible').wait_for()
    assert page.locator('#output-record').is_visible()
    page.locator('#output-close').click()
    assert page.locator('#handover-panel').is_visible()
    page.locator('#transfer-files').click()
    page.locator('tr[data-job="cpue_a"].running').wait_for()
    page.locator('#jobs-view').screenshot(path=str(ARTIFACTS / 'orchestration-running.png'))
    page.wait_for_function("states.cpue_report === 'complete' && waitingTransfer?.boundary === 'cpue'", timeout=30000)
    page.locator('#task-filter').select_option('assessment')
    page.locator('#job-status-filter').select_option('handover')
    assert page.locator('#job-table-body tr').count() == 2
    assert page.locator('#handover-note').is_hidden()
    page.screenshot(path=str(ARTIFACTS / 'orchestration-manual-wait.png'), full_page=True)
    page.locator('#transfer-files').click()
    page.wait_for_function("states.assessment_report === 'complete' && waitingTransfer?.boundary === 'assessment'", timeout=30000)
    assert page.locator('#handover-title').inner_text() == 'Assessment analyst → MSE analyst'
    page.locator('#task-filter').select_option('mse')
    assert page.locator('#job-table-body tr').count() == 1
    assert page.locator('tr[data-job="mse_prepare"] .state').inner_text() == 'Awaiting file'
    assert page.locator('.handover-marker.active[data-boundary="assessment"]').count() == 1
    page.locator('#show-dependencies').click()
    page.locator('#dependency-job').select_option('mse_prepare')
    assert 'separate workspaces' in page.locator('#workspace-description').inner_text()
    assert page.locator('[data-group="inputs"] .dependency-card.complete').count() == 4
    assert page.locator('[data-group="current"] .state').inner_text() == 'Awaiting file'
    assert 'Confirm file transfer' in page.locator('[data-group="current"] .dependency-progress').inner_text()
    assert page.locator('[data-group="outputs"] .dependency-card.waiting').count() == 3
    assert page.locator('[data-group="current"] .open-output').is_disabled()
    assert page.locator('#handover-panel').is_visible()
    assert page.evaluate("busy && states.assessment_summary === 'complete' && !records.mse_prepare")
    page.locator('#jobs-view').screenshot(path=str(ARTIFACTS / 'orchestration-dependencies-handover.png'))
    page.locator('#transfer-files').click()
    page.wait_for_function("document.querySelector('#status-title').textContent === 'Results are ready'", timeout=30000)
    assert page.evaluate('orchestrationRuns.at(-1).input.scope') == 'workflow'

    page.locator('#handover').select_option('connected')
    page.locator('#all-tasks').click()
    page.locator('#job-status-filter').select_option('')
    page.locator('#task-filter').select_option('cpue')
    page.locator('tr[data-job="cpue_summary"] .job-name').click()
    page.locator('#output-dialog:visible').wait_for()
    assert page.locator('#output-title').inner_text() == 'Compare CPUE results'
    assert 'Job 07' in page.locator('#output-kind').text_content()
    assert page.locator('#output-run').inner_text() == 'Run this job'
    previous = page.evaluate('orchestrationRuns.length')
    before = page.evaluate('records')
    page.locator('#output-run').click()
    page.wait_for_function("busy && selected === 'cpue_summary'")
    assert page.locator('#output-dialog').is_hidden()
    assert page.locator('#jobs-view').is_visible()
    assert page.locator('tr[data-job="cpue_summary"] .run-job').is_disabled()
    page.locator('[data-tab="workflow"]').click()
    assert page.locator('#run-controls').locator('#run').count() == 1
    assert page.locator('#workflow-view').is_visible()
    assert set(page.locator('.workflow-node.in-path').evaluate_all('nodes => nodes.map(n => n.dataset.job)')) == {'cpue_summary'}
    page.go_back()
    assert page.locator('#jobs-view').is_visible()
    assert page.locator('#jobs-view #run').count() == 1
    expect_run(page, previous, ['cpue_summary'], 'job')
    unchanged_records(page, before, ['cpue_summary'])
    assert page.evaluate('records.cpue_report.run_id') == 'Run 001'
    assert page.locator('tr[data-job="cpue_a"] .state').inner_text() == 'Reused'
    assert page.locator('tr[data-job="cpue_summary"] .state').inner_text() == 'Complete'
    assert page.locator('tr[data-job="cpue_a"] .run-label').inner_text() == 'Run 001'
    assert page.locator('tr[data-job="cpue_summary"] .run-label').inner_text() == 'Run 002'
    page.locator('#jobs-view').screenshot(path=str(ARTIFACTS / 'orchestration-cpue-jobs.png'))
    page.locator('.workspace-content').screenshot(path=str(ARTIFACTS / 'paper-jobs.png'))
    page.locator('tr[data-job="cpue_summary"] .open-job-record').click()
    page.locator('#output-record:visible').wait_for()
    assert page.locator('#output-title').inner_text() == 'Compare CPUE results'
    assert page.locator('#output-record .record-heading h3').inner_text() == 'Job 07 · Compare CPUE results · Run 002'
    page.locator('#output-record').screenshot(path=str(ARTIFACTS / 'paper-record.png'))
    (ARTIFACTS / 'paper-screenshot-record.json').write_text(page.evaluate('JSON.stringify(currentOutput.record, null, 2)'))
    page.locator('#output-close').click()

    assert page.evaluate('completedRun !== null && completedRun.run.length === 1')
    previous = page.evaluate('orchestrationRuns.length')
    page.locator('tr[data-job="cpue_report"] .run-job').click()
    expect_run(page, previous, ['cpue_report'], 'job')
    assert page.evaluate("records.cpue_summary.run_id") == 'Run 002'
    assert page.evaluate("records.cpue_report.inputs.cpue_summary.run_id") == 'Run 002'
    previous = page.evaluate('orchestrationRuns.length')
    before = page.evaluate('records')
    page.locator('tr[data-job="cpue_summary"] .run-job').click()
    expect_run(page, previous, ['cpue_summary'], 'job')
    unchanged_records(page, before, ['cpue_summary'])
    browse_dependencies(page)
    assert page.evaluate('completedRun !== null && completedRun.run.length === 1')

    # Selecting the diagram's starting job requests a workflow update, preserving
    # the separate behaviour of the main controls and their shared view state.
    page.locator('[data-tab="workflow"]').click()
    page.locator('.workflow-node[data-job="cpue_summary"]').click()
    page.wait_for_function("plan?.scope === 'workflow' && plan.run.length === 2")
    page.locator('#run:enabled').wait_for()
    page.locator('[data-tab="jobs"]').click()
    previous = page.evaluate('orchestrationRuns.length')
    page.locator('#run').click()
    expect_run(page, previous, ['cpue_summary', 'cpue_report'], 'workflow')
    browse_dependencies(page)
    assert page.evaluate('completedRun !== null && completedRun.run.length === 2')
    page.locator('#mortality').select_option('0.35')
    page.wait_for_function("settingsIntent && plan.changed.includes('assessment_a2')")
    browse_dependencies(page)
    assert page.evaluate("settingsIntent && selected === 'cpue_summary' && currentStart() === 'assessment_a2'")
    page.locator('#dependency-job').select_option('mse_prepare')
    assert page.locator('[data-group="current"] .state').inner_text() == 'Inputs changed'
    assert page.locator('[data-group="inputs"] .dependency-card.outdated').count() == 2
    page.locator('#mortality').select_option('0.30')
    page.wait_for_function('plan.changed.length === 0')
    page.locator('#show-tasks').click()
    assert '2 complete · 2 reused' in page.locator('#tasks .cpue .task-footer').inner_text()
    assert page.locator('#tasks .data .task-status').inner_text() == 'Reused'
    page.locator('#jobs-view').screenshot(path=str(ARTIFACTS / 'orchestration-overview.png'))
    page.locator('#tasks .cpue').click()
    page.set_viewport_size({'width': 390, 'height': 844})
    assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')
    assert page.locator('tr[data-job="cpue_a"] .open-job-record').is_visible()
    page.locator('#jobs-view').screenshot(path=str(ARTIFACTS / 'orchestration-mobile.png'))
    page.locator('#show-dependencies').click()
    page.locator('#dependency-job').select_option('mse_prepare')
    for width in [1440, 1100, 900, 768, 650, 390, 320]:
        page.set_viewport_size({'width': width, 'height': 1000})
        assert page.evaluate("document.querySelector('#jobs-view').scrollWidth <= document.querySelector('#jobs-view').clientWidth"), width
        assert page.evaluate("""() => {
          const cards = [...document.querySelectorAll('.dependency-card')].map(card => card.getBoundingClientRect());
          return cards.every((a, i) => cards.every((b, j) => i === j ||
            a.right <= b.left || b.right <= a.left || a.bottom <= b.top || b.bottom <= a.top));
        }"""), f'Dependency cards overlap at {width}px'
        if width == 1440:
            page.locator('#jobs-view').screenshot(path=str(ARTIFACTS / 'orchestration-dependencies-mse.png'))
        if width == 390:
            page.locator('#jobs-view').screenshot(path=str(ARTIFACTS / 'orchestration-dependencies-mobile.png'))

    # A job request must not apply unrelated changes elsewhere in the workflow.
    page.set_viewport_size({'width': 1440, 'height': 1000})
    page.locator('#all-tasks').click()
    page.locator('#mortality').select_option('0.35')
    page.wait_for_function("plan.changed.includes('assessment_a2')")
    previous = page.evaluate('orchestrationRuns.length')
    before = page.evaluate('records')
    page.locator('tr[data-job="cpue_a"] .run-job').click()
    expect_run(page, previous, ['cpue_a'], 'job')
    unchanged_records(page, before, ['cpue_a'])

    # Revised inputs leave dependent records in place and mark their jobs stale.
    page.locator('#mortality').select_option('0.30')
    page.locator('#filter').select_option('1200')
    page.wait_for_function("plan.changed.includes('cpue_a')")
    previous = page.evaluate('orchestrationRuns.length')
    before = page.evaluate('records')
    page.locator('tr[data-job="cpue_a"] .run-job').click()
    expect_run(page, previous, ['cpue_a'], 'job')
    unchanged_records(page, before, ['cpue_a'])
    for key in ['cpue_summary', 'prepare_a', 'assessment_a1', 'mse_prepare']:
        assert page.locator(f'.workflow-node[data-job="{key}"].outdated').count() == 1, key
    assert page.locator('#run-workflow').inner_text() == 'Update workflow'
    previous = page.evaluate('orchestrationRuns.length')
    before = page.evaluate('records')
    page.locator('#run-workflow').click()
    descendants = ['cpue_summary', 'cpue_report', 'prepare_a', 'assessment_a1',
                   'assessment_a2', 'assessment_summary', 'assessment_report',
                   'mse_prepare', 'mse_constant', 'mse_index', 'mse_buffered',
                   'mse_summary', 'mse_report']
    expect_run(page, previous, descendants, 'workflow')
    unchanged_records(page, before, descendants)

    # On a fresh workspace, build only the selected job's missing ancestors.
    page.locator('#reset').click()
    page.locator('#run:enabled').wait_for()
    page.locator('#all-tasks').click()
    previous = page.evaluate('orchestrationRuns.length')
    page.locator('tr[data-job="prepare_a"] .run-job').click()
    ancestors = ['submission', 'qc', 'database', 'extract', 'cpue_a', 'prepare_a']
    expect_run(page, previous, ancestors, 'job')
    assert set(page.evaluate('Object.keys(records)')) == set(ancestors)
    assert page.locator('.workflow-node.retained').count() == 0

    # A selected job also rebuilds a stale ancestor without running its peers,
    # reports or descendants, including other jobs still missing in this workspace.
    page.locator('#filter').select_option('1200')
    page.wait_for_function("plan.changed.includes('cpue_a')")
    page.locator('#all-tasks').click()
    previous = page.evaluate('orchestrationRuns.length')
    before = page.evaluate('records')
    page.locator('tr[data-job="prepare_a"] .run-job').click()
    expect_run(page, previous, ['cpue_a', 'prepare_a'], 'job')
    unchanged_records(page, before, ['cpue_a', 'prepare_a'])
    assert set(page.evaluate('Object.keys(records)')) == set(ancestors)
    assert not errors, errors
    browser.close()
print('PASS: built orchestration UI, owners/readiness, linked input records, output/record actions, '
      'three manual boundaries, independent assessment reporting, dependency browsing without changing '
      'run selection/settings/completion/plans, single-job runs with missing/stale ancestors, explicit '
      'workflow updates, source/terminal jobs, reused run identities and mobile reflow.')
