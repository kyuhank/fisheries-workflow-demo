"""Make local report and source links from the preserved run's own files."""
import hashlib
import html
import json
from urllib.parse import quote

STYLE = '''body{font:16px/1.6 system-ui,sans-serif;color:#233744;max-width:1080px;
margin:40px auto;padding:0 24px}h1{font-size:30px;line-height:1.2}h2{font-size:21px}
a{color:#176c92}nav{display:flex;gap:22px;flex-wrap:wrap;border-bottom:1px solid #cad6dc;
padding-bottom:14px}table{border-collapse:collapse;width:100%;font-size:14px}
th,td{text-align:left;vertical-align:top;padding:12px;border-bottom:1px solid #dce3e7}
th{background:#edf4f7}pre{white-space:pre-wrap;overflow-wrap:anywhere;font:13px/1.55 monospace;
background:#f4f7f9;padding:18px;border-radius:6px}code{font-family:monospace}
.muted{color:#586b77;font-size:13px}.steps{display:grid;grid-template-columns:repeat(auto-fit,
minmax(250px,1fr));gap:18px}.steps section{background:#f1f6f8;padding:8px 18px 18px;
border-radius:8px}details{margin:12px 0;border-bottom:1px solid #dce3e7;padding-bottom:12px}
summary{cursor:pointer;font-weight:600}input{font:inherit;padding:10px;width:min(90%,600px)}
@media(max-width:650px){table{font-size:12px}td,th{padding:8px}.hide-small{display:none}}'''


def page(title, body, script=''):
    return (f'<!doctype html><html lang="en-NZ"><head><meta charset="utf-8">'
            f'<meta name="viewport" content="width=device-width,initial-scale=1">'
            f'<title>{html.escape(title)}</title><style>{STYLE}</style></head><body>'
            '<nav><a href="START-HERE.html">Start here</a><a href="index.html">Interactive example</a>'
            '<a href="code.html">Preserved code</a><a href="OFFLINE.md">Local instructions</a></nav>'
            + body + (f'<script>{script}</script>' if script else '') + '</body></html>').encode()


def source_anchor(name):
    return 'source-' + hashlib.sha256(name.encode()).hexdigest()[:16]


def reader_pages(files, tool_version):
    jobs = json.loads(files['workflow/jobs.json'])['jobs']
    lock = json.loads(files['source-lock.json'])
    state = json.loads(files['reference/state.json'])
    origin = json.loads(files['coordinator-origin.json'])
    rows = []
    for job in jobs:
        key = job['key']
        if key not in state['records']:
            continue
        group = next(g for g, s in lock['repositories'].items() if key in s['jobs'])
        job_name = f'components/{group}/jobs/{key}/run.R'
        guide = f'components/{group}/jobs/{key}/README.md'
        record = state['records'][key]
        assert all(n in files for n in [job_name, guide])
        assert hashlib.sha256(files[job_name]).hexdigest() == record['analysis_source']['sha256']
        linked = [(guide, 'Guide'), (job_name, 'R script')]
        for name, pin in record['code_sources'].items():
            if ((name.startswith(('workflow/r/', 'components/')) and '/R/' in name)
                    or name.startswith('workflow/r/') or name.endswith(('.sql', '.qmd'))):
                assert name in files and hashlib.sha256(files[name]).hexdigest() == pin['sha256']
                linked.append((name, name.rsplit('/', 1)[-1]))
        links = ' · '.join(f'<a href="code.html#{source_anchor(n)}">{html.escape(label)}</a>'
                           for n, label in linked)
        inputs = ', '.join(f'<a href="reference/{quote(p)}/record.json">{html.escape(p)}</a>'
                           for p in job['parents']) or 'Supplied synthetic records'
        rows.append(f'<tr><td><strong>{html.escape(job["title"])}</strong><br>'
                    f'<span class="muted">{html.escape(key)}</span></td><td>{inputs}</td>'
                    f'<td><a href="reference/{key}/report.html">Result</a> · '
                    f'<a href="reference/{key}/record.json">Record</a></td><td>{links}</td></tr>')
    start = '<h1>Fisheries workflow: read, repeat, preserve</h1>'
    start += ('<p>Follow the saved CPUE indices through stock assessment and management trials. '
              'All links below open local files. The synthetic data and simple models illustrate '
              'the workflow; they provide no advice for a real fishery.</p><div class="steps">'
              '<section><h2>1. Read a result</h2><p>Choose a result below, then inspect its record '
              'and the earlier results it used. The guide, R script and library show how it was calculated.</p></section>'
              '<section><h2>2. Repeat the analyses</h2><p>Restore the saved Docker image, then run:</p>'
              '<pre>sh scripts/offline.sh reproduce\nsh scripts/offline.sh compare</pre>'
              '<p>See <a href="OFFLINE.md">local instructions</a>. New reports go into '
              '<code>offline-runs/</code>.</p></section>'
              '<section><h2>3. Keep the evidence</h2><p>Keep this folder and the runtime archive '
              'on independent storage. The source snapshots, settings, records and software '
              'allow repetition without the website or GitHub account.</p></section></div>'
              '<h2>Saved analyses and earlier jobs</h2><p>The earlier jobs must finish before '
              'an analysis can run. Open its Guide to see the files it reads.</p>'
              '<table><thead><tr><th>Analysis</th>'
              '<th>Earlier jobs</th><th>Saved output</th><th>Code used</th></tr></thead><tbody>')
    start += ''.join(rows) + '</tbody></table>'
    start += (f'<p class="muted">Local tools {html.escape(tool_version)}; saved analysis '
              f'{html.escape(json.loads(files["build-info.json"])["version"])}. '
              f'Coordinator revision: {html.escape(origin["commit"])}. '
              'The archive keeps its original analysis sources and adds local reading and execution tools.</p>')
    sections = []
    extensions = {'.R', '.qmd', '.py', '.sql', '.md'}
    for name, data in sorted(files.items()):
        if (name.startswith(('components/', 'workflow/', 'jobs/', 'scripts/'))
                or name in {'run.py', 'verify.py', 'OFFLINE.md', 'README.md', 'ADAPT.md'}):
            if not any(name.endswith(suffix) for suffix in extensions):
                continue
            source = data.decode('utf-8')
            provenance = ''
            if name.startswith('components/'):
                group = name.split('/')[1]
                provenance = 'Recorded component revision: ' + lock['repositories'][group]['commit']
            sections.append(f'<details id="{source_anchor(name)}" data-name="{html.escape(name,quote=True)}">'
                            f'<summary>{html.escape(name)}</summary><p class="muted">'
                            f'{html.escape(provenance)}<br>SHA-256: {hashlib.sha256(data).hexdigest()}</p>'
                            f'<pre>{html.escape(source)}</pre></details>')
    code = ('<h1>Preserved code</h1><p>These are the source bytes packaged with the saved run. '
            'The job links identify the component scripts actually used; coordinator job folders '
            'also retain the earlier monorepo fallback.</p><label for="filter">Find a file</label><br>'
            '<input id="filter" type="search" placeholder="For example: cpue_a or assessment.R">'
            + ''.join(sections))
    script = '''const entries=[...document.querySelectorAll('details')];
document.querySelector('#filter').addEventListener('input',e=>{const q=e.target.value.toLowerCase();
entries.forEach(n=>n.hidden=!n.dataset.name.toLowerCase().includes(q));});
function reveal(){const n=document.getElementById(location.hash.slice(1));if(n){n.hidden=false;
n.open=true;n.scrollIntoView();}}addEventListener('hashchange',reveal);reveal();'''
    return {'START-HERE.html': page('Fisheries workflow — start here', start),
            'code.html': page('Fisheries workflow — preserved code', code, script)}
