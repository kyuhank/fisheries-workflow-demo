"""Check saved MSE reports, input records and Live rerun scope.

Browser fixtures test navigation and requests. Container checks test simulations,
paired errors and barrier order.
"""
import json
from pathlib import Path
import runpy

from playwright.sync_api import expect, sync_playwright

from pdf_checks import assert_pdf_output, close_pdf_output, expected_record, verified_html

ROOT = Path(__file__).resolve().parents[1]
PEERS = ['mse_constant', 'mse_index', 'mse_buffered']
MSE = ['mse_prepare', *PEERS, 'mse_summary', 'mse_report']
ui = runpy.run_path(str(ROOT / 'scripts/check-browser.py'))

with sync_playwright() as playwright:
    browser = playwright.chromium.launch(headless=True)
    page = browser.new_page(offline=True, viewport={'width': 1440, 'height': 1100})
    errors = []
    page.on('pageerror', lambda error: errors.append(str(error)))
    page.goto((ROOT / 'docs/offline.html').as_uri())
    page.wait_for_function("mode === 'saved'")
    assert page.locator('#task-count').inner_text() == '4'
    assert page.locator('#job-count').inner_text() == '22'
    page.locator('[data-tab="jobs"]').click()
    page.locator('#tasks .mse').click()
    assert page.locator('#job-table-body tr').count() == 6
    page.locator('tr[data-job="mse_prepare"] .open-job-record').click()
    page.locator('#output-record:visible').wait_for()
    assert page.locator('#output-record .record-input').count() == 4
    assert set(page.evaluate('Object.keys(currentOutput.record.inputs)')) == {
        'assessment_a1', 'assessment_a2', 'assessment_b1', 'assessment_b2'}
    page.locator('#output-close').click()
    for key in PEERS:
        expected = expected_record(page, key)
        page.locator(f'tr[data-job="{key}"] .open-output').click()
        body, output = assert_pdf_output(page, key, expected, save=True)
        with verified_html(page, output) as frame:
            expect(frame.locator('svg:visible, img:visible').first).to_be_visible()
            assert frame.locator('details, summary').count() == 0
            expect(frame.locator('table:visible').first).to_be_visible()
        assert 'capped at 40% of starting biomass' in body and 'same saved errors and cases' in body
        assert 'trial fractions are not calibrated management risks' in body
        assert page.evaluate('Object.keys(currentOutput.record.inputs)') == ['mse_prepare']
        close_pdf_output(page)
    reports = {}
    for key in ['mse_summary', 'mse_report']:
        expected = expected_record(page, key)
        page.locator(f'tr[data-job="{key}"] .open-output').click()
        reports[key], _ = assert_pdf_output(page, key, expected, save=True)
        assert reports[key].strip()
        if key == 'mse_summary':
            assert all(phrase in reports[key] for phrase in ('Final B/K', 'Mean catch (t/y)', 'Constant catch', 'Index rule', 'Buffered rule'))
            assert set(page.evaluate('Object.keys(currentOutput.record.inputs)')) == set(PEERS)
        else:
            assert page.evaluate('Object.keys(currentOutput.record.inputs)') == ['mse_summary']
            rendering = page.evaluate('currentOutput.record.report_rendering')
            assert rendering['engine'] == 'Quarto' and rendering['quarto_executed'] is True
            assert 'capped at 40% of starting biomass' in reports[key]
            assert 'trial fractions are not calibrated management risks' in reports[key]
        close_pdf_output(page)
    assert reports['mse_report'] != reports['mse_summary']
    page.close()

    page = browser.new_page(viewport={'width': 1440, 'height': 1100})
    mock = ui['MockCloud']()
    ui['open_live'](page, mock)
    ui['complete'](page, page.evaluate('jobs.map(job => job.key)'))
    page.locator('.workflow-node[data-job="mse_index"]').click()
    before = page.evaluate('records')
    after = ui['complete'](page, ['mse_index', 'mse_summary', 'mse_report'])
    for key in ['mse_constant', 'mse_buffered', 'mse_prepare']:
        assert after[key] == before[key]
    page.locator('#growth-rate').select_option('0.35')
    page.wait_for_function('plan?.changed.includes("assessment_b2")')
    expected = ['assessment_a2', 'assessment_b2', 'assessment_summary', 'assessment_report', *MSE]
    ui['complete'](page, expected)
    highlighted = page.locator('.workflow-node.in-path').evaluate_all('(nodes) => nodes.map(n => n.dataset.job)')
    assert highlighted == expected
    page.locator('.workflow-node[data-job="cpue_summary"]').click()
    before = page.evaluate('records')
    after = ui['complete'](page, ['cpue_summary', 'cpue_report'])
    assert all(after[key] == before[key] for key in MSE)
    assert not errors, errors
    browser.close()
print(json.dumps({'scope': 'Saved reports and mocked UI contracts; no browser model calculations',
                  'mse': 'passed', 'jobs': 22, 'tasks': 4,
                  'checks': ['four recorded assessment inputs', 'three rule inputs',
                             'separate Quarto report', 'strategy-only rerun',
                             'growth-setting propagation', 'independent CPUE reporting']}))
