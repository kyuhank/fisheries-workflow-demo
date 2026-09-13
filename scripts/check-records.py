"""Check input tracing and a real rerun from a job's recorded settings."""
import argparse
import json
from pathlib import Path
import tempfile

from playwright.sync_api import expect, sync_playwright

ROOT = Path(__file__).resolve().parents[1]
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--online', action='store_true', help='Use the anonymous hosted runner.')
args = parser.parse_args()
(ROOT / '.test-output').mkdir(exist_ok=True)

with sync_playwright() as playwright, tempfile.TemporaryDirectory() as directory:
    browser = playwright.chromium.launch(headless=True)
    context = browser.new_context(offline=not args.online, accept_downloads=True,
                                  viewport={'width': 1440, 'height': 1000})
    page = context.new_page()
    errors = []
    page.on('pageerror', lambda error: errors.append(str(error)))
    page.goto((ROOT / 'docs/offline.html').as_uri())
    if not args.online:
        page.locator('#mode').select_option('live')
    page.locator('#run:enabled').wait_for(timeout=90000)
    page.locator('#run').click()
    page.wait_for_function("!busy && (!!records.assessment_a2 || document.querySelector('#status').classList.contains('failed'))", timeout=600000)
    assert page.locator('#status-title').inner_text() == 'Results are ready'
    print('Initial execution completed.', flush=True)
    page.locator('[data-tab="jobs"]').click()
    page.locator('#all-tasks').click()
    page.locator('tr[data-job="assessment_a2"] .open-output').click()
    page.locator('[data-output="record"]').click()
    assert 'assessment_a2 · Run 001' in page.locator('.record-heading').inner_text()
    assert 'Prepare inputs A' in page.locator('.record-input').inner_text()
    if args.online:
        assert 'Docker image' in page.locator('.record-cards').inner_text()
        assert '@sha256:' in page.locator('.record-details pre').text_content()
        assert page.locator('.record-image-digest').inner_text() == page.evaluate('currentOutput.record.execution.container.split("@")[1]')
        assert page.get_by_role('link', name='Open actual run').get_attribute('href').endswith(str(page.evaluate('currentOutput.record.execution.github_run')))
    page.locator('.record-input').click()
    expect(page.locator('.record-heading')).to_contain_text('prepare_a · Run 001')
    page.get_by_role('button', name='CPUE analysis A Run 001').click()
    expect(page.locator('.record-heading')).to_contain_text('cpue_a · Run 001')
    with page.expect_download() as transfer:
        page.locator('#download-job-record').click()
    path = Path(directory) / 'record.json'
    transfer.value.save_as(path)
    saved = json.loads(path.read_text())
    assert set(saved['jobs']) == {'submission', 'qc', 'database', 'extract', 'cpue_a'}
    assert all(record['code'] and record['software'] for record in saved['jobs'].values())
    page.locator('#output-close').click()
    # A changed form must not silently replace the settings of the reference job.
    page.locator('#filter').select_option('1200')
    page.locator('#mortality').select_option('0.35')
    page.locator('tr[data-job="cpue_a"] .open-output').click()
    page.locator('[data-output="record"]').click()
    page.locator('#reproduce-job').click()
    page.wait_for_function("document.querySelector('.record-comparison') || (!busy && document.querySelector('#status').classList.contains('failed'))", timeout=600000)
    assert page.locator('.record-comparison').count(), page.locator('#status-message').inner_text()
    assert page.locator('.record-comparison strong').inner_text() == 'Reproduced · output agrees'
    assert page.locator('#filter').input_value() == '0'
    assert page.evaluate('currentOutput.comparison.new_run') == 'Run 002'
    assert page.evaluate('currentOutput.comparison.changed_materials') == []
    assert page.evaluate('Object.values(records).every(record => record.run_id === "Run 002")')
    page.locator('#output-close').click()
    page.locator('tr[data-job="cpue_a"] .open-output').click()
    page.locator('[data-output="record"]').click()
    expect(page.locator('.record-comparison strong')).to_have_text('Reproduced · output agrees')
    assert page.evaluate('compareOutput({x:1}, {x:1.01})') == 'output.x'
    assert page.evaluate('compareOutput({x:1}, {x:1.0000001})') is None
    assert page.evaluate("""() => {
      const earlier = structuredClone(records);
      earlier.extract.run_id = 'An earlier run';
      try { traceInputs('cpue_a', earlier); } catch (error) {
        return error.message.includes('recorded version');
      }
      return false;
    }""")
    assert page.evaluate("""() => {
      const changed = structuredClone(records);
      changed.cpue_a.software.python = 'different';
      return compareMaterials(records, changed);
    }""") == ['software']
    page.screenshot(path=str(ROOT / '.test-output/job-record.png'), full_page=True)
    page.set_viewport_size({'width': 390, 'height': 844})
    assert page.evaluate("document.querySelector('#output-record').scrollWidth <= document.querySelector('#output-record').clientWidth")
    result = page.evaluate('currentOutput.comparison')
    result['mode'] = 'online' if args.online else 'offline'
    result['github_run'] = page.evaluate('currentOutput.record.execution?.github_run || null')
    assert not errors, errors
    (ROOT / '.test-output').mkdir(exist_ok=True)
    (ROOT / f'.test-output/record-{result["mode"]}.json').write_text(json.dumps(result, indent=2) + '\n')
    browser.close()
print('Passed: recorded-input navigation, complete context, restored settings, real rerun, output comparison and stale-input rejection.')
