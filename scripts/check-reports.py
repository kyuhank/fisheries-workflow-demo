"""Check generated reports, retained inputs and revised results through the UI."""
import argparse
import json
from pathlib import Path

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[1]
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--online', action='store_true', help='Run on the public service without login.')
args = parser.parse_args()
mode = 'online' if args.online else 'offline'
destination = ROOT / '.test-output' / f'reports-{mode}'
destination.mkdir(parents=True, exist_ok=True)


def run(page):
    page.locator('#run:enabled').wait_for(timeout=90000)
    previous = page.evaluate('latestRun')
    page.locator('#run').click()
    page.wait_for_function("""previous => !busy &&
      (latestRun !== previous || document.querySelector('#status').classList.contains('failed'))
    """, arg=previous, timeout=600000)
    assert page.locator('#status-title').inner_text() == 'Results are ready', \
        page.locator('#status-message').inner_text()
    print(f'{mode}: {page.evaluate("latestRun")} completed', flush=True)
    return page.evaluate('records')


def inspect(page, key, report=False):
    page.locator('[data-tab="jobs"]').click()
    page.locator('#all-tasks').click()
    page.locator(f'tr[data-job="{key}"] .open-output').click()
    frame = page.frame_locator('#output-frame')
    frame.locator('h1').wait_for()
    article = frame.locator('.narrative-report')
    assert article.count() == int(report), key
    if report:
        assert article.get_attribute('data-report') == key
        assert article.locator('h2').all_text_contents() == ['Methods', 'Results', 'Interpretation']
        assert article.locator('svg').count() == 1
        assert article.locator('table').count() == 0
    body = frame.locator('body').inner_text()
    assert 'Analysis record' in body and 'Synthetic' in body
    output = page.evaluate('currentOutput')
    assert output['record']['job'] == key
    if key == 'extract':
        assert 'Observations → CPUE' in body and 'Annual catch → assessment inputs' in body
        selected = output['output']
        assert all(set(row) == {'set_id', 'year', 'vessel', 'hooks', 'catch_n'}
                   and row['hooks'] > 0 and row['catch_n'] >= 0 for row in selected['sets'])
        assert all(set(row) == {'year', 'catch_t'} for row in selected['catch'])
    frame.locator('body').screenshot(path=str(destination / f'{key}.png'))
    if report:
        page.locator('[data-output="record"]').click()
        assert page.locator('.record-input').count() == 1
        if args.online:
            assert 'Docker image' in page.locator('.record-cards').inner_text()
            assert '@sha256:' in output['record']['execution']['container']
    page.locator('#output-close').click()
    return body, output


with sync_playwright() as playwright:
    browser = playwright.chromium.launch(headless=True)
    context = browser.new_context(offline=not args.online,
                                  viewport={'width': 1440, 'height': 1100})
    page = context.new_page()
    errors = []
    page.on('pageerror', lambda error: errors.append(str(error)))
    page.goto('https://kyuhank.github.io/fisheries-workflow-demo/' if args.online
              else (ROOT / 'docs/offline.html').as_uri())
    if not args.online:
        page.locator('#mode').select_option('live')
    page.locator('#run:enabled').wait_for(timeout=90000)
    assert page.locator('#mode').input_value() == ('cloud' if args.online else 'live')
    baseline = run(page)
    for key in ['extract', 'cpue_summary', 'assessment_summary']:
        inspect(page, key)
    cpue_before, _ = inspect(page, 'cpue_report', True)
    assessment_before, _ = inspect(page, 'assessment_report', True)

    page.locator('#filter').select_option('1200')
    cpue_records = run(page)
    assert cpue_records['extract'] == baseline['extract']
    assert cpue_records['cpue_b'] == baseline['cpue_b']
    assert cpue_records['assessment_b2'] == baseline['assessment_b2']
    cpue_after, _ = inspect(page, 'cpue_report', True)
    assert cpue_after != cpue_before

    page.locator('#mortality').select_option('0.35')
    mortality_records = run(page)
    assert {key for key in mortality_records
            if mortality_records[key] != cpue_records[key]} == {
                'assessment_a2', 'assessment_b2', 'assessment_summary', 'assessment_report'}
    assessment_after, output = inspect(page, 'assessment_report', True)
    assert assessment_after != assessment_before and '0.35' in assessment_after
    assert output['record']['inputs']['assessment_summary']['run_id'] == page.evaluate('latestRun')

    page.locator('#mode').select_option('saved')
    for key in ['cpue_report', 'assessment_report']:
        inspect(page, key, True)
    assert not errors, errors
    result = {'mode': mode, 'distinct_reports': True, 'settings_updates': True,
              'retained_inputs': True, 'saved_reports': True, 'page_errors': errors,
              'execution': mortality_records['assessment_report'].get('execution'),
              'source': mortality_records['assessment_report'].get('source')}
    (destination / 'checks.json').write_text(json.dumps(result, indent=2) + '\n')
    browser.close()
print('Passed: distinct reports, revised results, retained inputs and saved examples.')
