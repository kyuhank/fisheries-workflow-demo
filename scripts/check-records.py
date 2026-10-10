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
    assert page.evaluate('Object.keys(currentOutput.record.code).some(name => name.endsWith("jobs/assessment_a2/run.R"))')
    commit = page.evaluate('(currentOutput.record.analysis_source || currentOutput.record.source).commit')
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
    comparison_policy = page.evaluate("""() => {
      let checked = 0;
      const expectPolicy = (value, label) => { if (!value) throw Error(label); checked++; };
      const fit = (gradient = 5.48891009747709e-13, residual = 0.00198045620530427) => ({
        convergence: 0, gradient_check: 'Pass', active_bound: 'none',
        fit_method: 'RTMB::MakeADFun + nlminb', gradient_tolerance: 1e-4,
        objective_gradient_logK: gradient, projected_gradient_logK: gradient,
        K: 1000, objective_value: 0.25,
        series: [{year: 2023, observed_index: 1, fitted_index: Math.exp(-residual),
                  log_residual: residual, B_over_K: 0.6}]
      });
      const left = fit(), right = fit(2.35247591981661e-8, 0.00198045831937885);
      for (const job of comparisonAssessmentJobs) {
        expectPolicy(compareOutput(left, right, job) === null, job + ' observed diagnostics');
      }
      expectPolicy(!!compareOutput(left, right), 'generic outputs retain ordinary tolerance');
      expectPolicy(compareOutput(fit(0), fit(1e-7), 'assessment_b2') === null, 'gradient limit');
      expectPolicy(!!compareOutput(fit(0), fit(1.0001e-7), 'assessment_b2'), 'gradient above limit');
      expectPolicy(!!compareOutput(fit(-1e-7), fit(1e-7), 'assessment_b2'), 'gradient difference limit');
      for (const value of [NaN, Infinity, -Infinity, false, '0']) {
        const bad = structuredClone(right); bad.objective_gradient_logK = value;
        expectPolicy(!!compareOutput(left, bad, 'assessment_b2'), 'nonfinite/malformed gradient');
      }
      const zero = fit(0, JSON.parse('0')), tiny = fit(0, 7e-9);
      expectPolicy(compareOutput(zero, tiny, 'assessment_b2') === null, 'integer zero residual');
      expectPolicy(!!compareOutput(zero, fit(0, 1.01e-8), 'assessment_b2'), 'residual above limit');
      const incoherent = fit(0, 0); incoherent.series[0].log_residual = 2e-12;
      expectPolicy(!!compareOutput(incoherent, structuredClone(incoherent), 'assessment_b2'), 'residual invariant');
      for (const field of ['observed_index', 'fitted_index']) {
        for (const value of [0, -1, Infinity, false]) {
          const bad = fit(0, 0); bad.series[0][field] = value;
          expectPolicy(!!compareOutput(bad, structuredClone(bad), 'assessment_b2'), 'positive finite indices');
        }
      }
      for (const [field, value] of Object.entries({convergence: false, gradient_check: 'Review',
        gradient_tolerance: 1e-3, active_bound: 'unknown', fit_method: 'another optimizer'})) {
        const a = structuredClone(left), b = structuredClone(right); a[field] = b[field] = value;
        expectPolicy(!!compareOutput(a, b, 'assessment_b2'), 'optimizer prerequisite ' + field);
      }
      const bounded = fit(2, 0); bounded.active_bound = 'lower'; bounded.projected_gradient_logK = 0;
      const boundedNext = structuredClone(bounded);
      boundedNext.objective_gradient_logK += 5e-7;
      expectPolicy(compareOutput(bounded, boundedNext, 'assessment_b2') === null, 'ordinary nonzero boundary gradient');
      boundedNext.objective_gradient_logK += 1e-3;
      expectPolicy(!!compareOutput(bounded, boundedNext, 'assessment_b2'), 'nonzero raw gradient stays strict');
      const changedEstimate = structuredClone(right); changedEstimate.K += 0.01;
      expectPolicy(!!compareOutput(left, changedEstimate, 'assessment_b2'), 'ordinary estimate stays strict');
      const sources = {}, summaries = [{diagnostics: [], series: {}}, {diagnostics: [], series: {}}];
      for (const job of comparisonAssessmentJobs) {
        const label = 'Assessment ' + job.split('_')[1].toUpperCase();
        sources[job] = [structuredClone(left), structuredClone(right)];
        for (const side of [0, 1]) {
          const {series, gradient_tolerance, ...diagnostics} = sources[job][side];
          summaries[side].diagnostics.push({case: label, ...structuredClone(diagnostics)});
          summaries[side].series[label] = structuredClone(series);
        }
      }
      for (const job of ['assessment_summary', 'assessment_report']) {
        expectPolicy(compareOutput(...summaries, job, sources) === null, 'verified copies ' + job);
        expectPolicy(!!compareOutput(...summaries, job), 'copies require source context');
      }
      const missing = {...sources}; delete missing.assessment_b2;
      expectPolicy(!!compareOutput(...summaries, 'assessment_summary', missing), 'all four sources required');
      for (const mutation of ['missing case', 'duplicate case', 'diagnostic drift', 'series drift', 'boolean copy']) {
        const copied = structuredClone(summaries[1]);
        if (mutation === 'missing case') copied.diagnostics.pop();
        if (mutation === 'duplicate case') copied.diagnostics[0].case = copied.diagnostics[1].case;
        if (mutation === 'diagnostic drift') copied.diagnostics[0].objective_gradient_logK += 1e-15;
        if (mutation === 'series drift') copied.series['Assessment A1'][0].B_over_K += 1e-12;
        if (mutation === 'boolean copy') copied.diagnostics[0].convergence = false;
        expectPolicy(!!compareOutput(summaries[0], copied, 'assessment_summary', sources), mutation);
      }
      const material = (settings) => ({assessment_b2: {settings, code: {}, data_files: {}, software: {}}});
      expectPolicy(compareMaterials(material(left), material(right)).join() === 'settings', 'materials remain generic');
      return {checks: checked, scope: 'metric-specific comparison fixtures; no scientific calculation'};
    }""")
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
    result['comparison_policy'] = comparison_policy
    (ROOT / f'.test-output/record-{result["mode"]}.json').write_text(json.dumps(result, indent=2) + '\n')
    browser.close()
print('PASS: recorded-input navigation, source/image context, downloaded lineage and stale-input rejection.'
      + (' Real container rerun also passed.' if args.online else ' Saved mode executes nothing.'))
