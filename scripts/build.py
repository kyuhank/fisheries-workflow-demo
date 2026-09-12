"""Build a self-contained browser demo and a readable saved example."""
import asyncio
import base64
import json
from pathlib import Path
import shutil
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from workflow.engine import Workflow
from workflow.spec import SPEC


def base64_file(path):
    return base64.b64encode(path.read_bytes()).decode()


def build():
    with tempfile.TemporaryDirectory() as directory:
        runner = Workflow(directory)
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
    files = [*ROOT.glob('workflow/*.py'), *ROOT.glob('workflow/*.sql'), *ROOT.glob('data/*'),
             *ROOT.glob('tests/*.py'), *ROOT.glob('vendor/analysis/*')]
    files += [ROOT/name for name in ['run.py','verify.py','Makefile','Dockerfile','README.md','LICENSE','THIRD_PARTY.md','build-info.json']]
    runtime_names = ['pyodide.js','pyodide.asm.js','pyodide.asm.wasm','python_stdlib.zip','pyodide-lock.json',
                     'sqlite3-1.0.0-cp312-cp312-pyodide_2024_0_wasm32.whl']
    notices = '\n\n'.join((ROOT/name).read_text() for name in ['THIRD_PARTY.md','LICENSE','vendor/pyodide/LICENSE','vendor/pyodide/PYTHON-LICENSE'])
    payload = {'jobs': list(SPEC.values()), 'saved': saved, 'example': example, 'notices': notices,
               'files': {str(p.relative_to(ROOT)):base64_file(p) for p in files},
               'runtime': {name:base64_file(ROOT/'vendor/pyodide'/name) for name in runtime_names}}
    page = (ROOT/'app/index.html').read_text()
    inserts = {'CSS':(ROOT/'app/style.css').read_text(), 'PAYLOAD':json.dumps(payload, separators=(',', ':')).replace('</', '<\\/'),
               'WORKER':(ROOT/'app/worker.js').read_text(), 'APP':(ROOT/'app/app.js').read_text()}
    for name, content in inserts.items():
        page = page.replace('/*__'+name+'__*/', content)
    (ROOT/'docs/index.html').write_text(page)
    (ROOT/'docs/.nojekyll').touch()
    print(f'Built docs/index.html ({len(page.encode())/1e6:.1f} MB) and {len(SPEC)} saved job reports.')


if __name__ == '__main__':
    build()
