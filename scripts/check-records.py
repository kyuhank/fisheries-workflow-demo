"""Check saved input tracing; --online also checks a real container rerun."""
import argparse
import json
from pathlib import Path
import tempfile

from playwright.sync_api import expect, sync_playwright

ROOT = Path(__file__).resolve().parents[1]
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--online', action='store_true', help='Use the anonymous hosted container runner.')
args = parser.parse_args()
(ROOT / '.test-output').mkdir(exist_ok=True)

with sync_playwright() as playwright, tempfile.TemporaryDirectory() as directory:
    browser = playwright.chromium.launch(headless=True)
    context = browser.new_context(offline=not args.online, accept_downloads=True,
                                  viewport={'width': 1440, 'height': 1000})
    page = context.new_page()
    errors = []
    page.on('pageerror', lambda error: errors.append(str(error)))
    page.goto('https://kyuhank.github.io/fisheries-workflow-demo/' if args.online
              else (ROOT / 'docs/offline.html').as_uri())
    if args.online:
        page.locator('#run:enabled').wait_for(timeout=90000)
        page.locator('#run').click()
        page.wait_for_function("!busy && (!!records.assessment_a2 || $('status').classList.contains('failed'))", timeout=600000)
        assert page.locator('#status-title').inner_text() == 'Results are ready'
    else:
        page.wait_for_function("mode === 'saved'")
    page.locator('[data-tab="jobs"]').click()
    page.locator('#all-tasks').click()
    page.locator('tr[data-job="assessment_a2"] .open-output').click()
    page.locator('[data-output="record"]').click()
    expect(page.locator('.record-heading')).to_contain_text('Job 12 · Assessment A2 · Run 001')
    assert 'Prepare inputs A' in page.locator('.record-input').inner_text()
    assert page.evaluate('Object.hasOwn(currentOutput.record.code, "jobs/assessment_a2/run.R")')
    commit = page.evaluate('currentOutput.record.source.commit')
    assert page.locator('a.record-source').filter(has_text='Job code & guide').get_attribute('href').endswith('/' + commit + '/jobs/assessment_a2')
    assert page.locator('.record-image-digest').inner_text() == page.evaluate('currentOutput.record.execution.container.split("@")[1]')
    assert page.locator('.record-image-link').get_attribute('href') == 'https://github.com/orgs/pacificcommunity/packages/container/package/fisheries-workflow'
    page.locator('.record-input').click()
    expect(page.locator('.record-heading')).to_contain_text('Job 09 · Prepare inputs A · Run 001')
    page.get_by_role('button', name='CPUE analysis A Run 001').click()
    expect(page.locator('.record-heading')).to_contain_text('Job 05 · CPUE analysis A · Run 001')
    with page.expect_download() as transfer:
        page.locator('#download-job-record').click()
    path = Path(directory) / 'record.json'
    transfer.value.save_as(path)
    saved = json.loads(path.read_text())
    assert set(saved['jobs']) == {'submission', 'qc', 'database', 'extract', 'cpue_a'}
    assert all(record['code'] and record['software'] and record['execution']['container'] for record in saved['jobs'].values())
    assert page.evaluate('compareOutput({x:1}, {x:1.01})') == 'output.x'
    assert page.evaluate('compareOutput({x:1}, {x:1.0000001})') is None
    assert page.evaluate("""() => {
      const earlier = structuredClone(records); earlier.extract.run_id = 'Earlier';
      try { traceInputs('cpue_a', earlier); } catch (error) { return error.message.includes('recorded version'); }
      return false;
    }""")
    assert page.evaluate("""() => {
      const changed = structuredClone(records); changed.cpue_a.software.R = 'different';
      return compareMaterials(records, changed);
    }""") == ['software']
    if args.online:
        page.locator('#output-close').click()
        page.locator('#filter').select_option('1200')
        page.locator('#growth-rate').select_option('0.35')
        page.locator('tr[data-job="cpue_a"] .open-output').click()
        page.locator('[data-output="record"]').click()
        page.locator('#reproduce-job').click()
        page.wait_for_function("document.querySelector('.record-comparison') || (!busy && $('status').classList.contains('failed'))", timeout=600000)
        assert page.locator('.record-comparison strong').inner_text() == 'Reproduced · output agrees'
        assert page.locator('#filter').input_value() == '0'
        assert page.evaluate('currentOutput.comparison.changed_materials') == []
        result = page.evaluate('currentOutput.comparison')
    else:
        assert page.locator('#reproduce-job').is_disabled()
        result = {'saved_trace': True, 'container_provenance': True, 'real_rerun': 'not requested'}
    page.set_viewport_size({'width': 390, 'height': 844})
    assert page.evaluate("$('output-record').scrollWidth <= $('output-record').clientWidth")
    assert not errors, errors
    result['mode'] = 'online' if args.online else 'saved'
    (ROOT / f'.test-output/record-{result["mode"]}.json').write_text(json.dumps(result, indent=2) + '\n')
    browser.close()
print('PASS: recorded-input navigation, source/image context, downloaded lineage and stale-input rejection.'
      + (' Real container rerun also passed.' if args.online else ' Saved mode executes nothing.'))
