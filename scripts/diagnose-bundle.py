"""Inspect genuine preserved synthetic inputs in the declared calculation image."""
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import subprocess
import sys
import tempfile
import zipfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from workflow.r_bridge import RBridge

RBridge.require_container()
bundle = ROOT / 'diagnostics' / 'hosted-update-22.zip'
assert hashlib.sha256(bundle.read_bytes()).hexdigest() == '920d44e1ee551cb6d34912c91cb9505a9898871e59f4200d02c9f48fdb6de902'
report = {'status': 'running', 'bundle_sha256': hashlib.sha256(bundle.read_bytes()).hexdigest(),
          'container': os.environ['PAPER_RUNTIME_IMAGE'], 'steps': []}
destination = ROOT / '.test-output' / 'bundle-diagnostic.json'
destination.parent.mkdir(exist_ok=True)
try:
    with tempfile.TemporaryDirectory(prefix='preserved-hosted-') as directory:
        folder = Path(directory)
        with zipfile.ZipFile(bundle) as archive:
            names = archive.namelist()
            assert len(names) == len(set(names)) == 174
            assert archive.testzip() is None
            assert all(not PurePosixPath(n).is_absolute() and '..' not in PurePosixPath(n).parts for n in names)
            manifest = json.loads(archive.read('SHA256SUMS.json'))
            assert all(hashlib.sha256(archive.read(n)).hexdigest() == h for n, h in manifest.items())
            archive.extractall(folder)
        for stage, argv in [('run', [sys.executable, 'run.py', '--settings', 'settings.json', '--output', 'reproduced']),
                            ('compare', [sys.executable, 'verify.py', 'reference', 'reproduced'])]:
            result = subprocess.run(argv, cwd=folder, capture_output=True, text=True, timeout=360)
            record = {'stage': stage, 'returncode': result.returncode,
                      'stdout': result.stdout[-12000:], 'stderr': result.stderr[-12000:]}
            report['steps'].append(record)
            print(json.dumps(record), flush=True)
            if result.returncode:
                raise RuntimeError(stage + ' failed; original child diagnostics are preserved.')
        report['status'] = 'passed'
finally:
    destination.write_text(json.dumps(report, indent=2) + '\n')
