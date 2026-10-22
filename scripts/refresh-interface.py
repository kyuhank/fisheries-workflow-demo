"""Refresh interface wording while preserving the saved analysis and its records."""
import hashlib
import json
from pathlib import Path
import re
import subprocess

ROOT = Path(__file__).resolve().parents[1]


def sha(data):
    return hashlib.sha256(data).hexdigest()


def refresh():
    names = ['app/index.html', 'app/style.css'] + [
        'app/' + name for name in ['cloud.js', 'lineage.js', 'app.js', 'record.js']]
    names.append('scripts/refresh-interface.py')
    commit = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT,
                                     text=True).strip()
    sources = {name: (ROOT / name).read_bytes() for name in names}
    for name, data in sources.items():
        recorded = subprocess.check_output(['git', 'show', commit + ':' + name], cwd=ROOT)
        if recorded != data:
            raise ValueError('Commit interface sources before refreshing: ' + name)

    pattern = r'<script id="demo-payload" type="application/json">\s*(.*?)\s*</script>'
    original = [(ROOT / 'docs' / name).read_text() for name in ['index.html', 'offline.html']]
    payloads = [re.search(pattern, page, re.S).group(1) for page in original]
    if payloads[0] != payloads[1]:
        raise ValueError('Online and offline pages must use the same saved analysis')
    raw = payloads[0]
    payload = json.loads(raw)
    page = sources['app/index.html'].decode()
    inserts = {'CSS': sources['app/style.css'].decode(), 'WORKER': '',
               'APP': '\n'.join(sources['app/' + name].decode() for name in
                                ['cloud.js', 'lineage.js', 'app.js', 'record.js']),
               'PAYLOAD': raw}
    for key, value in inserts.items():
        page = page.replace('/*__' + key + '__*/', value)
    if re.search(pattern, page, re.S).group(1) != raw:
        raise ValueError('Saved payload changed during interface generation')

    for name in ['index.html', 'offline.html']:
        (ROOT / 'docs' / name).write_text(page)
    build = ROOT / 'docs/build-record.json'
    saved_build = json.loads(build.read_text())
    if 'execution' in saved_build:
        saved_execution = saved_build['execution']
    elif saved_build.get('schema_version') == 2 and saved_build.get('saved_state_sha256'):
        saved_execution = {key: saved_build[key] for key in
                           ['producing_runs', 'saved_state_sha256', 'jobs']}
    else:
        raise ValueError('The saved build has no execution identity')
    record = {'schema_version': 1, 'operation': 'interface-refresh',
              'interface_source_commit': commit, 'analysis_reexecuted': False,
              'saved_analysis_execution': saved_execution,
              'saved_build_record_sha256': sha(build.read_bytes()),
              'saved_payload_sha256': sha(raw.encode()),
              'interface_input_sha256': {name: sha(data) for name, data in sources.items()},
              'output_sha256': {name: sha((ROOT / name).read_bytes()) for name in
                                ['docs/index.html', 'docs/offline.html']}}
    (ROOT / 'docs/interface-record.json').write_text(json.dumps(record, indent=2) + '\n')
    print('Refreshed interface; saved analyses, PDFs and execution records preserved.')


if __name__ == '__main__':
    refresh()
