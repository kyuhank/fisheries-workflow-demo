"""Check generated reports, retained inputs and revised results through the UI."""
import argparse
import json
from pathlib import Path

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[1]
JOB_KEYS = [job['key'] for job in json.loads((ROOT / 'workflow/jobs.json').read_text())['jobs']]
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--online', action='store_true', help='Run on the public service without login.')
args = parser.parse_args()
mode = 'online' if args.online else 'saved'
destination = ROOT / '.test-output' / f'reports-{mode}'
destination.mkdir(parents=True, exist_ok=True)
MSE_JOBS = {
    'mse_prepare', 'mse_constant', 'mse_index', 'mse_buffered',
    'mse_summary', 'mse_report',
}


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
    if report:
        assert len(frame.locator('h2').all_text_contents()) >= 2, key
        assert frame.locator('svg, img').count() >= 1, key
    body = frame.locator('body').inner_text()
    output = page.evaluate('currentOutput')
    assert output['record']['job'] == key
    assert output['record']['data_source']['cpue_scope'].startswith('Fiji fleet;')
    assert 'Synthetic fisheries workflow' not in body
    rendering = output['record']['report_rendering']
    assert rendering['engine'] == 'Quarto' and rendering['quarto_executed'] is True, key
    assert frame.locator('details, summary').count() == 0, key
    if not report:
        assert rendering['presentation_source'] == 'workflow/results.qmd', key
        assert rendering['execution_engine'] == 'static', key
        assert 'report-body.html' in rendering['artifacts'], key
        assert frame.locator('svg').count() <= 2, key
        assert frame.locator('pre').count() == 0, key
    if key in ('cpue_a', 'cpue_b', 'cpue_summary'):
        assert 'Standardised' in body and 'Nominal' in body, key
        assert frame.locator('svg').first.get_attribute('aria-label') == 'Fish per 1,000 hooks', key
        assert 'same selected rows' in body, key
    if key == 'cpue_summary':
        assert 'An A-only effort filter does not apply to B' in body
    if key.startswith('assessment_') and key[-2:] in ('a1', 'a2', 'b1', 'b2'):
        assert 'Observed CPUE' in body and 'Fitted CPUE' in body and 'Biomass trajectory' in body, key
        assert frame.locator('svg').count() == 2, key
    if key == 'mse_summary':
        assert frame.locator('svg').first.get_attribute('aria-label').startswith('Management trade-off')
    if key == 'extract':
        assert 'Records → CPUE' in body and 'Annual catch → assessment inputs' in body
        selected = output['output']
        fields = {'set_id', 'source_row', 'year', 'fleet', 'quarter', 'cell', 'stratum', 'hooks', 'catch_n'}
        assert all(set(row) == fields and row['fleet'] == 'FJ'
                   and row['hooks'] > 0 and row['catch_n'] >= 0 for row in selected['sets'])
        assert len({row['stratum'] for row in selected['sets']}) == 6
        assert len(selected['sets']) == 6 * len(selected['catch'])
        assert all(set(row) == {'year', 'catch_t'} for row in selected['catch'])
        assert max(row['year'] for row in selected['sets']) == output['record']['snapshot']
    if key == 'cpue_report':
        assert 'quasipoisson' in body and 'cell–quarter' in body
        assert output['output']['data_kind'] == 'public-wcpfc'
    if key in ('assessment_report', 'mse_report'):
        assert 'not a validated stock-wide abundance index' in body
    if key == 'mse_report':
        assert 'Shared guardrail' in body and 'true starting biomass' in body
    preview = page.context.new_page()
    preview.set_content(output['html'])
    preview.screenshot(path=str(destination / f'{key}.png'), full_page=True)
    preview.close()
    if report:
        assert output['record']['report_rendering']['engine'] == 'Quarto'
        assert output['record']['report_rendering']['quarto_executed'] is True
        page.locator('[data-output="record"]').click()
        assert page.locator('.record-input').count() == 1
        if page.locator('#mode').input_value() == 'cloud':
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
        page.wait_for_function("mode === 'saved'")
        baseline = page.evaluate('records')
    else:
        baseline = run(page)
    for key in JOB_KEYS:
        if not key.endswith('_report'):
            inspect(page, key)
    cpue_before, _ = inspect(page, 'cpue_report', True)
    assessment_before, _ = inspect(page, 'assessment_report', True)
    mse_before, _ = inspect(page, 'mse_report', True)

    growth_records = baseline
    if args.online:
        page.locator('#snapshot').select_option('2022')
        cpue_records = run(page)
        assert all(cpue_records[key]['run_id'] != baseline[key]['run_id'] for key in baseline)
        assert cpue_records['submission']['settings']['last_year'] == 2022
        cpue_after, _ = inspect(page, 'cpue_report', True)
        assert cpue_after != cpue_before

        page.locator('#growth-rate').select_option('0.35')
        growth_records = run(page)
        assert {key for key in growth_records
                if growth_records[key] != cpue_records[key]} == {
                    'assessment_a2', 'assessment_b2', 'assessment_summary', 'assessment_report'} | MSE_JOBS
        assessment_after, output = inspect(page, 'assessment_report', True)
        assert assessment_after != assessment_before and '0.35' in assessment_after
        assert output['record']['inputs']['assessment_summary']['run_id'] == page.evaluate('latestRun')
        mse_after, output = inspect(page, 'mse_report', True)
        assert mse_after != mse_before
        assert output['record']['inputs']['mse_summary']['run_id'] == page.evaluate('latestRun')
        for key in ['assessment_a1', 'assessment_a2', 'assessment_b1', 'assessment_b2']:
            assert growth_records['mse_prepare']['inputs'][key] == {
                'run_id': growth_records[key]['run_id'],
                'checksum': growth_records[key]['outputs']['output.json'],
            }

    page.locator('#mode').select_option('saved')
    for key in ['cpue_report', 'assessment_report', 'mse_report']:
        inspect(page, key, True)
    assert not errors, errors
    result = {'mode': mode, 'distinct_reports': True, 'all_native_views_quarto': True,
              'visible_plot_first_results': True, 'collapsed_controls': False,
              'settings_updates': args.online,
              'retained_inputs': True, 'mse_assessment_inputs': True,
              'saved_reports': True, 'page_errors': errors,
              'execution': growth_records['assessment_report'].get('execution'),
              'source': growth_records['assessment_report'].get('source')}
    (destination / 'checks.json').write_text(json.dumps(result, indent=2) + '\n')
    browser.close()
print('PASS: readable QMD reports, provenance and saved examples.' + (' Hosted revisions and retained inputs also passed.' if args.online else ' No browser calculations.'))
