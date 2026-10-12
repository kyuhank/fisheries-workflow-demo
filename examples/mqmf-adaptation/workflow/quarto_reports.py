"""Render report jobs inside the calculation container."""
import json
from pathlib import Path
import shutil
import tempfile
from .r_bridge import RBridge, make_command, process_environment, run_command

REPORT_JOBS = {'cpue_report', 'assessment_report', 'mse_report'}


def render_report(root, key, result, record, folder, result_html, source_path=None):
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
    # Render recorded results without refitting the models.
    source = source_path or root / 'jobs' / key / 'report.qmd'
    (folder / 'report.qmd').write_bytes(source.read_bytes())
    (folder / 'report-data.json').write_text(json.dumps({'result': result, 'record': record}, allow_nan=False))
    # Give Quarto writable XDG directories when Docker uses a non-root UID.
    with tempfile.TemporaryDirectory(prefix='fisheries-quarto-') as temporary:
        environment = process_environment()
        environment['PAPER_REPORT_DIR'] = str(folder.resolve())
        for name, suffix in [('XDG_CACHE_HOME', 'cache'), ('XDG_DATA_HOME', 'data'),
                             ('XDG_CONFIG_HOME', 'config')]:
            environment[name] = str(Path(temporary) / suffix)
        process = run_command(make_command('report'), timeout=120, environment=environment)
    if process.returncode or not destination.is_file():
        raise RuntimeError('Quarto report failed: ' + (process.stderr or process.stdout).strip()[-2000:])
    version_check = run_command(make_command('quarto-version'), timeout=10)
    if version_check.returncode:
        raise RuntimeError('Quarto version check failed: ' + version_check.stderr.strip()[-2000:])
    version = version_check.stdout.strip()
    return {'engine': 'Quarto', 'version': version, 'calculation': 'R',
            'quarto_executed': True, 'source': f'jobs/{key}/report.qmd'}
