"""Readable HTML outputs, with small native SVG plots and recorded inputs."""
import html
import json
import math

STYLE = '''body{font:16px/1.6 system-ui,sans-serif;color:#243649;max-width:920px;margin:36px auto;padding:0 24px}h1{font-size:28px;line-height:1.2}h2{font-size:19px;margin-top:30px}p{max-width:75ch}small,.muted{color:#617181}table{width:100%;border-collapse:collapse;font-size:14px}td,th{text-align:left;padding:9px 12px;border-bottom:1px solid #dde5eb}th{background:#f3f6f8}svg{max-width:100%;height:auto}pre{font-size:12px;white-space:pre-wrap;overflow-wrap:anywhere;background:#f3f6f8;padding:16px;border-radius:8px}.note{border-left:3px solid #7195b2;padding:8px 16px;background:#f3f7fa}footer{margin-top:36px;border-top:1px solid #dde5eb;padding-top:12px;color:#617181;font-size:13px}details{margin:18px 0}summary{cursor:pointer;font-weight:600;color:#316985}'''
STYLE += '''.mp-rules{display:grid;grid-template-columns:repeat(3,1fr);gap:12px;margin:16px 0 24px}.mp-rule{border:1px solid #dde5eb;border-top:3px solid #1378a3;border-radius:8px;padding:14px}.mp-rule:nth-child(2){border-top-color:#b56435}.mp-rule:nth-child(3){border-top-color:#7357a8}.mp-rule h3{font-size:16px;margin:0 0 6px}.mp-rule p{font-size:14px;margin:0}.feedback-flow{padding:10px 14px;background:#edf5f8;border-radius:8px;color:#316985;font-weight:600}.table-scroll{overflow-x:auto}.trial-table{min-width:650px}@media(max-width:640px){.mp-rules{grid-template-columns:1fr}body{margin:20px auto;padding:0 16px}}'''


def esc(value):
    return html.escape(str(value))


def table(rows, columns, limit=None):
    parts = ['<table><thead><tr>' + ''.join('<th>' + esc(title) + '</th>' for _, title in columns) + '</tr></thead><tbody>']
    for row in rows[:limit] if limit else rows:
        parts.append('<tr>' + ''.join('<td>' + esc(f'{row[key]:.4g}' if isinstance(row.get(key), float)
                                                  else row.get(key, '')) + '</td>' for key, _ in columns) + '</tr>')
    return ''.join(parts) + '</tbody></table>'


def plot(series, value, label, points=(), colour_by_name=None, upper=None):
    colours = ['#1378a3', '#b56435', '#7357a8', '#328363', '#a7526d', '#93761e', '#277f88', '#66748b']
    all_rows = [r for rows in series.values() for r in rows]
    xs = [r['year'] for r in all_rows]; ys = [r[value] for r in all_rows]
    xmin, xmax = min(xs), max(xs)
    ymin, ymax = min(0, min(ys) * 1.1), max(0, max(ys) * 1.1)
    if upper is not None:
        ymax = max(ymax, upper * 1.1)
    scale = 10 ** math.floor(math.log10(max(ymax - ymin, 1e-12) / 4))
    step = next(size * scale for size in [1, 2, 2.5, 5, 10] if size * scale >= (ymax-ymin) / 4)
    ymin, ymax = math.floor(ymin / step) * step, math.ceil(ymax / step) * step
    span = max(ymax - ymin, step)
    x = lambda year: 65 + (year - xmin) / max(1, xmax - xmin) * 660
    y = lambda number: 280 - (number - ymin) / span * 225
    out = ['<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 780 340" role="img" aria-label="' + esc(label) + '">']
    for i in range(round(span / step) + 1):
        v = ymin + step * i
        if abs(v) < step * 1e-8:
            v = 0.0
        stroke = '#9cafba' if v == 0 and ymin < 0 else '#e1e8ee'
        out.append(f'<path d="M65 {y(v):.1f}H730" stroke="{stroke}"/><text x="54" y="{y(v)+4:.1f}" text-anchor="end" fill="#607080" font-size="12">{v:g}</text>')
    for year in [xmin, (xmin+xmax)//2, xmax]:
        out.append(f'<text x="{x(year):.1f}" y="304" text-anchor="middle" fill="#607080" font-size="12">{year}</text>')
    for i, (name, rows) in enumerate(series.items()):
        coordinates = ' '.join(f'{x(r["year"]):.2f},{y(r[value]):.2f}' for r in rows)
        colour = (colour_by_name or {}).get(name, colours[i % len(colours)])
        if name in points:
            out.extend(f'<circle cx="{x(r["year"]):.2f}" cy="{y(r[value]):.2f}" r="3.5" fill="{colour}"/>' for r in rows)
        else:
            out.append(f'<polyline points="{coordinates}" fill="none" stroke="{colour}" stroke-width="2.5"/>')
        out.append(f'<text x="{65+(i%4)*170}" y="{25+(i//4)*20}" fill="{colour}" font-size="14">{esc(name)}</text>')
    out.append(f'<text x="65" y="332" fill="#607080" font-size="12">{esc(label)}</text></svg>')
    return ''.join(out)


def cpue_report(result):
    """Write an account of the supplied indices without refitting the analyses."""
    series = result['series']
    findings = ' '.join(
        f'The index from {esc(name)} was <strong>{rows[-1]["index"]:.3f}</strong> in '
        f'{esc(rows[-1]["year"])}, relative to 1 in {esc(rows[0]["year"])}.'
        for name, rows in series.items())
    return (
        '<p>This report brings together the CPUE indices prepared for the assessment.</p>'
        '<h2>Methods</h2><p>Analysis A includes year and vessel effects; analysis B '
        'includes year effects only. Both use R Poisson GLMs with a log hooks offset. Each index is '
        'scaled to one in its first year.</p>'
        '<h2>Results</h2><p class="note">' + findings + '</p>'
        + plot(series, 'index', 'CPUE relative to the first year')
        + '<h2>Interpretation</h2><p>Differences between the indices can reflect vessel '
        'adjustment and record selection. Their input records identify the analyses '
        'used in this comparison. These synthetic indices illustrate the workflow '
        'and do not describe a real fishery.</p>')


def assessment_report(result):
    """Describe the supplied assessment cases and their recorded checks."""
    series = result['series']
    diagnostics = result['diagnostics']
    growth_rates = ' and '.join(f'{value:.2f}' for value in
                              sorted({row['r'] for row in diagnostics}))
    final = [(name, rows[-1]) for name, rows in series.items()]
    years = {row['year'] for _, row in final}
    if len(years) == 1:
        values = [row['B_over_K'] for _, row in final]
        findings = (f'In <strong>{esc(next(iter(years)))}</strong>, biomass '
                    f'ranged from <strong>{min(values):.3f} to {max(values):.3f}</strong> '
                    'of each case’s carrying capacity.')
    else:
        findings = ' '.join(
            f'Biomass in {esc(name)} was <strong>{row["B_over_K"]:.3f}</strong> of its '
            f'carrying capacity in {esc(row["year"])}.' for name, row in final)
    boundary = [row['case'] for row in diagnostics if row['boundary_fit']]
    catch_failures = [row['case'] for row in diagnostics if row.get('balance_check', row.get('catch_check')) != 'Pass' or row.get('feasibility_check', 'Pass') != 'Pass']
    checks = ('The biomass recurrence and positive-stock feasibility checks passed.'
              if not catch_failures else
              'Biomass balance or feasibility needs review for ' + ', '.join(map(esc, catch_failures)) + '.')
    checks += (' The biomass search boundary was reached for ' + ', '.join(map(esc, boundary))
               + '; these fits need review.' if boundary else
               ' The fits stayed within the biomass search bounds.')
    return (
        '<p>This report compares the assessment cases using CPUE indices A and B.</p>'
        '<h2>Methods</h2><p>The annual Schaefer surplus-production model uses catch and '
        'a CPUE index. R and RTMB estimate carrying capacity, profile catchability, '
        'and start biomass at carrying capacity. The cases use intrinsic growth '
        'rates of ' + growth_rates + ' per year.</p>'
        '<h2>Results</h2><p class="note">' + findings + '</p>'
        + plot(series, 'B_over_K', 'Biomass / carrying capacity')
        + '<p>' + checks + '</p>'
        '<h2>Interpretation</h2><p>The cases show how CPUE inputs and growth '
        'assumptions carry through to assessment results. Differences between cases '
        'are not an uncertainty interval. These synthetic examples provide no '
        'stock-management advice.</p>')


def mse_metrics(rows):
    return '<div class="table-scroll">' + table(rows, [('name', 'Management rule'), ('mean_catch_t', 'Mean catch (t/year)'),
                        ('final_B_over_K', 'Final B / K'),
                        ('below_threshold_percent', 'Trials below 0.2 (%)'),
                        ('catch_change_percent', 'Catch change (%)')]) + '</div>'


def mse_series(result):
    """Keep rule colours consistent after a result has been saved as sorted JSON."""
    return {row['name']: result['series'][row['name']] for row in result['metrics']}


def mse_rules(result):
    """Show the catch decisions beside their shared comparison conditions."""
    rules = result['rules']
    return ('<h2>Management procedures (MPs)</h2>'
            '<p>Three catch rules face the same stock cases, growth scenarios and observation errors.</p>'
            '<div class="mp-rules">' + ''.join(
                '<section class="mp-rule"><h3>' + esc(rules[key]['name']) + '</h3><p>'
                + esc(rules[key]['description']) + '</p></section>'
                for key in ('constant', 'index', 'buffered')) + '</div>')


def mse_trial(rows):
    """Display recorded annual decisions and stock changes from one trial."""
    display = [{**row, 'stock_change':
                f'{row["start_B_over_K"]:.2f} → {row["B_over_K"]:.2f}'} for row in rows]
    columns = [
        ('year', 'Year'), ('index_ratio', '3-year index / reference'),
    ]
    if rows and 'target_catch_t' in rows[0]:
        columns.append(('target_catch_t', 'Target catch (t)'))
    columns += [
        ('requested_catch_t', 'Catch advice (t)'), ('catch_t', 'Realised catch (t)'),
        ('stock_change', 'Stock before → after (B / K)'),
    ]
    return '<div class="table-scroll"><div class="trial-table">' + table(display, columns) + '</div></div>'


def mse_trial_plots(example):
    rows = example['rows']
    indicators = {
        'Observed index': [{'year': r['year'], 'value': r['index_ratio']} for r in rows],
        'Biomass': [{'year': r['year'], 'value': r['B_over_K']} for r in rows],
    }
    catches = {name: [{'year': r['year'], 'value': r[key]} for r in rows]
               for key, name in [('target_catch_t', 'Target catch'),
                                 ('requested_catch_t', 'Catch advice'), ('catch_t', 'Realised catch')]
               if key in rows[0]}
    return (plot(indicators, 'value', 'Observed index / reference; biomass / carrying capacity')
            + plot(catches, 'value', 'One trial: annual catch (tonnes)'))


def mse_steps(result):
    steps = result['assumptions'].get('buffered_steps')
    if not steps:
        return ''
    lower, upper = steps['thresholds']
    bands = [f'Below {lower:g}', f'{lower:g} to below {upper:g}', f'{upper:g} or above']
    rows = [{'index': band, 'target': f'{100 * fraction:g}% of reference catch'}
            for band, fraction in zip(bands, steps['multipliers'])]
    return table(rows, [('index', 'Observed index / reference'), ('target', 'Target before buffer')])


def mse_scenario_plots(result):
    """Compare scenarios separately, using the same axes and rule colours."""
    scenarios = result.get('scenarios')
    if not scenarios:
        series = mse_series(result) if isinstance(result['series'], dict) else {result['name']: result['series']}
        scenarios = [{'name': 'All trials', 'series': series}]
    else:
        scenarios = [{**s, 'series': {row['name']: s['series'][row['name']] for row in s['metrics']}
                      if isinstance(s['series'], dict)
                      else {result['name']: s['series']}} for s in scenarios]
    colours = {'Constant catch': '#1378a3', 'Index rule': '#b56435', 'Buffered rule': '#7357a8'}
    axes = [('B_over_K', 'Median end-of-year biomass / carrying capacity'),
            ('catch_t', 'Median annual realised catch (tonnes)')]
    ceilings = {key: max(r[key] for s in scenarios for rows in s['series'].values() for r in rows)
                for key, _ in axes}
    panels = []
    for scenario in reversed(scenarios):
        charts = ''.join(plot(scenario['series'], key, label, colour_by_name=colours,
                              upper=ceilings[key]) for key, label in axes)
        if scenario.get('key') == 'baseline' and len(scenarios) > 1:
            panels.append('<details><summary>' + esc(scenario['name']) + '</summary>' + charts + '</details>')
        else:
            panels.append('<h2>' + esc(scenario['name']) + '</h2>' + charts)
    return ''.join(panels)


def mse_metric_note():
    return ('<p class="muted">Final biomass is the median across trials. The threshold column '
            'counts trials that fell below 0.2 of carrying capacity at any time; '
            '0.2 is an illustrative comparison level. Catch change is annual absolute change '
            'relative to mean catch, including the first change from recent catch. Cases and '
            'scenarios have equal weight, not estimated probabilities.</p>')


def mse_methods(result):
    assumptions = result['assumptions']
    scenarios = ('<p>Intrinsic growth stays at its baseline mean, or uses 0.7 of that mean '
                 'for six years before recovering. Year-to-year growth still varies '
                 'in both scenarios.</p>' if any('growth_multipliers' in s
                 for s in assumptions['scenarios']) else '')
    return (f'<p>Four fitted assessment cases supply the simulated stocks. Each rule is tested '
            f'for {assumptions["years"]} years under two growth scenarios, with '
            f'{assumptions["replicates"]} repeated trials per case and scenario. The same '
            'random errors are used when comparing rules.</p>'
            '<p>Each year, an index is observed with error, a catch rule is applied, and the '
            'stock responds to that catch. The next observation comes from the updated stock. '
            'The index-based rules use a three-year mean; they do not see the true stock size.</p>'
            + scenarios)


def mse_limits(result):
    text = '<p>' + ' '.join(esc(item) for item in result['limitations']) + '</p>'
    if result.get('boundary_cases'):
        text += ('<p>The fitted biomass reached its search boundary in '
                 + ', '.join(map(esc, result['boundary_cases']))
                 + '. These operating-model inputs need review.</p>')
    return text


def mse_report(result):
    """Write a short account of the comparison, separate from the summary page."""
    metrics = result['metrics']
    catches = [row['mean_catch_t'] for row in metrics]
    stock = [row['final_B_over_K'] for row in metrics]
    findings = (f'Across the three rules, mean annual catch ranged from '
                f'<strong>{min(catches):,.0f} to {max(catches):,.0f} tonnes</strong>. '
                f'Median final biomass ranged from <strong>{min(stock):.2f} to '
                f'{max(stock):.2f}</strong> of its carrying capacity.')
    changes = ' '.join(f'{esc(row["name"])} had average annual catch changes of '
                       f'{row["catch_change_percent"]:.1f}%.' for row in metrics)
    shortfalls = sum(row['shortfall_trials'] for row in metrics)
    catch_note = (' Some requested catches could not be taken within the simulated harvest '
                  'limit; the comparison uses realised catches.' if shortfalls else '')
    return ('<p>This report compares three simple catch rules under the same simulated '
            'stock conditions and observation errors.</p><h2>Methods</h2>' + mse_methods(result)
            + '<p>' + ' '.join(esc(result['rules'][rule]['name']) + ': '
                               + esc(result['rules'][rule]['description'])
                               for rule in ('constant', 'index', 'buffered'))
            + '</p><h2>Results</h2><p class="note">' + findings + '</p>'
            + mse_scenario_plots(result)
            + '<p>' + changes + catch_note + '</p>'
            '<h2>Interpretation</h2><p>The comparison shows how management decisions feed back '
            'into future stock conditions and catches. Catch, stock condition and stability '
            'must be considered together; this example does not select a preferred rule or '
            'provide advice for a real fishery.</p>'
            '<details><summary>Scope and assumptions</summary>' + mse_limits(result) + '</details>')


def output_page(job, result, record, lineage):
    key = job['key']; body = '<p>' + esc(job['description']) + '</p>'
    if key == 'submission':
        body += '<p>' + str(len(result['sets'])) + ' submitted observations.</p>'
        body += table(result['sets'], [('set_id','Record'),('year','Year'),('vessel','Vessel'),('hooks','Hooks'),('catch_n','Catch')], 10)
    elif key == 'qc':
        body += '<p class="note">' + ('The corrected submission passed all checks.' if result['returned'] else 'All records passed the checks.') + '</p>'
        body += table(result['checks'], [('check','Check'),('result','Result')])
        if result['returned']:
            body += '<h2>Correction record</h2><p>The first submitted record had zero hooks. It was returned to the data provider and resubmitted with its recorded positive effort.</p>'
    elif key == 'database':
        body += f'<p class="note"><strong>{result["rows"]:,}</strong> fishing observations · <strong>{len(result["vessels"])}</strong> vessels · <strong>{result["first_year"]}–{result["last_year"]}</strong></p>'
        body += '<p>The database contains fishing observations (<code>sets</code>) and total annual removals (<code>removals</code>). Catch in numbers in the sampled observations is distinct from total catch in tonnes.</p>'
        body += '<h2>Annual catch</h2>' + plot({'Total removals': result['annual']}, 'catch_t', 'Total annual catch (tonnes)')
        vessel_series = {v: [{'year': r['year'], 'share': 100*r['vessels'][v]/r['observations']} for r in result['annual']] for v in result['vessels']}
        body += '<details><summary>Sampling and vessel composition</summary>' + plot(vessel_series, 'share', 'Share of sampled observations (%)')
        body += '<p>Changes in which vessels are sampled can affect the observed catch rate. CPUE analysis A accounts for vessel effects.</p>'
        body += '<h2>Annual data</h2>' + table(result['annual'], [('year','Year'),('observations','Observations'),('hooks','Hooks'),('catch_t','Total catch (t)'),('zero_catch_percent','Zero catch (%)')]) + '</details>'
        body += '<details><summary>Database fields</summary>' + table(result['fields'], [('name','Field'),('meaning','Meaning'),('type','Type')]) + '</details>'
    elif key == 'extract':
        years = [row['year'] for row in result['sets']]
        coverage = f'{min(years)}–{max(years)}' if years else 'No observation years'
        body += (f'<p class="note"><strong>{len(result["sets"]):,}</strong> observations · '
                 f'<strong>{esc(coverage)}</strong> · <strong>{len(result["catch"])}</strong> '
                 'annual catch records</p>')
        body += ('<p>The saved query selects shared fields from observations with positive effort '
                 'and non-negative catch; any effort filter for analysis A is applied later.</p>')
        body += '<h2>Observations → CPUE</h2>' + table(result['sets'], [('set_id','Record'),('year','Year'),('vessel','Vessel'),('hooks','Hooks'),('catch_n','Catch')], 10)
        body += '<p class="muted">Preview of up to ten observations; the Data tab contains all selected records.</p>'
        body += ('<h2>Annual catch → assessment inputs</h2><p>Annual total catches in tonnes '
                 'are joined to each CPUE index during input preparation.</p>')
        body += '<details><summary>Extraction SQL</summary><pre>' + esc(result['sql']) + '</pre></details>'
    elif key.startswith('prepare_'):
        body += '<p>One annual CPUE index is joined to annual catch by year. No years or values are missing.</p>' + table(result['rows'], [('year','Year'),('index','Relative CPUE'),('catch_t','Catch (t)')], 6)
        body += '<p class="muted">First six years shown; the Data tab contains every model input.</p>'
    elif key in ('cpue_a', 'cpue_b'):
        body += f'<p><strong>{esc(result["method"])}</strong> · {result["sets_used"]:,} observations used · {result["sets_excluded"]:,} excluded.</p>'
        body += plot({job['title']: result['series']}, 'index', 'CPUE relative to the first year')
        body += table([result['series'][0], result['series'][-1]], [('year','Year'),('index','Relative CPUE')])
        body += '<details><summary>All annual values</summary>' + table(result['series'], [('year','Year'),('index','Relative CPUE')]) + '</details>'
    elif key.startswith('assessment_') and key[-2:] in ('a1','a2','b1','b2'):
        body += f'<p>Schaefer surplus-production model · intrinsic growth {result["r"]:.2f} per year · R/RTMB fit. Initial biomass equals carrying capacity.</p>'
        body += '<h2>Biomass trajectory</h2>' + plot({job['title']:result['series']}, 'B_over_K', 'Biomass / carrying capacity')
        body += table([result['series'][0],result['series'][-1]], [('year','Year'),('B_over_K','B / K'),('harvest_rate','Harvest rate')])
        fit_series = {'Observed CPUE':[{'year':r['year'], 'index':r['observed_index']} for r in result['series']],
                      'Fitted CPUE':[{'year':r['year'], 'index':r['fitted_index']} for r in result['series']]}
        if result['boundary_fit']:
            body += '<p class="note">The fit reached a search boundary. Inspect the fit before interpreting it.</p>'
        body += '<details><summary>Fit and diagnostic checks</summary><h2>Fit to the CPUE index</h2>' + plot(fit_series, 'index', 'Relative CPUE', points=('Observed CPUE',))
        body += '<h2>Fit residuals</h2>' + plot({'Log residual': result['series']}, 'log_residual', 'Log(observed / fitted); persistent patterns merit review', points=('Log residual',))
        body += '<h2>Recorded checks</h2>' + table([result], [
            ('feasibility_check', 'Positive biomass'), ('balance_check', 'Biomass recurrence'),
            ('balance_residual_t', 'Balance residual (t)'), ('gradient_check', 'Projected gradient'),
            ('projected_gradient_logK', 'Projected gradient at fit'), ('active_bound', 'Active capacity bound')])
        body += '<p>The checks describe the declared recurrence and optimizer, and do not establish model adequacy.</p>'
        body += '</details><details><summary>All annual estimates</summary>'
        body += table(result['series'], [('year','Year'),('B_over_K','B / K'),('harvest_rate','Harvest rate')]) + '</details>'
    elif key == 'cpue_report':
        body = '<article class="narrative-report" data-report="cpue_report">' + cpue_report(result) + '</article>'
    elif key == 'assessment_report':
        body = '<article class="narrative-report" data-report="assessment_report">' + assessment_report(result) + '</article>'
    elif key == 'mse_prepare':
        body += '<p class="note">Four assessment cases → three catch rules → one comparison.</p>'
        body += ('<h2>From stock assessment to MSE</h2><p>Each fitted assessment supplies a '
                 'starting biomass and its fitted carrying capacity, growth and catchability. '
                 'Simulation begins in the year after the last observed catch. '
                 'The four cases are deliberately included in this example.</p>')
        body += table([
            {'source': 'Fitted model and catch history', 'use': 'Carry forward the fitted final biomass.'},
            {'source': 'Intrinsic growth and carrying capacity', 'use': 'Define annual surplus production.'},
            {'source': 'Catchability and recent CPUE indices', 'use': 'Simulate future indices and define the reference index.'},
            {'source': 'Recent annual catches', 'use': 'Set the reference catch for the management rules.'},
        ], [('source', 'Assessment result used'), ('use', 'Role in MSE')])
        model_rows = [{**model, 'starting_depletion': model['B'] / model['K']}
                      for model in result['operating_models']]
        body += '<h2>Starting stocks</h2>' + table(model_rows, [
            ('name', 'Assessment case'), ('first_year', 'First future year'),
            ('starting_depletion', 'Starting B / K'), ('reference_catch_t', 'Reference catch (t/year)')])
        body += ('<p>Open <strong>Inputs &amp; versions</strong> to follow each case to the exact '
                 'assessment run used. Full starting states and parameters are in the Data tab.</p>')
        body += ('<h2>Added for the future trials</h2><p>The example specifies two growth '
                 'scenarios, observation error and three management rules. These are additional '
                 'assumptions; they are not estimated by the assessments. Every rule faces the '
                 'same scenarios and random trials.</p>')
        body += mse_rules(result)
        body += ('<p>The MSE catch buffer belongs to the Buffered rule job. Changing it reuses '
                 'these prepared stocks and common trial conditions; the MP output and MSE '
                 'comparison record the fraction actually tested.</p>')
        body += ('<h2>What is compared?</h2><p>Catch, biomass and annual catch changes. '
                 'These are illustrative objectives for demonstrating the connected workflow.</p>')
        body += '<details><summary>Simulation assumptions</summary>' + mse_methods(result) + mse_limits(result)
        body += '<pre>' + esc(json.dumps(result['assumptions'], indent=2)) + '</pre></details>'
    elif key in ('mse_constant', 'mse_index', 'mse_buffered'):
        body = '<p class="muted">Management procedure (MP)</p><p class="note">' + esc(result['description']) + '</p>'
        if key == 'mse_buffered':
            body += mse_steps(result)
        body += '<p class="feedback-flow">Observe index → Set catch → Update stock → Repeat</p>'
        example = result['example']
        body += ('<h2>Follow one trial</h2><p>' + esc(example['case']) + ' · '
                 + esc(example['scenario']) + ' · trial ' + str(example['replicate'])
                 + '. The same case and random errors are used for each rule.</p>')
        body += mse_trial_plots(example)
        body += ('<p class="muted">The index-based MPs use the three-year observed index; '
                 'constant catch keeps the reference catch. Stock change includes fishing, '
                 'surplus production and catch removals. B / K is biomass relative '
                 'to its carrying capacity.</p>')
        body += '<details><summary>All years in this trial</summary>' + mse_trial(example['rows']) + '</details>'
        body += '<details><summary>Median results across all trials</summary>' + mse_scenario_plots(result) + '</details>'
        body += '<h2>Across all trials</h2>'
        body += mse_metrics([{'name': result['name'], **result['metrics']}]) + mse_metric_note()
        body += '<details><summary>Results by stock case and scenario</summary>' + table(
            result['cases'], [('case', 'Stock case'), ('scenario', 'Growth'),
                              ('mean_catch_t', 'Mean catch (t/year)'), ('final_B_over_K', 'Final B / K'),
                              ('below_threshold_percent', 'Trials below 0.2 (%)')]) + '</details>'
        body += '<details><summary>Scope and assumptions</summary>' + mse_methods(result) + mse_limits(result) + '</details>'
    elif key == 'mse_summary':
        body = mse_rules(result)
        body += '<h2>Results across all trials</h2>'
        body += mse_metrics(result['metrics']) + mse_metric_note()
        body += mse_scenario_plots(result)
        body += '<details><summary>Results by stock case and scenario</summary>' + table(
            result['cases'], [('rule', 'Rule'), ('case', 'Stock case'), ('scenario', 'Growth'),
                              ('mean_catch_t', 'Mean catch (t/year)'),
                              ('final_B_over_K', 'Final B / K')]) + '</details>'
    elif key == 'mse_report':
        body = '<article class="narrative-report" data-report="mse_report">' + mse_report(result) + '</article>'
    else:
        cpue = key.startswith('cpue_'); value = 'index' if cpue else 'B_over_K'
        label = 'CPUE relative to the first year' if cpue else 'Biomass / carrying capacity'
        body += '<h2>Results</h2>' + plot(result['series'], value, label)
        rows = [{'case': name, 'year': values[-1]['year'], 'value': values[-1][value]} for name, values in result['series'].items()]
        body += table(rows, [('case','Analysis'),('year','Final year'),('value','Relative CPUE' if cpue else 'B / K')])
        if not cpue:
            body += '<details><summary>Harvest rate and case checks</summary><h2>Harvest rate</h2>' + plot(result['series'], 'harvest_rate', 'Catch / starting biomass')
            diagnostics = [{**r, 'boundary': 'Review' if r['boundary_fit'] else 'Within bounds'} for r in result['diagnostics']]
            body += '<h2>Case checks</h2>' + table(diagnostics, [('case','Case'),('r','Intrinsic growth'),('balance_check','Biomass balance'),('feasibility_check','Feasibility'),('gradient_check','Projected gradient'),('boundary','Biomass search')]) + '</details>'
        body += '<h2>Interpretation</h2><p>' + ('The two analyses use different treatment of vessel effects. Any selected record filter applies to analysis A. This comparison shows how those methods and inputs change the index.' if cpue else 'The four cases combine two CPUE indices with two growth settings. Their differences illustrate how analytical inputs and assumptions carry through to assessment outputs. These calculations provide no management advice.') + '</p>'
    body += '<h2>Analysis record</h2><p>Produced in <strong>' + esc(record['run_id']) + '</strong>. Each retained input keeps its original run.</p>'
    if lineage:
        preview = [{**row, 'checksum': row['checksum'][:12]} for row in lineage]
        body += table(preview, [('job','Input job'),('run_id','Original run'),('checksum','Checksum prefix')])
    if record.get('execution'):
        execution = record['execution']
        repo = esc(execution['repository'])
        commit = esc(execution['commit'])
        body += '<p>Executed on GitHub Actions · <a href="https://github.com/' + repo + '/commit/' + commit + '">' + commit[:8] + '</a></p>'
    container = record.get('software', {}).get('container')
    if container:
        body += '<p>Calculation container: <code>' + esc(container) + '</code></p>'
        url = record.get('software', {}).get('container_url')
        if url:
            body += '<p><a href="' + esc(url) + '">Container package</a></p>'
    body += '<details><summary>Data, code, settings and software</summary><pre>' + esc(json.dumps(record, indent=2)) + '</pre></details>'
    return '<!doctype html><html lang="en-NZ"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>' + esc(job['title']) + '</title><style>' + STYLE + '</style><body><p class="muted">Fisheries workflow · illustrative analysis</p><h1>' + esc(job['title']) + '</h1>' + body + '<footer>Synthetic data and simplified models. The downloadable run bundle preserves the inputs, code, settings and results.</footer></body></html>'
