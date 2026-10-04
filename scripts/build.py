"""Build a self-contained browser demo and a readable saved example."""
import asyncio
import base64
import hashlib
import json
import os
import re
from pathlib import Path
import shutil
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from workflow.engine import Workflow, job_files, calculation_files
from workflow.r_bridge import RBridge
from workflow.spec import SPEC


def base64_file(path):
    return base64.b64encode(path.read_bytes()).decode()


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
        asyncio.run(runner.run())
        saved = runner.state()
        saved['outputs'] = {key: {'html': (runner.directory/key/'report.html').read_text(),
                                 'record': runner.records[key], 'output': runner.output(key)}
                            for key in SPEC}
        saved['bundle'] = base64.b64encode(runner.bundle()).decode()
        example = saved['outputs']['assessment_report']['html']
        example_dir = ROOT / 'docs/example'
        shutil.rmtree(example_dir, ignore_errors=True)
        shutil.copytree(runner.directory, example_dir)
        (example_dir/'index.html').write_text('<!doctype html><html lang="en-NZ"><meta charset="utf-8"><title>Saved workflow example</title><style>body{font:17px/1.6 system-ui;max-width:850px;margin:50px auto;padding:0 24px}a{color:#1779a0}li{margin:12px 0}</style><h1>Saved workflow example</h1><p>These outputs were calculated when this version was built. Open them without running code or connecting to the internet.</p><ol>' + ''.join(f'<li><a href="{key}/report.html">{job["title"]}</a> — {job["description"]}</li>' for key, job in SPEC.items()) + '</ol><p><a href="../index.html">Open the interactive demo</a></p></html>')
    files = [*ROOT.glob('workflow/*.py'), *ROOT.glob('workflow/*.sql'), *calculation_files(), *ROOT.glob('data/*'),
             *ROOT.glob('tests/*.py'), *ROOT.glob('tests/*.R'), *ROOT.glob('cloud/*.py'), *ROOT.glob('vendor/analysis/*')]
    files += [ROOT/name for name in ['run.py','verify.py','Makefile','Dockerfile','README.md','LICENSE','THIRD_PARTY.md','build-info.json']]
    files += [ROOT/'scripts/generate-data.R', ROOT/'scripts/import-r-data.py']
    files += job_files() + [ROOT/'ADAPT.md', ROOT/'cloud/README.md']
    notices = '\n\n'.join((ROOT/name).read_text() for name in ['THIRD_PARTY.md','LICENSE'])
    payload = {'cloud': json.loads((ROOT/'cloud/config.json').read_text()), 'jobs': list(SPEC.values()), 'diagram': diagram, 'saved': saved, 'example': example, 'notices': notices,
               'files': {str(p.relative_to(ROOT)):base64_file(p) for p in files},
               'calculationBackend': 'container', 'offlineMode': 'saved'}
    template = (ROOT/'app/index.html').read_text()
    inserts = {'CSS':(ROOT/'app/style.css').read_text(),
               'WORKER':'', 'APP':'\n'.join((ROOT/'app'/name).read_text() for name in ['cloud.js', 'lineage.js', 'app.js', 'record.js'])}

    def page(data):
        html = template
        for name, content in inserts.items():
            html = html.replace('/*__'+name+'__*/', content)
        return html.replace('/*__PAYLOAD__*/', json.dumps(data, separators=(',', ':')).replace('</', '<\\/'))

    # Both pages view saved results without a browser calculation runtime.
    # New jobs are dispatched to the declared container by the hosted adapter.
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
