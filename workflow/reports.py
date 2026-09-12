"""Readable HTML outputs, with small native SVG plots and recorded inputs."""
import html
import json

STYLE = '''body{font:16px/1.6 system-ui,sans-serif;color:#243649;max-width:920px;margin:36px auto;padding:0 24px}h1{font-size:28px;line-height:1.2}h2{font-size:19px;margin-top:30px}p{max-width:75ch}small,.muted{color:#617181}table{width:100%;border-collapse:collapse;font-size:14px}td,th{text-align:left;padding:9px 12px;border-bottom:1px solid #dde5eb}th{background:#f3f6f8}svg{max-width:100%;height:auto}pre{font-size:12px;white-space:pre-wrap;overflow-wrap:anywhere;background:#f3f6f8;padding:16px;border-radius:8px}.note{border-left:3px solid #7195b2;padding:8px 16px;background:#f3f7fa}footer{margin-top:36px;border-top:1px solid #dde5eb;padding-top:12px;color:#617181;font-size:13px}summary{cursor:pointer;font-weight:600}'''


def esc(value):
    return html.escape(str(value))


def table(rows, columns, limit=None):
    parts = ['<table><thead><tr>' + ''.join('<th>' + esc(title) + '</th>' for _, title in columns) + '</tr></thead><tbody>']
    for row in rows[:limit] if limit else rows:
        parts.append('<tr>' + ''.join('<td>' + esc(f'{row[key]:.4g}' if isinstance(row.get(key), float)
                                                  else row.get(key, '')) + '</td>' for key, _ in columns) + '</tr>')
    return ''.join(parts) + '</tbody></table>'


def plot(series, value, label):
    colours = ['#1378a3', '#b56435', '#7357a8', '#328363']
    all_rows = [r for rows in series.values() for r in rows]
    xs = [r['year'] for r in all_rows]; ys = [r[value] for r in all_rows]
    xmin, xmax = min(xs), max(xs); ymax = max(ys) * 1.1
    x = lambda year: 65 + (year - xmin) / max(1, xmax - xmin) * 660
    y = lambda number: 280 - number / ymax * 225
    out = ['<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 780 340" role="img" aria-label="' + esc(label) + '">']
    for i in range(5):
        v = ymax * i / 4
        out.append(f'<path d="M65 {y(v):.1f}H730" stroke="#e1e8ee"/><text x="54" y="{y(v)+4:.1f}" text-anchor="end" fill="#607080" font-size="12">{v:.2f}</text>')
    for year in [xmin, (xmin+xmax)//2, xmax]:
        out.append(f'<text x="{x(year):.1f}" y="304" text-anchor="middle" fill="#607080" font-size="12">{year}</text>')
    for i, (name, rows) in enumerate(series.items()):
        points = ' '.join(f'{x(r["year"]):.2f},{y(r[value]):.2f}' for r in rows)
        colour = colours[i % len(colours)]
        out.append(f'<polyline points="{points}" fill="none" stroke="{colour}" stroke-width="2.5"/><text x="{65+i*170}" y="25" fill="{colour}" font-size="14">{esc(name)}</text>')
    out.append(f'<text x="65" y="332" fill="#607080" font-size="12">{esc(label)}</text></svg>')
    return ''.join(out)


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
        body += f'<p><strong>{result["rows"]:,}</strong> observations · {result["first_year"]}–{result["last_year"]}</p><p>Tables: <code>sets</code> and <code>removals</code>. This snapshot supplies the SQL extraction.</p>'
    elif key == 'extract':
        body += '<h2>Selected observations</h2>' + table(result['sets'], [('set_id','Record'),('year','Year'),('vessel','Vessel'),('hooks','Hooks'),('catch_n','Catch')], 10)
        body += '<h2>SQL</h2><pre>' + esc(result['sql']) + '</pre><p class="muted">The preview shows the first ten rows. The JSON output contains every selected record.</p>'
    elif key.startswith('prepare_'):
        body += '<p>One annual CPUE index is joined to annual catch by year. No years or values are missing.</p>' + table(result['rows'], [('year','Year'),('index','Relative CPUE'),('catch_t','Catch (t)')])
    elif key in ('cpue_a', 'cpue_b'):
        body += f'<p><strong>{esc(result["method"])}</strong> · {result["sets_used"]:,} observations used · {result["sets_excluded"]:,} excluded.</p>'
        body += plot({job['title']: result['series']}, 'index', 'CPUE relative to the first year')
        body += table(result['series'], [('year','Year'),('index','Relative CPUE')])
    elif key.startswith('assessment_') and key[-2:] in ('a1','a2','b1','b2'):
        body += f'<p>Natural mortality: {result["M"]:.2f} per year. Fixed biology and constant recruitment.</p>'
        if result['boundary_fit']:
            body += '<p class="note">The fit reached a search boundary. This is a diagnostic flag for review.</p>'
        body += plot({job['title']:result['series']}, 'SB_over_SB0', 'Spawning biomass / unfished level')
        body += table(result['series'], [('year','Year'),('SB_over_SB0','SB / SB₀'),('F','Fishing mortality')])
    else:
        cpue = key.startswith('cpue_'); value = 'index' if cpue else 'SB_over_SB0'
        label = 'CPUE relative to the first year' if cpue else 'Spawning biomass / unfished level'
        body += '<h2>Results</h2>' + plot(result['series'], value, label)
        rows = [{'case': name, 'year': values[-1]['year'], 'value': values[-1][value]} for name, values in result['series'].items()]
        body += table(rows, [('case','Analysis'),('year','Final year'),('value','Relative CPUE' if cpue else 'SB / SB₀')])
        body += '<h2>Interpretation</h2><p>' + ('The two analyses use different treatment of vessel effects. Any selected record filter applies to analysis A. This comparison shows how those methods and inputs change the index.' if cpue else 'The four cases combine two CPUE indices with two mortality settings. Their differences illustrate how analytical inputs and assumptions carry through to assessment outputs. These calculations provide no management advice.') + '</p>'
    body += '<h2>Analysis record</h2><p>Produced in <strong>' + esc(record['run_id']) + '</strong>. Each retained input keeps its original run.</p>'
    if lineage:
        body += table(lineage, [('job','Input job'),('run_id','Original run'),('checksum','Output checksum')])
    body += '<details><summary>Data, code, settings and software</summary><pre>' + esc(json.dumps(record, indent=2)) + '</pre></details>'
    return '<!doctype html><html lang="en-NZ"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>' + esc(job['title']) + '</title><style>' + STYLE + '</style><body><p class="muted">Fisheries workflow · illustrative analysis</p><h1>' + esc(job['title']) + '</h1>' + body + '<footer>Synthetic data and simplified models. The downloadable run bundle preserves the inputs, code, settings and results.</footer></body></html>'
