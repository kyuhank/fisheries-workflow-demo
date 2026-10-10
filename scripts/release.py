"""Package the built demo, source, runtime and saved outputs for offline use."""
import hashlib
import json
from pathlib import Path
import zipfile
import sys
import base64
import io
import re

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from workflow.engine import source_payload
from importlib.util import module_from_spec, spec_from_file_location
reader_spec = spec_from_file_location('offline_reader', ROOT/'scripts/offline-reader.py')
reader = module_from_spec(reader_spec)
reader_spec.loader.exec_module(reader)
version = json.loads((ROOT/'build-info.json').read_text())['version']
destination = ROOT/'dist'
destination.mkdir(exist_ok=True)
if "--offline-only" not in sys.argv:
    files = {}
    for folder in ['jobs','workflow','data','diagnostics','app','scripts','tests','vendor/analysis','cloud','supabase/functions','.github/workflows']:
        for path in (ROOT/folder).rglob('*'):
            if path.is_file() and '__pycache__' not in path.parts:
                files[str(path.relative_to(ROOT))] = path.read_bytes()
    for name in ['run.py','verify.py','Makefile','Dockerfile','.dockerignore','README.md','ADAPT.md','OFFLINE.md','runtime-preservation.json','LICENSE','THIRD_PARTY.md','CITATION.cff','build-info.json','examples/analyst-repositories.yaml']:
        files[name] = (ROOT/name).read_bytes()
    files.update(source_payload())
    files['index.html'] = (ROOT/'docs/offline.html').read_bytes()
    for path in (ROOT/'docs/example').rglob('*'):
        if path.is_file():
            files['example/'+str(path.relative_to(ROOT/'docs/example'))] = path.read_bytes()
    files['SHA256SUMS.json'] = json.dumps({name:hashlib.sha256(data).hexdigest() for name,data in files.items()},indent=2).encode()
    archive_path = destination/f'fisheries-workflow-{version}.zip'
    with zipfile.ZipFile(archive_path, 'w', zipfile.ZIP_DEFLATED) as archive:
        for name, data in sorted(files.items()):
            archive.writestr(name, data)
    (destination/'fisheries-workflow.html').write_bytes(files['index.html'])
# Preserve the source used by the saved run, rather than replacing it with
# whichever coordinator revision packages this release.
payload_match = re.search(r'<script id="demo-payload" type="application/json">\s*(.*?)\s*</script>',
                          (ROOT/'docs/offline.html').read_text(), re.S)
payload = json.loads(payload_match.group(1))
with zipfile.ZipFile(io.BytesIO(base64.b64decode(payload['saved']['bundle']))) as saved:
    assert saved.testzip() is None
    preserved = {name: saved.read(name) for name in saved.namelist()}
old_manifest = json.loads(preserved['SHA256SUMS.json'])
assert all(hashlib.sha256(preserved[n]).hexdigest() == h for n,h in old_manifest.items())
support = ['OFFLINE.md', 'runtime-preservation.json', 'scripts/offline.sh',
           'scripts/offline-runtime.py', 'scripts/preserve-runtime.sh', 'workflow/offline.py']
for name in support:
    if name in preserved and preserved[name] != (ROOT/name).read_bytes():
        raise ValueError('Support tools must not replace recorded source: ' + name)
    preserved[name] = (ROOT/name).read_bytes()
preserved['index.html'] = (ROOT/'docs/offline.html').read_bytes()
preserved.update(reader.reader_pages(preserved, version))
# The public guide points to the same saved reports already served by Pages.
guide_directory = ROOT/'docs/offline-guide'
guide_directory.mkdir(exist_ok=True)
for name in ['START-HERE.html', 'code.html', 'OFFLINE.md']:
    data = preserved[name]
    if name.endswith('.html'):
        data = data.replace(b'href="reference/', b'href="../example/')
        data = data.replace(b'href="index.html"', b'href="../offline.html"')
    (guide_directory/name).write_bytes(data)
preserved['PRESERVATION.json'] = (json.dumps({
    'schema_version': 1, 'tool_version': version,
    'saved_analysis_version': json.loads(preserved['build-info.json'])['version'],
    'original_manifest': old_manifest,
    'support_files': support,
    'note': 'Original run sources and records are unchanged; local tools are added separately.'
}, indent=2) + '\n').encode()
preserved['REPRODUCE.txt'] = ('Open START-HERE.html and follow OFFLINE.md.\n'
    'Repeat: sh scripts/offline.sh reproduce\nCompare: sh scripts/offline.sh compare\n'
    'Docker and a POSIX shell are required. Restore the recorded image from the separate\n'
    'runtime archive if necessary. These commands never retrieve software or source.\n'
    'Original analysis sources are preserved; local support tools are separately recorded\n'
    'in PRESERVATION.json. Results remain synthetic demonstration results.\n').encode()
preserved['SHA256SUMS.json'] = (json.dumps({n:hashlib.sha256(v).hexdigest()
    for n,v in sorted(preserved.items()) if n != 'SHA256SUMS.json'},indent=2)+'\n').encode()
offline_archive = destination/f'fisheries-workflow-offline-{version}.zip'
with zipfile.ZipFile(offline_archive, 'w', zipfile.ZIP_DEFLATED) as archive:
    for name,data in sorted(preserved.items()):
        archive.writestr(name,data)
assets = [offline_archive]
if "--offline-only" not in sys.argv:
    assets += [archive_path, destination/'fisheries-workflow.html']
(destination/'SHA256SUMS.txt').write_text('\n'.join(hashlib.sha256(path.read_bytes()).hexdigest()+'  '+path.name for path in assets)+'\n')
for asset in assets:
    print(asset)
