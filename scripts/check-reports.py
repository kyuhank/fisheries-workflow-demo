"""Inspect every saved PDF through the result browser; perform no calculations."""
import json
from pathlib import Path
from playwright.sync_api import sync_playwright
from pdf_checks import assert_pdf_output, close_pdf_output, expected_record, verified_html

ROOT = Path(__file__).resolve().parents[1]
JOBS = json.loads((ROOT / 'workflow/jobs.json').read_text())['jobs']
DEST = ROOT / '.test-output' / 'reports-saved'
DEST.mkdir(parents=True, exist_ok=True)
checks = []
with sync_playwright() as playwright:
    browser = playwright.chromium.launch(headless=True)
    context = browser.new_context(offline=True, viewport={'width': 1440, 'height': 1100})
    page = context.new_page()
    errors = []
    page.on('pageerror', lambda error: errors.append(str(error)))
    page.goto((ROOT / 'docs/offline.html').as_uri())
    page.wait_for_function("mode === 'saved'")
    page.locator('[data-tab="jobs"]').click()
    page.locator('#all-tasks').click()
    for job in JOBS:
        key = job['key']
        expected = expected_record(page, key)
        page.locator(f'tr[data-job="{key}"] .open-output').click()
        text, output = assert_pdf_output(page, key, expected, save=key.endswith('_report'))
        record = output['record']
        rendering = record['report_rendering']
        assert rendering['engine'] == 'Quarto' and rendering['quarto_executed'] is True, key
        assert rendering['execution_engine'] == 'knitr' and rendering['models_refitted'] is False, key
        assert rendering['presentation_source'] == (f'jobs/{key}/report.qmd' if key.endswith('_report') else 'reports/results.qmd'), key
        assert all(name in rendering['artifacts'] for name in ('report.pdf', 'report.qmd', 'report-data.json', 'report.typ', 'report-view.R')), key
        assert len(text.split()) < 650, (key, 'PDF has become too long')
        with verified_html(page, output) as frame:
            assert frame.locator('h1').count() == 1, key
            assert frame.locator('details, summary, pre').count() == 0, key
            if key.startswith(('cpue_', 'assessment_', 'mse_')) and key != 'mse_prepare':
                assert frame.locator('img, svg').count() >= 1, key
            if key in ('cpue_a', 'cpue_b', 'cpue_report'):
                assert 'Standardised' in text and 'Nominal' in text, key
                assert 'Fish per 1,000 hooks' in text, key
            if key == 'extract':
                rows = output['output']['sets']
                assert len({row['stratum'] for row in rows}) == 6
                assert all(row['fleet'] == 'FJ' and row['hooks'] > 0 and row['catch_n'] >= 0 for row in rows)
                assert max(row['year'] for row in rows) == record['snapshot']
            if key.endswith('_report'):
                frame.screenshot(path=str(DEST / f'{key}-html.png'), full_page=True)
        checks.append({'job': key, 'pdf_sha256': record['outputs']['report.pdf'], 'words': len(text.split()), 'quarto': True})
        close_pdf_output(page)
    assert not errors, errors
    browser.close()
(DEST / 'checks.json').write_text(json.dumps({'status': 'passed', 'scope': 'Saved PDF bytes, text, native rendering custody and browser access; no calculations or Live dispatch', 'jobs': checks, 'page_errors': errors}, indent=2) + '\n')
print('PASS: all 22 saved Quarto PDFs, readable outputs and retained rendering sources.')
