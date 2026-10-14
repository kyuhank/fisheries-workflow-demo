"""Build the browser demo and its saved example."""
import asyncio
import base64
import csv
import hashlib
import html
import json
import os
import re
from pathlib import Path
import shutil
import sys
import tempfile
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from workflow.engine import Workflow, source_payload
from workflow.r_bridge import RBridge
from workflow.spec import SPEC


def base64_file(path):
    return base64.b64encode(path.read_bytes()).decode()


def data_page(source):
    """Expose the same input projection and query used by the saved example."""
    folder = ROOT / 'docs/data'
    folder.mkdir(parents=True, exist_ok=True)
    for name, rows in [('fiji-source.csv', source['sets']), ('annual-catch.csv', source['catch'])]:
        with (folder / name).open('w', newline='') as stream:
            writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
            writer.writeheader()
            writer.writerows(rows)
    query = (ROOT / 'workflow/extract-public.sql').read_text()
    (folder / 'extract.sql').write_text(query)
    sources = ''.join('<li><a href="' + html.escape(item['url'], quote=True) + '">' +
                      html.escape(item['file'].rsplit('/', 1)[-1]) + '</a> · SHA-256 <code>' +
                      item['sha256'] + '</code></li>' for item in source['metadata']['sources'])
    page = ('<!doctype html><html lang="en-NZ"><meta charset="utf-8">'
            '<meta name="viewport" content="width=device-width,initial-scale=1">'
            '<title>Public albacore data</title><style>body{font:17px/1.6 system-ui;color:#233744;'
            'max-width:880px;margin:40px auto;padding:0 24px}a{color:#176c92}pre{white-space:pre-wrap;'
            'padding:18px;background:#f3f6f8}code{overflow-wrap:anywhere;font-size:13px}</style>'
            '<a href="index.html">← Workflow</a><h1>Public albacore data</h1>'
            '<p>The Fiji records come from the WCPFC/SPC longline release. Each row is a '
            'fleet, quarter and 5° cell aggregate. It is not an individual fishing set or vessel.</p>'
            '<p><a href="https://www.wcpfc.int/index.php/sustainability/scientific-data/'
            'wcpfc-public-domain-aggregated-catcheffort-data-download-page">Official download page</a> · '
            '<a href="https://github.com/kyuhank/fisheries-workflow-demo/tree/main/data/public">'
            'Preserved originals and field definitions</a></p><ol>' + sources + '</ol>'
            '<h2>1. Extract a small, consistent sample</h2><p>The source projection contains 662 '
            'released Fiji records from 2000–2022. The query selects six cell–quarter strata '
            'observed in every year: 132 records through 2021, or 138 through 2022.</p>'
            '<p><a href="data/fiji-source.csv" download>Source projection (CSV)</a> · '
            '<a href="data/extract.sql" download>Selection query (SQL)</a></p>'
            '<h3>Selection query</h3><pre>' + html.escape(query) + '</pre>'
            '<h2>2. Standardise catch per effort</h2><p>CPUE A uses year and cell–quarter stratum '
            'with a log effort offset. CPUE B uses year and quarter. Both quasi-Poisson models predict '
            'fish per 1,000 hooks and average the same six strata equally in each year; '
            'the relative index starts at one in 2000.</p>'
            '<h2>3. Keep annual stock catch separate</h2><p>The yearbook series sums South Pacific '
            'albacore across all gears and fleets, in metric tonnes. It is not the catch in the '
            'six CPUE strata. <a href="data/annual-catch.csv" download>Annual catch (CSV)</a>.</p>'
            '<p>HHOOKS is hundreds of hooks; the adapter multiplies it by 100. ALB_N counts fish. '
            'Confidential cells have masked catch and effort, and are excluded before selection. '
            'Their zeros are not observed zero catches. The small fleet index is not validated '
            'as stock-wide abundance; assessment and management trials use teaching assumptions.</p>'
            '<p>Source notices and attribution remain with WCPFC/SPC. The code licence does '
            'not relicense the data.</p></html>')
    (ROOT / 'docs/data.html').write_text(page)


def build():
    RBridge.require_container()
    diagram = json.loads((ROOT/'app/diagram.json').read_text())
    if {node['key'] for node in diagram['nodes']} != set(SPEC):
        raise ValueError('Diagram must include every job')
    if {(edge['from'], edge['to']) for edge in diagram['edges']} != {
        (parent, key) for key, job in SPEC.items() for parent in job['parents']
    }:
        raise ValueError('Diagram connections must match the calculation dependencies')
    with tempfile.TemporaryDirectory() as directory:
        runner = Workflow(directory)
        if not runner.sources.multi_repository:
            raise ValueError('The saved site requires pinned components; use make run for the monorepo fallback.')
        provenance = {name: os.environ.get(name) for name in
                      ('GITHUB_SHA', 'GITHUB_REPOSITORY', 'GITHUB_RUN_ID')}
        if any(provenance.values()):
            commit, repository, run_id = (provenance[name] for name in
                                         ('GITHUB_SHA', 'GITHUB_REPOSITORY', 'GITHUB_RUN_ID'))
            if (not commit or not re.fullmatch(r'[0-9a-f]{40}', commit) or
                    not repository or not re.fullmatch(r'[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+', repository) or
                    not run_id or not run_id.isdigit()):
                raise ValueError('Saved-example build requires complete actual GitHub execution identity.')
            runner.execution = {'provider': 'GitHub Actions', 'purpose': 'saved-example-build',
                                'repository': repository, 'commit': commit, 'github_run': run_id,
                                'container': RBridge.require_container()}
            if os.environ.get('PAPER_RUNTIME_IMAGE_URL'):
                runner.execution['container_url'] = os.environ['PAPER_RUNTIME_IMAGE_URL']
        else:
            origin = runner.sources.coordinator_identity()
            if not origin.get('commit'):
                raise ValueError('Saved-example build requires a verified committed coordinator source.')
            runner.execution = {'provider': 'Local Docker', 'purpose': 'saved-example-build',
                                'repository': 'kyuhank/fisheries-workflow-demo',
                                'commit': origin['commit'], 'container': RBridge.require_container()}
            for variable, field in [('PAPER_EXECUTION_HOST', 'execution_host'),
                                    ('PAPER_COMPUTE_SELECTION_RECEIPT', 'compute_selection_receipt')]:
                if os.environ.get(variable):
                    runner.execution[field] = os.environ[variable]
        started = time.perf_counter()
        asyncio.run(runner.run())
        elapsed = time.perf_counter() - started
        build_record = {
            'schema_version': 1, 'type': 'saved-example-build',
            'execution': runner.execution, 'settings': runner.settings,
            'jobs_executed': runner.last_plan['run'],
            'analysis_and_reports_seconds': elapsed,
            'timing_scope': 'Fresh workflow including R analyses, checks and all report rendering; '
                            'excludes source retrieval, container image download and runner queue.',
            'source_lock_sha256': hashlib.sha256(runner.sources.lock_path.read_bytes()).hexdigest(),
            'builder_sha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
            'extracted_records': len(runner.output('extract')['sets']),
            'annual_catches': len(runner.output('extract')['catch']),
            'report_jobs': [key for key in runner.records if key.endswith('_report')],
            'quarto_result_views': [key for key, record in runner.records.items()
                                    if record['report_rendering']['quarto_executed']]}
        (ROOT / 'docs/build-record.json').write_text(json.dumps(build_record, indent=2) + '\n')
        saved = runner.state()
        saved['outputs'] = {key: {'html': (runner.directory/key/'report.html').read_text(),
                                 'pdf_base64': base64_file(runner.directory/key/'report.pdf'),
                                 'record': runner.records[key], 'output': runner.output(key)}
                            for key in SPEC}
        saved['bundle'] = base64.b64encode(runner.bundle()).decode()
        example = saved['outputs']['assessment_report']['html']
        example_dir = ROOT / 'docs/example'
        shutil.rmtree(example_dir, ignore_errors=True)
        shutil.copytree(runner.directory, example_dir)
        (example_dir/'index.html').write_text('<!doctype html><html lang="en-NZ"><meta charset="utf-8"><title>Saved workflow example</title><style>body{font:17px/1.6 system-ui;max-width:850px;margin:50px auto;padding:0 24px}a{color:#1779a0}li{margin:12px 0}</style><h1>Saved workflow example</h1><p>These outputs were calculated when this version was built. Open their compiled Quarto PDFs without running code or connecting to the internet.</p><ol>' + ''.join(f'<li><a href="{key}/report.pdf">{job["title"]}</a> — {job["description"]}</li>' for key, job in SPEC.items()) + '</ol><p><a href="../index.html">Open the interactive demo</a></p></html>')
    notices = '\n\n'.join((ROOT/name).read_text() for name in ['THIRD_PARTY.md','LICENSE'])
    payload = {'cloud': json.loads((ROOT/'cloud/config.json').read_text()), 'jobs': list(SPEC.values()), 'diagram': diagram, 'saved': saved, 'example': example, 'example_pdf_base64': saved['outputs']['assessment_report'].get('pdf_base64'), 'example_pdf_sha256': saved['records']['assessment_report']['outputs']['report.pdf'], 'notices': notices,
               'calculationBackend': 'container', 'offlineMode': 'saved'}
    if runner.source_context().get('data_kind') == 'public-wcpfc-albacore':
        data_page(runner.source_context())
    template = (ROOT/'app/index.html').read_text()
    inserts = {'CSS':(ROOT/'app/style.css').read_text(),
               'WORKER':'', 'APP':'\n'.join((ROOT/'app'/name).read_text() for name in ['cloud.js', 'lineage.js', 'app.js', 'record.js'])}

    def page(data):
        html = template
        for name, content in inserts.items():
            html = html.replace('/*__'+name+'__*/', content)
        return html.replace('/*__PAYLOAD__*/', json.dumps(data, separators=(',', ':')).replace('</', '<\\/'))

    # Both pages browse saved results; Live submits new jobs to the container.
    offline_page = page(payload)
    (ROOT/'docs/offline.html').write_text(offline_page)
    for previous in (ROOT/'docs').glob('runtime-*.json'):
        previous.unlink()
    live_page = page(payload)
    (ROOT/'docs/index.html').write_text(live_page)
    (ROOT/'docs/.nojekyll').touch()
    print(f'Built container-run page ({len(live_page.encode())/1e6:.1f} MB), saved offline page ({len(offline_page.encode())/1e6:.1f} MB) and {len(SPEC)} saved job reports.')


if __name__ == '__main__':
    build()
