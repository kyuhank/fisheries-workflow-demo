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


def pdf_body(body, folder):
    """Export the existing vector plots before Pandoc converts the saved HTML."""
    body = re.sub(r'<style>.*?</style>', '', body, flags=re.S)
    # Legends are embedded in each exported SVG; the HTML view has its own legend.
    body = re.sub(r'<div class="plot-legend">.*?</div>', '', body, flags=re.S)
    plots = []

    def export(match):
        svg = match[0]
        name = f'report-plot-{len(plots) + 1:02d}.svg'
        (folder / name).write_text(svg)
        plots.append(name)
        label = re.search(r'aria-label="([^"]*)"', svg)
        alt = label[1] if label else 'Saved analysis plot'
        return f'<p><img src="{name}" alt="{alt}"></p>'

    return re.sub(r'<svg\b.*?</svg>', export, body, flags=re.S), plots


def render_report(root, key, result, record, folder, result_html, source_path=None):
    destination = folder / 'report.html'
    pdf = folder / 'report.pdf'
    RBridge.require_container()
    executable = shutil.which('quarto')
    if executable is None:
        raise RuntimeError('Quarto is required for native result views and report jobs.')
    # Render recorded results without refitting the models.
    formal = key in REPORT_JOBS
    source = source_path or (root / 'jobs' / key / 'report.qmd' if formal
                             else root / 'workflow/results.qmd')
    artifacts = ['report.html', 'report.pdf', 'report.qmd', 'report-data.json', 'report.typ']
    if not formal:
        body = result_body(result_html)
        (folder / 'report-body.html').write_text(body)
        converted, plots = pdf_body(body, folder)
        (folder / 'report-pdf-body.html').write_text(converted)
        artifacts.extend(['report-body.html', 'report-pdf-body.html', 'report-body.md', *plots])
    (folder / 'report.qmd').write_bytes(source.read_bytes())
    (folder / 'report-data.json').write_text(json.dumps({'result': result, 'record': record}, allow_nan=False))
    # Give Quarto writable XDG directories when Docker uses a non-root UID.
    with tempfile.TemporaryDirectory(prefix='fisheries-quarto-') as temporary:
        environment = process_environment()
        environment['PAPER_REPORT_DIR'] = str(folder.resolve())
        for name, suffix in [('XDG_CACHE_HOME', 'cache'), ('XDG_DATA_HOME', 'data'),
                             ('XDG_CONFIG_HOME', 'config')]:
            environment[name] = str(Path(temporary) / suffix)
        if not formal:
            conversion = run_command(make_command('report-markdown'), timeout=30, environment=environment)
            if conversion.returncode or not (folder / 'report-body.md').is_file():
                raise RuntimeError('Quarto Markdown conversion failed: ' +
                                   (conversion.stderr or conversion.stdout).strip()[-2000:])
            markdown = folder / 'report-body.md'
            # The units already follow each plot; retain alt text without duplicate captions.
            text = re.sub(r'!\[([^\]]*)\]\((report-plot-\d+\.svg)\)',
                          lambda match: '![](' + match[2] + '){fig-alt=' +
                          json.dumps(match[1]) + '}', markdown.read_text())
            markdown.write_text(text)
        process = run_command(make_command('report'), timeout=120, environment=environment)
        if process.returncode or not destination.is_file() or not pdf.is_file():
            raise RuntimeError('Quarto report failed: ' + (process.stderr or process.stdout).strip()[-2000:])
        version_check = run_command(make_command('quarto-version'), timeout=10, environment=environment)
        typst_check = run_command(make_command('typst-version'), timeout=10, environment=environment)
    if not pdf.read_bytes().startswith(b'%PDF-'):
        raise RuntimeError('Quarto did not produce a PDF document.')
    # Preserve generated knitr figure assets for reproduction of the kept Typst source.
    assets = folder / 'report_files'
    if assets.is_dir():
        artifacts.extend(path.relative_to(folder).as_posix() for path in sorted(assets.rglob('*'))
                         if path.is_file())
    artifacts.extend(path.name for path in sorted(folder.glob('report*.md'))
                     if path.name not in artifacts)
    for name in artifacts:
        if not (folder / name).is_file():
            raise RuntimeError('Quarto did not preserve render artifact: ' + name)
    for name in re.findall(r'image\("([^"]+)"', (folder / 'report.typ').read_text()):
        if not (folder / name).is_file():
            raise RuntimeError('Quarto did not preserve figure asset: ' + name)
    if version_check.returncode:
        raise RuntimeError('Quarto version check failed: ' + version_check.stderr.strip()[-2000:])
    version = version_check.stdout.strip()
    if typst_check.returncode:
        raise RuntimeError('Typst version check failed: ' + typst_check.stderr.strip()[-2000:])
    typst_version = (typst_check.stdout or typst_check.stderr).strip()
    if not re.match(r'typst \d+\.\d+\.\d+', typst_version, re.I):
        raise RuntimeError('Typst version was not verified.')
    return {'engine': 'Quarto', 'version': version, 'calculation': 'R',
            'quarto_executed': True,
            'source': f'jobs/{key}/report.qmd' if formal else 'workflow/results.qmd',
            'presentation_source': f'jobs/{key}/report.qmd' if formal else 'workflow/results.qmd',
            'execution_engine': 'knitr' if formal else 'static',
            'plot_generator': 'R from saved results' if formal else 'Python SVG from saved results',
            'formats': ['html', 'typst'], 'view': 'report.pdf',
            'pdf_engine': 'Typst', 'pdf_engine_version': typst_version,
            'artifacts': artifacts}
