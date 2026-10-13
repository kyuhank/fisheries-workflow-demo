"""Concise result views and formal accounts, prepared from saved results."""
import html
import json
import math

STYLE = '''body{font:16px/1.6 system-ui,sans-serif;color:#243649;max-width:920px;margin:36px auto;padding:0 24px}h1{font-size:28px;line-height:1.2}h2{font-size:19px;margin-top:30px}p{max-width:75ch}small,.muted{color:#617181}table{width:100%;border-collapse:collapse;font-size:14px}td,th{text-align:left;padding:9px 12px;border-bottom:1px solid #dde5eb}th{background:#f3f6f8}svg{max-width:100%;height:auto}pre{font-size:12px;white-space:pre-wrap;overflow-wrap:anywhere;background:#f3f6f8;padding:16px;border-radius:8px}.note{border-left:3px solid #7195b2;padding:8px 16px;background:#f3f7fa}footer{margin-top:36px;border-top:1px solid #dde5eb;padding-top:12px;color:#617181;font-size:13px}details{margin:18px 0}summary{cursor:pointer;font-weight:600;color:#316985}'''
STYLE += '''.mp-rules{display:grid;grid-template-columns:repeat(3,1fr);gap:12px;margin:16px 0 24px}.mp-rule{border:1px solid #dde5eb;border-top:3px solid #1378a3;border-radius:8px;padding:14px}.mp-rule:nth-child(2){border-top-color:#b56435}.mp-rule:nth-child(3){border-top-color:#7357a8}.mp-rule h3{font-size:16px;margin:0 0 6px}.mp-rule p{font-size:14px;margin:0}.feedback-flow{padding:10px 14px;background:#edf5f8;border-radius:8px;color:#316985;font-weight:600}.table-scroll{overflow-x:auto}.trial-table{min-width:650px}@media(max-width:640px){.mp-rules{grid-template-columns:1fr}body{margin:20px auto;padding:0 16px}}'''
STYLE += '''.plot-pair{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:18px}.plot-pair h2{font-size:17px;margin:12px 0 4px}.plot-pair p{font-size:14px;margin:4px 0 12px}.result-method{font-size:14px;color:#526477}.result-view h2{margin-top:20px}@media(max-width:640px){.plot-pair{grid-template-columns:1fr}}'''
MSE_COLOURS = {'Constant catch': '#1378a3', 'Index rule': '#b56435', 'Buffered rule': '#7357a8'}


def esc(value):
    return html.escape(str(value))


def observation_columns(rows):
    columns = [('set_id', 'Record'), ('year', 'Year')]
    if rows and 'stratum' in rows[0]:
        columns += [('fleet', 'Fleet'), ('cell', 'Cell'), ('quarter', 'Quarter')]
    else:
        columns += [('vessel', 'Vessel')]
    return columns + [('hooks', 'Hooks'), ('catch_n', 'Fish (number)')]


def cpue_methods(result):
    analyses = result.get('analyses', {})
    if not analyses:
        return ('<p>Each supplied index is scaled to one in its first year. '
                'This saved comparison has no model metadata; inspect the '
                'producing jobs and their recorded code for the methods used.</p>')
    return '<p>' + ' '.join(
        esc(name) + ': ' + esc(analysis['method']) + '.'
        for name, analysis in analyses.items()) + (
        ' Both use a log(hooks / 1000) effort offset and scale each index to one '
        'in its first year.</p>')


def cpue_details(result):
    fields = [('formula', 'Formula'), ('standardisation', 'Prediction target'),
              ('effort_unit', 'CPUE unit'), ('sets_used', 'Rows used'),
              ('sets_excluded', 'Rows excluded'), ('converged', 'Converged'),
              ('iterations', 'Iterations'), ('dispersion', 'Pearson dispersion'),
              ('residual_degrees_of_freedom', 'Residual degrees of freedom'),
              ('score_residual', 'Maximum relative score residual')]
    rows = [{'name': title, 'value': result[key]} for key, title in fields if key in result]
    body = table(rows, [('name', 'Item'), ('value', 'Recorded value')])
    if result.get('weights'):
        body += '<h2>Fixed prediction weights</h2>' + table(
            result['weights'], [('stratum', 'Cell–quarter stratum'), ('weight', 'Weight')])
        body += '<p>Predict 1,000 hooks in every supported stratum, then average '
        body += 'the response-scale predictions using these same weights in every year.</p>'
    if result.get('normalisation'):
        normalisation = result['normalisation']
        body += '<p>Reference year: ' + esc(normalisation['reference_year'])
        body += '; divide predicted CPUE by ' + esc(normalisation['divisor']) + '.</p>'
    if result.get('limitations'):
        body += '<p>' + ' '.join(esc(item) for item in result['limitations']) + '</p>'
    return body


def job_trace(key):
    traces = {
        'submission': 'Source records → select final year → submitted rows',
        'qc': 'Submitted rows → check effort, catch and IDs → accepted rows',
        'database': 'Accepted rows → save SQLite snapshot → fixed data inputs',
        'extract': 'SQLite snapshot → recorded SQL → CPUE rows and annual catches',
        'cpue_a': 'Catch and effort rows → adjusted GLM → annual CPUE index A',
        'cpue_b': 'Catch and effort rows → year-only GLM → annual CPUE index B',
        'cpue_summary': 'Indices A and B → align years → index comparison',
        'cpue_report': 'Saved index comparison → describe methods and values → CPUE report',
        'prepare_a': 'Index A and annual catches → join by year → assessment inputs A',
        'prepare_b': 'Index B and annual catches → join by year → assessment inputs B',
        'assessment_summary': 'Four fitted cases → compare trajectories → sensitivity summary',
        'assessment_report': 'Saved assessment comparison → describe cases and checks → assessment report',
        'mse_prepare': 'Four fitted cases → define future trials → shared simulation inputs',
        'mse_constant': 'Shared trials → fixed annual catch → catch and biomass outcomes',
        'mse_index': 'Shared trials → index-based catch → catch and biomass outcomes',
        'mse_buffered': 'Shared trials → buffered catch target → catch and biomass outcomes',
        'mse_summary': 'Three rule outputs → compare trial metrics → management comparison',
        'mse_report': 'Saved management comparison → describe trade-offs and limits → MSE report',
    }
    if key.startswith('assessment_') and key[-2:] in ('a1', 'a2', 'b1', 'b2'):
        return 'Annual index and catches → fixed-growth Schaefer fit → biomass trajectory'
    return traces[key]


def table(rows, columns, limit=None):
    parts = ['<table><thead><tr>' + ''.join('<th>' + esc(title) + '</th>' for _, title in columns) + '</tr></thead><tbody>']
    for row in rows[:limit] if limit else rows:
        parts.append('<tr>' + ''.join('<td>' + esc(f'{row[key]:.4g}' if isinstance(row.get(key), float)
                                                  else row.get(key, '')) + '</td>' for key, _ in columns) + '</tr>')
    return ''.join(parts) + '</tbody></table>'


def plot(series, value, label, points=(), colour_by_name=None, upper=None):
    colours = ['#1378a3', '#b56435', '#7357a8', '#328363', '#a7526d', '#93761e', '#277f88', '#66748b']
    all_rows = [r for rows in series.values() for r in rows]
    if not all_rows:
        return '<p class="muted">No saved values are available for this plot.</p>'
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
    for year in sorted({xmin, (xmin+xmax)//2, xmax}):
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
        '<h2>Methods</h2>' + cpue_methods(result) +
        '<h2>Results</h2><p class="note">' + findings + '</p>'
        + plot(series, 'index', 'CPUE relative to the first year')
        + '<h2>Interpretation</h2><p>Differences between the indices reflect the '
        'adjustment and record selection used by each analysis. These indices cover '
        'the supplied records; they provide no stock-management advice.</p>')


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
        'are not an uncertainty interval. These simplified examples provide no '
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
    colours = MSE_COLOURS
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



def cpue_rates(rows):
    """Use the two rates saved by one producing analysis on its selected rows."""
    if not rows or not all('standardised_cpue' in row and 'nominal_cpue' in row for row in rows):
        return None
    return {label: [{'year': row['year'], 'cpue': row[field]} for row in rows]
            for field, label in [('standardised_cpue', 'Standardised'), ('nominal_cpue', 'Nominal')]}


def cpue_support(analysis):
    parts = ['Both curves use the same selected rows']
    if 'sets_used' in analysis:
        parts.append(f'{analysis["sets_used"]:,} used, {analysis.get("sets_excluded", 0):,} excluded')
    if 'min_hooks' in analysis:
        parts.append(f'effort filter: at least {analysis["min_hooks"]:g} hooks')
    return '<p class="result-method">' + esc('; '.join(parts)) + '.</p>'


def paired_plots(left_title, left, right_title, right):
    return ('<div class="plot-pair"><section><h2>' + esc(left_title) + '</h2>' + left
            + '</section><section><h2>' + esc(right_title) + '</h2>' + right + '</section></div>')


def mse_tradeoff(metrics):
    """Plot the actual saved catch/biomass metrics, with no rule ranking."""
    if not metrics:
        return '<p>No saved management metrics are available.</p>'
    colours = MSE_COLOURS
    xmax = max(1, max(row['mean_catch_t'] for row in metrics) * 1.15)
    ymax = max(1, max(row['final_B_over_K'] for row in metrics) * 1.15)
    x = lambda v: 75 + 610 * v / xmax
    y = lambda v: 275 - 220 * v / ymax
    out = ['<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 780 340" role="img" '
           'aria-label="Management trade-off: mean annual catch (tonnes) and median final biomass / carrying capacity">']
    for i in range(5):
        catch, biomass = xmax * i / 4, ymax * i / 4
        out.append(f'<path d="M75 {y(biomass):.1f}H685" stroke="#e1e8ee"/>'
                   f'<text x="64" y="{y(biomass)+4:.1f}" text-anchor="end" fill="#607080" font-size="12">{biomass:.2g}</text>'
                   f'<text x="{x(catch):.1f}" y="299" text-anchor="middle" fill="#607080" font-size="12">{catch:,.0f}</text>')
    for i, row in enumerate(metrics):
        colour = colours.get(row['name'], '#1378a3')
        out.append(f'<circle cx="{x(row["mean_catch_t"]):.2f}" cy="{y(row["final_B_over_K"]):.2f}" '
                   f'r="6" fill="{colour}"><title>{esc(row["name"])}: {row["mean_catch_t"]:.4g} t/year; '
                   f'final B / K {row["final_B_over_K"]:.4g}</title></circle>'
                   f'<text x="{x(row["mean_catch_t"])+9:.2f}" y="{y(row["final_B_over_K"])-8-i*13:.2f}" '
                   f'fill="{colour}" font-size="13">{i+1}</text>'
                   f'<text x="{75+i*205}" y="25" fill="{colour}" font-size="13">{i+1}. {esc(row["name"])}</text>')
    out.append('<text x="75" y="328" fill="#607080" font-size="12">Mean annual realised catch (tonnes); y: median final B / K</text></svg>')
    return ''.join(out)


def annual_coverage(rows):
    counts = {}
    for row in rows:
        counts[row['year']] = counts.get(row['year'], 0) + 1
    return [{'year': year, 'records': counts[year]} for year in sorted(counts)]


def coverage_text(rows):
    years = [row['year'] for row in rows]
    return f'{min(years)}–{max(years)}' if years else 'No observation years'


def result_view(job, result):
    """Keep all nineteen non-report views visible, brief and based on saved values."""
    key = job['key']
    if key == 'submission':
        rows = result['sets']
        public = bool(rows and 'stratum' in rows[0])
        unit = 'public aggregate records' if public else 'synthetic fishing observations'
        body = (f'<p>{len(rows):,} submitted {unit} · {esc(coverage_text(rows))}.</p>'
                + plot({'Submitted records': annual_coverage(rows)}, 'records', 'Records per year'))
        body += '<h2>Sample of submitted rows</h2>' + table(rows, observation_columns(rows), 6)
        if public:
            body += '<p>Each row combines fleet, five-degree cell, quarter and year; vessel IDs are unavailable.</p>'
        return body + '<p class="muted">First six rows shown. Open Data for all submitted rows.</p>'
    if key == 'qc':
        passed = all(row['result'] == 'Pass' for row in result['checks'])
        message = ('The corrected submission passed all checks.' if result['returned']
                   else 'All records passed the checks.') if passed else 'The quality checks need review.'
        body = '<p class="note">' + message + '</p>' + table(result['checks'], [('check', 'Check'), ('result', 'Result')])
        if result['returned']:
            body += '<p>Invalid rows were returned and replaced from the supplied source. The saved correction record preserves the change.</p>'
        return body
    if key == 'database':
        public = result.get('grouping_field') == 'stratum'
        groups = result.get('groups', result.get('vessels', []))
        group_name = 'cell–quarter strata' if public else 'vessels'
        body = (f'<p>{result["rows"]:,} records · {len(groups)} {group_name} · '
                f'{result["first_year"]}–{result["last_year"]}.</p>'
                + plot({'Total removals': result['annual']}, 'catch_t', 'Total annual catch (tonnes)'))
        body += '<p>Annual removals are saved separately from catch numbers in the CPUE rows.</p>'
        return body + '<h2>Sample of annual coverage</h2>' + table(result['annual'], [
            ('year', 'Year'), ('observations', 'Records'), ('hooks', 'Hooks'),
            ('catch_n', 'Fish (number)'), ('catch_t', 'Total catch (t)')], 6)
    if key == 'extract':
        rows = result['sets']
        body = (f'<p>{len(rows):,} observations · {esc(coverage_text(rows))} · '
                f'{len(result["catch"])} annual catch records.</p>'
                '<p>The query selects positive effort and non-negative catch; any effort filter for analysis A is applied later.</p>')
        body += '<h2>Records → CPUE</h2>' + table(rows, observation_columns(rows), 6)
        body += ('<p>First six rows shown; Data preserves all selected rows and the extraction SQL.</p>'
                 '<h2>Annual catch → assessment inputs</h2><p>Annual total catches in tonnes '
                 'are joined to each index by year; they are not the catch numbers above.</p>')
        return body
    if key.startswith('prepare_'):
        rows = result.get('rows', result.get('series', []))
        return (f'<p>{len(rows)} annual index/catch pairs · {esc(coverage_text(rows))}.</p>'
                '<p>The saved CPUE index and annual removals are joined by year for the stock model.</p>'
                + table(rows, [('year', 'Year'), ('index', 'Relative CPUE'), ('catch_t', 'Catch (t)')], 6)
                + '<p class="muted">First six years shown. Data contains every model input.</p>')
    if key in ('cpue_a', 'cpue_b'):
        rows = result['series']
        rates = cpue_rates(rows)
        body = '<p>Annual CPUE from the selected catch and effort records.</p>'
        if rates:
            body += plot(rates, 'cpue', 'Fish per 1,000 hooks') + cpue_support(result)
            body += '<p>The nominal curve is 1,000 times annual fish numbers divided by annual hooks. The standardised curve uses the saved GLM prediction target.</p>'
        else:
            body += plot({job['title']: rows}, 'index', 'CPUE relative to the first year')
            body += '<p>Only the relative index is available in this saved result; nominal and standardised rates were not recorded.</p>'
        body += '<p class="result-method">' + esc(result.get('method', 'See the saved producing-job methods'))
        if result.get('standardisation'):
            body += ' · ' + esc(result['standardisation'])
        body += '.</p>'
        columns = [('year', 'Year'), ('standardised_cpue', 'Standardised (fish/1,000 hooks)'),
                   ('nominal_cpue', 'Nominal (fish/1,000 hooks)')] if rates else [('year', 'Year'), ('index', 'Relative CPUE')]
        return body + table([rows[0], rows[-1]] if len(rows) > 1 else rows, columns)
    if key == 'cpue_summary':
        series = result['series']
        a_name = 'CPUE analysis A'
        rates = cpue_rates(series.get(a_name, []))
        relative = plot(series, 'index', 'Each index relative to its own first year')
        body = '<p>Compare standardisation on analysis A’s selected rows, then compare the saved A/B indices.</p>'
        if rates:
            body += paired_plots('Standardised and nominal — A rows', plot(rates, 'cpue', 'Fish per 1,000 hooks'),
                                 'Relative indices A and B', relative)
            body += cpue_support(result.get('analyses', {}).get(a_name, {}))
            body += '<p>The main overlay uses analysis A’s nominal rate. An A-only effort filter does not apply to B; B is not substituted for A’s nominal curve.</p>'
            analysis = result.get('analyses', {}).get(a_name, {})
            if analysis.get('standardisation'):
                body += '<p class="result-method">Standardised: ' + esc(analysis['standardisation']) + '. Nominal: 1,000 × annual fish numbers / annual hooks on the A rows.</p>'
        else:
            body += relative + '<p>The saved result has relative indices only; an A-row nominal overlay is unavailable.</p>'
        return body + '<p class="result-method">The A/B comparison includes differences in adjustment and row selection. Each relative index equals one in its own first year.</p>'
    if key.startswith('assessment_') and key[-2:] in ('a1', 'a2', 'b1', 'b2'):
        rows = result['series']
        fit = {'Observed CPUE': [{'year': row['year'], 'index': row['observed_index']} for row in rows],
               'Fitted CPUE': [{'year': row['year'], 'index': row['fitted_index']} for row in rows]}
        body = '<p>Fit the annual CPUE index and carry catch removals through the stock model.</p>'
        body += paired_plots('Observed and fitted CPUE', plot(fit, 'index', 'Relative CPUE', points=('Observed CPUE',)),
                             'Biomass trajectory', plot({'Biomass': rows}, 'B_over_K', 'Biomass / carrying capacity'))
        body += (f'<p class="result-method">Schaefer model · intrinsic growth {result["r"]:.2f} per year · '
                 'R/RTMB fit · initial biomass equals carrying capacity.</p>'
                 '<p>Points are observed indices; the fitted line follows model biomass. Biomass is relative to the fitted capacity.</p>')
        if result['boundary_fit']:
            body += '<p class="note">The fit reached a search boundary and needs review.</p>'
        checks = [{'check': title, 'value': result[field]} for field, title in [
            ('balance_check', 'Biomass recurrence'), ('feasibility_check', 'Positive biomass'),
            ('gradient_check', 'Projected gradient')] if field in result]
        return body + table(checks, [('check', 'Recorded check'), ('value', 'Result')]) + '<p class="muted">These checks do not establish model adequacy. Data preserves estimates, residuals and optimizer diagnostics.</p>'
    if key == 'assessment_summary':
        body = '<p>Compare the four fitted biomass trajectories.</p>'
        body += plot(result['series'], 'B_over_K', 'Biomass / each case’s carrying capacity')
        body += '<p>The cases combine two CPUE indices and two fixed growth settings. Their differences are sensitivities, not an uncertainty interval.</p>'
        rows = [{'case': name, 'year': values[-1]['year'], 'value': values[-1]['B_over_K']}
                for name, values in result['series'].items() if values]
        return body + table(rows, [('case', 'Case'), ('year', 'Final year'), ('value', 'B / K')])
    if key == 'mse_prepare':
        models = result['operating_models']
        assumptions = result['assumptions']
        model_rows = [{**model, 'starting_depletion': model['B'] / model['K']} for model in models]
        body = (f'<p>{len(models)} fitted stock cases · {len(result["rules"])} catch rules · '
                f'{assumptions["years"]} future years · {assumptions["replicates"]} trials per case and scenario.</p>'
                '<h2>Starting stocks</h2>' + table(model_rows, [('name', 'Assessment case'),
                ('first_year', 'First future year'), ('starting_depletion', 'Starting B / K'),
                ('reference_catch_t', 'Reference catch (t/year)')]))
        body += '<p>Trials start after the last observed catch, using the fitted next-year biomass. Future growth and observation errors are declared assumptions.</p>'
        body += '<p>Every rule faces the same recorded scenarios and random errors. The Buffered rule job supplies the catch buffer actually tested.</p>'
        return body + '<p class="muted">Inputs &amp; versions traces each stock to its assessment run. Data preserves parameters, scenarios and paired random streams.</p>'
    if key in ('mse_constant', 'mse_index', 'mse_buffered'):
        series = {result['name']: result['series']}
        body = '<p>' + esc(result['description']) + '</p>'
        body += paired_plots('Biomass across trials', plot(series, 'B_over_K', 'Median end-of-year B / K', colour_by_name=MSE_COLOURS),
                             'Realised catch across trials', plot(series, 'catch_t', 'Median annual catch (tonnes)', colour_by_name=MSE_COLOURS))
        body += '<p>These medians combine the declared stock cases and growth scenarios with equal weight; they are conditional examples.</p>'
        body += mse_metrics([{'name': result['name'], **result['metrics']}])
        return body + mse_metric_note() + '<p class="result-method">Observe the index → set catch → update stock → repeat. Data preserves each annual decision and one complete example trial.</p>'
    if key == 'mse_summary':
        body = '<p>Compare catch, stock condition and catch stability under the same trials.</p>'
        body += paired_plots('Catch and final biomass', mse_tradeoff(result['metrics']),
                             'Biomass through time', plot(mse_series(result), 'B_over_K', 'Median end-of-year B / K', colour_by_name=MSE_COLOURS))
        body += '<p>Each point is one rule’s saved mean catch and median final biomass. The comparison shows trade-offs and does not rank the rules.</p>'
        return body + mse_metrics(result['metrics']) + mse_metric_note()
    raise ValueError('No result view for job: ' + key)


def output_page(job, result, record, lineage):
    key = job['key']
    if key == 'cpue_report':
        body = '<article class="narrative-report" data-report="cpue_report">' + cpue_report(result) + '</article>'
        for name, analysis in result.get('analyses', {}).items():
            body += '<h2>' + esc(name) + ': prediction support and checks</h2>' + cpue_details(analysis)
    elif key == 'assessment_report':
        body = '<article class="narrative-report" data-report="assessment_report">' + assessment_report(result) + '</article>'
    elif key == 'mse_report':
        body = '<article class="narrative-report" data-report="mse_report">' + mse_report(result) + '</article>'
    else:
        body = '<article class="result-view" data-result="' + esc(key) + '">' + result_view(job, result) + '</article>'
    if record.get('data_source') and key.startswith(('assessment_', 'mse_', 'prepare_')):
        body += '<p>The selected Fiji fleet index is not a validated stock-wide abundance index. Using it with stock-wide catches is a teaching assumption.</p>'
    if key.startswith('mse_') and result.get('assumptions'):
        cap = 100 * result['assumptions']['maximum_harvest_rate']
        body += (f'<p class="result-method">The shared guardrail caps realised catch at {cap:g}% of true starting biomass. '
                 'Biomass and low-biomass statistics are conditional on that safeguard.</p>')
    warnings = []
    for check in ('balance_check', 'feasibility_check', 'gradient_check'):
        if check in result and result[check] != 'Pass':
            warnings.append(check.replace('_', ' ') + ': ' + str(result[check]))
    for row in result.get('diagnostics', []):
        if row.get('boundary_fit') or any(row.get(check, 'Pass') != 'Pass'
                                         for check in ('balance_check', 'feasibility_check', 'gradient_check')):
            warnings.append('Review the fit and checks for ' + row['case'] + '.')
    if result.get('converged') is False:
        warnings.append('The CPUE model did not converge.')
    for name, analysis in result.get('analyses', {}).items():
        if analysis.get('converged') is False:
            warnings.append(name + ' did not converge.')
    if result.get('boundary_cases'):
        warnings.append('Assessment search boundary reached: ' + ', '.join(result['boundary_cases']) + '.')
    metrics = result.get('metrics', [])
    metrics = [metrics] if isinstance(metrics, dict) else metrics
    if any(row.get('shortfall_trials', 0) for row in metrics):
        warnings.append('Some requested catches exceeded the simulated harvest limit; metrics use realised catch.')
    if warnings:
        body += '<p class="note">' + ' '.join(esc(warning) for warning in warnings) + '</p>'
    body = body.replace('</p>', '</p><p class="feedback-flow">' + esc(job_trace(key)) + '</p>', 1)
    body += '<p class="muted">Produced in <strong>' + esc(record['run_id']) + '</strong>. Retained inputs keep their original runs.</p>'
    if key.endswith('_report') and lineage:
        preview = [{**row, 'checksum': row['checksum'][:12]} for row in lineage]
        body += '<h2>Retained inputs</h2>' + table(preview, [('job', 'Input job'), ('run_id', 'Original run'), ('checksum', 'Checksum prefix')])
    body += '<p class="muted">Open Data for complete values and Inputs &amp; versions for exact source, settings and execution records. The run bundle preserves these files.</p>'
    return ('<!doctype html><html lang="en-NZ"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>'
            + esc(job['title']) + '</title><style>' + STYLE + '</style><body><h1>' + esc(job['title']) + '</h1>'
            + body + '<footer>Teaching workflow with simplified assessment and management models. The run bundle preserves inputs, code, settings and results.</footer></body></html>')
