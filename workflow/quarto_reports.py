"""Render saved result views and formal reports with Quarto in the container."""
import json
from pathlib import Path
import re
import shutil
import tempfile
from .r_bridge import RBridge, make_command, process_environment, run_command

REPORT_JOBS = {'cpue_report', 'assessment_report', 'mse_report'}


def result_body(page):
    """Retain the generated view's style/body as a static Quarto HTML include."""
    match = re.search(r'(<style>.*?</style>).*?<body>(.*?)</body>', page, re.S)
    if match is None:
        raise ValueError('A result view must contain its generated style and body.')
    return match[1] + '\n' + match[2] + '\n'


def render_report(root, key, result, record, folder, result_html, source_path=None):
    destination = folder / 'report.html'
    RBridge.require_container()
    executable = shutil.which('quarto')
    if executable is None:
        raise RuntimeError('Quarto is required for native result views and report jobs.')
    # Render recorded results without refitting the models.
    formal = key in REPORT_JOBS
    source = source_path or (root / 'jobs' / key / 'report.qmd' if formal
                             else root / 'workflow/results.qmd')
    artifacts = ['report.html', 'report.qmd', 'report-data.json']
    if not formal:
        (folder / 'report-body.html').write_text(result_body(result_html))
        artifacts.append('report-body.html')
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
            'quarto_executed': True,
            'source': f'jobs/{key}/report.qmd' if formal else 'workflow/results.qmd',
            'presentation_source': f'jobs/{key}/report.qmd' if formal else 'workflow/results.qmd',
            'execution_engine': 'knitr' if formal else 'static',
            'plot_generator': 'R from saved results' if formal else 'Python SVG from saved results',
            'artifacts': artifacts}
