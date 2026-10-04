"""Render report jobs from real QMD source inside the same calculation container."""
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
from .r_bridge import RBridge

REPORT_JOBS = {'cpue_report', 'assessment_report', 'mse_report'}


def render_report(root, key, result, record, folder, result_html):
    destination = folder / 'report.html'
    if key not in REPORT_JOBS:
        destination.write_text(result_html)
        return {'engine': 'HTML presentation', 'calculation': 'R',
                'quarto_executed': False,
                'source': 'workflow/reports.py'}
    RBridge.require_container()
    executable = shutil.which('quarto')
    if executable is None:
        raise RuntimeError('Quarto is required for native report jobs.')
    # Native Quarto reads preserved JSON results; it never refits a model.
    source = root / 'jobs' / key / 'report.qmd'
    (folder / 'report.qmd').write_bytes(source.read_bytes())
    (folder / 'report-data.json').write_text(json.dumps({'result': result, 'record': record}, allow_nan=False))
    # Quarto's pinned appdirs implementation writes XDG cache/config/data paths.
    # A non-root Docker UID may not write the image's inherited user directory.
    with tempfile.TemporaryDirectory(prefix='fisheries-quarto-') as temporary:
        environment = dict(os.environ)
        for name, suffix in [('XDG_CACHE_HOME', 'cache'), ('XDG_DATA_HOME', 'data'),
                             ('XDG_CONFIG_HOME', 'config')]:
            environment[name] = str(Path(temporary) / suffix)
        process = subprocess.run([executable, 'render', 'report.qmd', '--to', 'html',
                                  '--output', 'report.html'], cwd=folder, env=environment,
                                 capture_output=True, text=True, timeout=120)
    if process.returncode or not destination.is_file():
        raise RuntimeError('Quarto report failed: ' + (process.stderr or process.stdout).strip()[-2000:])
    version = subprocess.check_output([executable, '--version'], text=True, timeout=10).strip()
    return {'engine': 'Quarto', 'version': version, 'calculation': 'R',
            'quarto_executed': True, 'source': f'jobs/{key}/report.qmd'}
