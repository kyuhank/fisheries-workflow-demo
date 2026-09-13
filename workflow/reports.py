"""Readable HTML outputs, with small native SVG plots and recorded inputs."""
import html
import json
import math

STYLE = '''body{font:16px/1.6 system-ui,sans-serif;color:#243649;max-width:920px;margin:36px auto;padding:0 24px}h1{font-size:28px;line-height:1.2}h2{font-size:19px;margin-top:30px}p{max-width:75ch}small,.muted{color:#617181}table{width:100%;border-collapse:collapse;font-size:14px}td,th{text-align:left;padding:9px 12px;border-bottom:1px solid #dde5eb}th{background:#f3f6f8}svg{max-width:100%;height:auto}pre{font-size:12px;white-space:pre-wrap;overflow-wrap:anywhere;background:#f3f6f8;padding:16px;border-radius:8px}.note{border-left:3px solid #7195b2;padding:8px 16px;background:#f3f7fa}footer{margin-top:36px;border-top:1px solid #dde5eb;padding-top:12px;color:#617181;font-size:13px}details{margin:18px 0}summary{cursor:pointer;font-weight:600;color:#316985}'''


def esc(value):
    return html.escape(str(value))


def table(rows, columns, limit=None):
    parts = ['<table><thead><tr>' + ''.join('<th>' + esc(title) + '</th>' for _, title in columns) + '</tr></thead><tbody>']
    for row in rows[:limit] if limit else rows:
        parts.append('<tr>' + ''.join('<td>' + esc(f'{row[key]:.4g}' if isinstance(row.get(key), float)
                                                  else row.get(key, '')) + '</td>' for key, _ in columns) + '</tr>')
    return ''.join(parts) + '</tbody></table>'


def plot(series, value, label, points=()):
    colours = ['#1378a3', '#b56435', '#7357a8', '#328363', '#a7526d', '#93761e', '#277f88', '#66748b']
    all_rows = [r for rows in series.values() for r in rows]
    xs = [r['year'] for r in all_rows]; ys = [r[value] for r in all_rows]
    xmin, xmax = min(xs), max(xs)
    ymin, ymax = min(0, min(ys) * 1.1), max(0, max(ys) * 1.1)
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
        colour = colours[i % len(colours)]
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
        'includes year effects only. Both account for fishing effort. Each index is '
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
    mortalities = ' and '.join(f'{value:.2f}' for value in
                             sorted({row['M'] for row in diagnostics}))
    final = [(name, rows[-1]) for name, rows in series.items()]
    years = {row['year'] for _, row in final}
    if len(years) == 1:
        values = [row['SB_over_SB0'] for _, row in final]
        findings = (f'In <strong>{esc(next(iter(years)))}</strong>, spawning biomass '
                    f'ranged from <strong>{min(values):.3f} to {max(values):.3f}</strong> '
                    'of each case’s unfished level.')
    else:
        findings = ' '.join(
            f'Spawning biomass in {esc(name)} was <strong>{row["SB_over_SB0"]:.3f}</strong> of its '
            f'unfished level in {esc(row["year"])}.' for name, row in final)
    boundary = [row['case'] for row in diagnostics if row['boundary_fit']]
    catch_failures = [row['case'] for row in diagnostics if row['catch_check'] != 'Pass']
    checks = ('Annual catches were reproduced within the numerical tolerance.'
              if not catch_failures else
              'Catch matching needs review for ' + ', '.join(map(esc, catch_failures)) + '.')
    checks += (' The biomass search boundary was reached for ' + ', '.join(map(esc, boundary))
               + '; these fits need review.' if boundary else
               ' The fits stayed within the biomass search bounds.')
    return (
        '<p>This report compares the assessment cases using CPUE indices A and B.</p>'
        '<h2>Methods</h2><p>The simple age-structured model uses annual catch and a CPUE '
        'index, with fixed biology and constant recruitment. The cases use natural '
        'mortality of ' + mortalities + ' per year.</p>'
        '<h2>Results</h2><p class="note">' + findings + '</p>'
        + plot(series, 'SB_over_SB0', 'Spawning biomass / unfished level')
        + '<p>' + checks + '</p>'
        '<h2>Interpretation</h2><p>The cases show how CPUE inputs and mortality '
        'assumptions carry through to assessment results. Differences between cases '
        'are not an uncertainty interval. These synthetic examples provide no '
        'stock-management advice.</p>')


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
        body += f'<p>Annual age-structured model · ages 0–10+ · natural mortality {result["M"]:.2f} per year. Biology is fixed and recruitment is constant.</p>'
        body += '<h2>Biomass trajectory</h2>' + plot({job['title']:result['series']}, 'SB_over_SB0', 'Spawning biomass / unfished level')
        body += table([result['series'][0],result['series'][-1]], [('year','Year'),('SB_over_SB0','SB / SB₀'),('F','Fishing mortality')])
        fit_series = {'Observed CPUE':[{'year':r['year'], 'index':r['observed_index']} for r in result['series']],
                      'Fitted CPUE':[{'year':r['year'], 'index':r['fitted_index']} for r in result['series']]}
        if result['boundary_fit']:
            body += '<p class="note">The fit reached a search boundary. Inspect the fit before interpreting it.</p>'
        body += '<details><summary>Fit and diagnostic checks</summary><h2>Fit to the CPUE index</h2>' + plot(fit_series, 'index', 'Relative CPUE', points=('Observed CPUE',))
        body += '<h2>Fit residuals</h2>' + plot({'Log residual': result['series']}, 'log_residual', 'Log(observed / fitted); persistent patterns merit review', points=('Log residual',))
        body += '<p>Annual catches were reproduced within the numerical tolerance. The fit ' + ('reached' if result['boundary_fit'] else 'stayed within') + ' the biomass search bounds. These checks do not establish model adequacy.</p>'
        body += '</details><details><summary>All annual estimates</summary>'
        body += table(result['series'], [('year','Year'),('SB_over_SB0','SB / SB₀'),('F','Fishing mortality')]) + '</details>'
    elif key == 'cpue_report':
        body = '<article class="narrative-report" data-report="cpue_report">' + cpue_report(result) + '</article>'
    elif key == 'assessment_report':
        body = '<article class="narrative-report" data-report="assessment_report">' + assessment_report(result) + '</article>'
    else:
        cpue = key.startswith('cpue_'); value = 'index' if cpue else 'SB_over_SB0'
        label = 'CPUE relative to the first year' if cpue else 'Spawning biomass / unfished level'
        body += '<h2>Results</h2>' + plot(result['series'], value, label)
        rows = [{'case': name, 'year': values[-1]['year'], 'value': values[-1][value]} for name, values in result['series'].items()]
        body += table(rows, [('case','Analysis'),('year','Final year'),('value','Relative CPUE' if cpue else 'SB / SB₀')])
        if not cpue:
            body += '<details><summary>Fishing mortality and case checks</summary><h2>Fishing mortality</h2>' + plot(result['series'], 'F', 'Annual fishing mortality')
            diagnostics = [{**r, 'boundary': 'Review' if r['boundary_fit'] else 'Within bounds'} for r in result['diagnostics']]
            body += '<h2>Case checks</h2>' + table(diagnostics, [('case','Case'),('M','Natural mortality'),('catch_check','Catch matching'),('boundary','Biomass search')]) + '</details>'
        body += '<h2>Interpretation</h2><p>' + ('The two analyses use different treatment of vessel effects. Any selected record filter applies to analysis A. This comparison shows how those methods and inputs change the index.' if cpue else 'The four cases combine two CPUE indices with two mortality settings. Their differences illustrate how analytical inputs and assumptions carry through to assessment outputs. These calculations provide no management advice.') + '</p>'
    body += '<h2>Analysis record</h2><p>Produced in <strong>' + esc(record['run_id']) + '</strong>. Each retained input keeps its original run.</p>'
    if lineage:
        preview = [{**row, 'checksum': row['checksum'][:12]} for row in lineage]
        body += table(preview, [('job','Input job'),('run_id','Original run'),('checksum','Checksum prefix')])
    if record.get('execution'):
        execution = record['execution']
        repo = esc(execution['repository'])
        commit = esc(execution['commit'])
        body += '<p>Executed on GitHub Actions · <a href="https://github.com/' + repo + '/commit/' + commit + '">' + commit[:8] + '</a></p>'
    body += '<details><summary>Data, code, settings and software</summary><pre>' + esc(json.dumps(record, indent=2)) + '</pre></details>'
    return '<!doctype html><html lang="en-NZ"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>' + esc(job['title']) + '</title><style>' + STYLE + '</style><body><p class="muted">Fisheries workflow · illustrative analysis</p><h1>' + esc(job['title']) + '</h1>' + body + '<footer>Synthetic data and simplified models. The downloadable run bundle preserves the inputs, code, settings and results.</footer></body></html>'
