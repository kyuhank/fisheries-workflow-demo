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


with tempfile.TemporaryDirectory() as directory, sync_playwright() as playwright:
    path = Path(directory) / 'preview.html'
    path.write_text(preview())
    browser = playwright.chromium.launch(headless=True)
    page = browser.new_page(offline=True, viewport={'width': 1440, 'height': 1000}, device_scale_factor=2)
    errors = []
    page.on('pageerror', lambda error: errors.append(str(error)))
    page.goto(path.as_uri())
    page.wait_for_function("document.querySelector('#mode').value === 'live'")
    page.locator('#mode').select_option('saved')
    page.locator('[data-tab="jobs"]').click()
    assert page.locator('.task-responsibility').count() == page.evaluate('taskGroups.length')
    page.locator('#tasks .cpue').click()
    assert page.locator('#job-table-body tr').count() == 4
    page.locator('tr[data-job="cpue_a"] .open-output').click()
    assert page.frame_locator('#output-frame').locator('h1').inner_text() == 'CPUE analysis A'
    page.locator('#output-close').click()
    page.locator('tr[data-job="cpue_a"] .open-job-record').click()
    page.locator('#output-record:visible').wait_for()
    assert page.locator('#output-record').is_visible()
    assert page.locator('#output-record .record-input').count() == 1
    page.locator('#output-close').click()
    page.locator('tr[data-job="cpue_report"] [data-input-job="cpue_summary"]').click()
    page.locator('#output-record:visible').wait_for()
    assert page.locator('#output-title').inner_text() == 'Compare CPUE results'
    assert page.locator('#output-record').is_visible()
    page.locator('#output-close').click()

    page.locator('#mode').select_option('live')
    page.locator('#run:enabled').wait_for(timeout=90000)
    page.locator('#all-tasks').click()
    assert page.locator('tr[data-job="submission"] .state').inner_text() == 'Ready'
    assert 'Extract data' in page.locator('tr[data-job="cpue_a"] .progress-detail').inner_text()
    page.locator('#handover').select_option('manual')
    assert page.locator('[data-tab="jobs"]').inner_text() == 'Job outputs'
    assert 'without shared orchestration' in page.locator('#workspace-description').inner_text()
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
    page.wait_for_function("document.querySelector('#status-title').textContent === 'Results are ready'", timeout=30000)

    page.locator('#handover').select_option('connected')
    page.locator('#job-status-filter').select_option('')
    page.locator('#task-filter').select_option('cpue')
    page.locator('tr[data-job="cpue_summary"] .job-name').click()
    page.wait_for_function("plan.run.length === 2")
    page.locator('#run').click()
    page.wait_for_function("document.querySelector('#status-title').textContent === 'Results are ready'", timeout=30000)
    assert page.locator('tr[data-job="cpue_a"] .state').inner_text() == 'Reused'
    assert page.locator('tr[data-job="cpue_summary"] .state').inner_text() == 'Complete'
    assert page.locator('tr[data-job="cpue_a"] .run-label').inner_text() == 'Run 001'
    assert page.locator('tr[data-job="cpue_summary"] .run-label').inner_text() == 'Run 002'
    page.locator('#jobs-view').screenshot(path=str(ARTIFACTS / 'orchestration-cpue-jobs.png'))
    page.locator('.workspace-content').screenshot(path=str(ARTIFACTS / 'paper-jobs.png'))
    page.locator('tr[data-job="cpue_summary"] .open-job-record').click()
    page.locator('#output-record:visible').wait_for()
    assert page.locator('#output-title').inner_text() == 'Compare CPUE results'
    assert page.locator('#output-record .record-heading h3').inner_text() == 'cpue_summary · Run 002'
    page.locator('#output-record').screenshot(path=str(ARTIFACTS / 'paper-record.png'))
    (ARTIFACTS / 'paper-screenshot-record.json').write_text(page.evaluate('JSON.stringify(currentOutput.record, null, 2)'))
    page.locator('#output-close').click()
    page.locator('#show-tasks').click()
    assert '2 complete · 2 reused' in page.locator('#tasks .cpue .task-footer').inner_text()
    assert page.locator('#tasks .data .task-status').inner_text() == 'Reused'
    page.locator('#jobs-view').screenshot(path=str(ARTIFACTS / 'orchestration-overview.png'))
    page.locator('#tasks .cpue').click()
    page.set_viewport_size({'width': 390, 'height': 844})
    assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')
    assert page.locator('tr[data-job="cpue_a"] .open-job-record').is_visible()
    page.locator('#jobs-view').screenshot(path=str(ARTIFACTS / 'orchestration-mobile.png'))
    assert not errors, errors
    browser.close()
print('PASS: built orchestration UI, owners/readiness, linked input records, output/record actions, '
      'manual transfers, active rows, reused run identities and mobile reflow.')
