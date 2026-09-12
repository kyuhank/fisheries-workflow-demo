"""Package the built demo, source, runtime and saved outputs for offline use."""
import hashlib
import json
from pathlib import Path
import zipfile

ROOT = Path(__file__).resolve().parents[1]
version = json.loads((ROOT/'build-info.json').read_text())['version']
destination = ROOT/'dist'
destination.mkdir(exist_ok=True)
files = {}
for folder in ['workflow','data','app','scripts','tests','vendor']:
    for path in (ROOT/folder).rglob('*'):
        if path.is_file() and '__pycache__' not in path.parts:
            files[str(path.relative_to(ROOT))] = path.read_bytes()
for name in ['run.py','verify.py','Makefile','Dockerfile','.dockerignore','README.md','ADAPT.md','LICENSE','THIRD_PARTY.md','CITATION.cff','build-info.json']:
    files[name] = (ROOT/name).read_bytes()
files['index.html'] = (ROOT/'docs/index.html').read_bytes()
for path in (ROOT/'docs/example').rglob('*'):
    if path.is_file():
        files['example/'+str(path.relative_to(ROOT/'docs/example'))] = path.read_bytes()
files['SHA256SUMS.json'] = json.dumps({name:hashlib.sha256(data).hexdigest() for name,data in files.items()},indent=2).encode()
archive_path = destination/f'fisheries-workflow-{version}.zip'
with zipfile.ZipFile(archive_path, 'w', zipfile.ZIP_DEFLATED) as archive:
    for name, data in sorted(files.items()):
        archive.writestr(name, data)
(destination/'fisheries-workflow.html').write_bytes(files['index.html'])
(destination/'SHA256SUMS.txt').write_text('\n'.join(hashlib.sha256(path.read_bytes()).hexdigest()+'  '+path.name for path in [archive_path,destination/'fisheries-workflow.html'])+'\n')
print(archive_path)
