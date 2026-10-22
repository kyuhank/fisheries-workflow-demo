"""Check SVG layout and output controls in Chromium or WebKit."""
import argparse
from contextlib import contextmanager
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
import importlib.util
import json
import os
from pathlib import Path
from threading import Thread

from playwright.sync_api import sync_playwright

from pdf_checks import assert_pdf_output, close_pdf_output, expected_record

ROOT = Path(__file__).resolve().parents[1]
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("--engine", choices=("chromium", "webkit"), default="chromium")
parser.add_argument("--executable", default=os.environ.get("CHROME_PATH"))
parser.add_argument("--screenshots", type=Path)
args = parser.parse_args()


@contextmanager
def hosted_docs():
    """Serve current UI sources with saved reports, without running analyses."""
    spec = importlib.util.spec_from_file_location('handover_preview', ROOT / 'scripts/check-handover.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    html, _ = module.preview()
    index = html.encode()

    class QuietHandler(SimpleHTTPRequestHandler):
        def log_message(self, *_):
            pass

        def do_GET(self):
            if self.path.split('?', 1)[0] in ('/', '/index.html'):
                self.send_response(200)
                self.send_header('Content-Type', 'text/html; charset=utf-8')
                self.send_header('Content-Length', str(len(index)))
                self.end_headers()
                self.wfile.write(index)
            elif self.path == '/favicon.ico':
                self.send_response(204)
                self.end_headers()
            else:
                super().do_GET()

    with ThreadingHTTPServer(('127.0.0.1', 0), partial(QuietHandler, directory=ROOT/'docs')) as server:
        Thread(target=server.serve_forever, daemon=True).start()
        try:
            yield f'http://127.0.0.1:{server.server_port}/index.html'
        finally:
            server.shutdown()


with hosted_docs() as url, sync_playwright() as playwright:
    options = {"executable_path": args.executable} if args.executable else (
        {"channel": "chromium"} if args.engine == "chromium" else {})
    browser = getattr(playwright, args.engine).launch(**options)
    page = browser.new_page(viewport={"width": 1440, "height": 1050})
    page.route("https://**/*", lambda route: route.abort())
    errors = []
    page.on("pageerror", lambda error: errors.append(str(error)))
    page.goto(url, wait_until="domcontentloaded")
    page.locator("#mode").select_option("saved")
    page.locator('.job[data-job="submission"].complete').wait_for()
    checks = []
    for width, zoom in ((1440, 1), (1024, 1), (1440, 1.25), (390, 1)):
        page.set_viewport_size({"width": width, "height": 1050})
        page.evaluate("zoom => document.body.style.zoom = zoom", str(zoom))
        problems = page.evaluate("""() => {
            const problems = [];
            const layout = JSON.parse(document.querySelector('#demo-payload').textContent).diagram;
            if (document.querySelector('foreignObject')) problems.push('HTML node inside SVG');
            for (const node of layout.nodes) {
                const group = document.querySelector(`.job[data-job="${node.key}"]`);
                const shape = group.querySelector('.node-shape');
                const bounds = shape.getBoundingClientRect();
                const matrix = group.getScreenCTM();
                const expected = new DOMPoint(0, 0).matrixTransform(matrix);
                if (Math.abs(bounds.x - expected.x) > 1 || Math.abs(bounds.y - expected.y) > 1)
                    problems.push(node.key + ': displaced box');
                for (const text of group.querySelectorAll('text')) {
                    const b = text.getBoundingClientRect();
                    if (b.width && (b.left < bounds.left - 1 || b.right > bounds.right + 1 ||
                                   b.top < bounds.top - 1 || b.bottom > bounds.bottom + 1))
                        problems.push(node.key + ': text outside box: ' + text.textContent);
                }
                const viewControl = group.querySelector('.node-view rect').getBoundingClientRect();
                for (const line of group.querySelectorAll('.node-status tspan')) {
                    const b = line.getBoundingClientRect();
                    if (b.left < viewControl.right && b.right > viewControl.left &&
                        b.top < viewControl.bottom && b.bottom > viewControl.top)
                        problems.push(node.key + ': state text overlaps output control');
                }
                const title = group.querySelector('.node-title');
                const renderedTitleSize = parseFloat(getComputedStyle(title).fontSize) *
                    Math.hypot(matrix.a, matrix.b);
                if (renderedTitleSize < 12)
                    problems.push(node.key + ': title too small at rendered size: ' + renderedTitleSize);
                if (!group.querySelector('.node-status').textContent.includes('Complete'))
                    problems.push(node.key + ': missing state text');
            }
            if (document.documentElement.scrollWidth > innerWidth + 1)
                problems.push('page overflows horizontally');
            const guideText = document.querySelector('#view-guide-description').getBoundingClientRect();
            const guideLink = document.querySelector('#view-guide-link').getBoundingClientRect();
            if (guideText.left < guideLink.right && guideText.right > guideLink.left &&
                guideText.top < guideLink.bottom && guideText.bottom > guideLink.top)
                problems.push('view guide text overlaps its switch link');
            return problems;
        }""")
        assert not problems, (width, zoom, problems)
        checks.append({"viewport": width, "zoom": zoom, "nodes": page.locator(".workflow-node").count()})
    page.set_viewport_size({"width": 1440, "height": 1050})
    page.evaluate("document.body.style.zoom = '1'")
    node = page.locator('.job[data-job="cpue_a"]')
    node.click()
    assert page.locator("#selection-title").inner_text() == "CPUE analysis A"
    assert not page.locator("#output-dialog").is_visible()
    expected = expected_record(page, "cpue_a")
    node.locator(".node-view").press("Enter")
    assert_pdf_output(page, "cpue_a", expected, phrases=("CPUE",),
                      save=True, open_link=args.engine == "chromium")
    close_pdf_output(page)
    page.locator('.job[data-job="prepare_a"]').press("Enter")
    assert page.locator("#selection-title").inner_text() == "Prepare inputs A"
    page.locator('[data-tab="jobs"]').click()
    assert page.locator('#tasks .task').count() == page.evaluate('taskGroups.length')
    assert page.locator('#workspace-activity').bounding_box()['height'] < 50
    page.locator('#tasks .assessment').click()
    assert page.locator('#job-table-body tr').count() == 8
    expected = expected_record(page, 'assessment_a1')
    page.locator('#job-table-body tr[data-job="assessment_a1"] .open-output').click()
    assert_pdf_output(page, 'assessment_a1', expected, phrases=('Assessment A1',))
    close_pdf_output(page)
    page.locator('#show-tasks').click()
    page.locator('#tasks .mse').click()
    assert page.locator('#job-table-body tr').count() == 6
    expected = expected_record(page, 'mse_report')
    page.locator('#job-table-body tr[data-job="mse_report"] .open-output').click()
    assert_pdf_output(page, 'mse_report', expected,
                      phrases=('Management strategy comparison',))
    assert page.evaluate('currentOutput.record.job') == 'mse_report'
    close_pdf_output(page)
    page.locator('[data-tab="workflow"]').click()
    assert page.locator('[data-reference]').count() == 0
    page.locator('.workflow-node[data-job="mse_prepare"] .node-view').press('Enter')
    page.locator('[data-output="record"]').click()
    assert page.locator('#output-record').is_visible()
    assert page.locator('#output-title').inner_text() == 'Prepare MSE'
    assert page.locator('#output-record .record-input').count() == 4
    edges = page.evaluate('payload.diagram.edges.filter(edge => edge.to === "mse_prepare")')
    nodes = page.evaluate('Object.fromEntries(payload.diagram.nodes.map(node => [node.key, node]))')
    assert {edge['from'] for edge in edges} == {
        'assessment_a1', 'assessment_a2', 'assessment_b1', 'assessment_b2'}
    # Allow separate ports and box clearance; check proximity and route direction.
    for edge in edges:
        source, target = nodes[edge['from']], nodes[edge['to']]
        first, last = edge['points'][0], edge['points'][-1]
        assert abs(first[0] - source['x'] - source['width']) <= 4
        assert source['y'] <= first[1] <= source['y'] + source['height']
        assert target['x'] <= last[0] <= target['x'] + target['width']
        assert abs(last[1] - target['y']) <= 4
    for edge in page.evaluate('payload.diagram.edges'):
        points = edge['points']
        for start, end in zip(points, points[1:]):
            assert start != end, edge
            assert start[0] == end[0] or start[1] == end[1], edge
    page.locator('#output-close').click()
    page.locator('[data-tab="jobs"]').click()
    page.locator('#running-jobs').click()
    assert page.locator('#job-table-body').inner_text() == 'No jobs in this state.'
    page.locator('#show-tasks').click()
    page.set_viewport_size({'width': 390, 'height': 844})
    assert page.evaluate('document.documentElement.scrollWidth <= innerWidth + 1')

    # Saved Complete cards miss the longer labels emitted during an actual run.
    # Keep real saved records, so View remains present while each status is shown.
    live_checks = []
    for width, zoom in ((1440, 1), (1024, 1), (1440, 1.25), (390, 1)):
        page.set_viewport_size({'width': width, 'height': 1050})
        page.evaluate('zoom => document.body.style.zoom = zoom', str(zoom))
        for state, activity, label in (
            ('running', 'rendering', 'Rendering PDF'),
            ('running', 'calculating', 'Calculating'),
            ('running', 'preparing', 'Preparing'),
            ('unconfirmed', '', 'Status unavailable'),
            ('handover', '', 'Awaiting file'),
            ('outdated', '', 'Inputs changed'),
            ('retained', '', 'Retained'),
            ('waiting', '', 'Waiting'),
        ):
            page.evaluate("""({state, activity}) => {
                busy = true;
                states = Object.fromEntries(jobs.map(job => [job.key, state]));
                activities = Object.fromEntries(jobs.map(job => [job.key, activity]));
                selectedTask = null;
                jobStatusFilter = '';
                workspaceView = 'jobs';
                render();
            }""", {'state': state, 'activity': activity})
            page.locator('[data-tab="workflow"]').click()
            problems = page.evaluate("""label => {
                const problems = [];
                const overlap = (a, b) => a.left < b.right && a.right > b.left &&
                    a.top < b.bottom && a.bottom > b.top;
                for (const group of document.querySelectorAll('.workflow-node')) {
                    const key = group.dataset.job;
                    const bounds = group.querySelector('.node-shape').getBoundingClientRect();
                    const status = group.querySelector('.node-status');
                    if (status.getAttribute('aria-label') !== label)
                        problems.push(key + ': incomplete accessible status');
                    const view = group.querySelector('.node-view rect').getBoundingClientRect();
                    for (const line of group.querySelectorAll('text tspan, text:not(:has(tspan))')) {
                        const b = line.getBoundingClientRect();
                        if (!b.width || !b.height) continue;
                        if (b.left < bounds.left - 1 || b.right > bounds.right + 1 ||
                            b.top < bounds.top - 1 || b.bottom > bounds.bottom + 1)
                            problems.push(key + ': text outside box: ' + line.textContent);
                        if (line.closest('.node-status') && overlap(b, view))
                            problems.push(key + ': status overlaps View: ' + line.textContent);
                    }
                }
                if (document.documentElement.scrollWidth > innerWidth + 1)
                    problems.push('page overflows horizontally');
                return problems;
            }""", label)
            assert not problems, (width, zoom, label, problems)
            if args.screenshots and label == 'Rendering PDF':
                args.screenshots.mkdir(parents=True, exist_ok=True)
                page.screenshot(path=str(args.screenshots / f'workflow-{width}-{zoom}.png'), full_page=True)
            page.locator('[data-tab="jobs"]').click()
            problems = page.evaluate("""() => {
                const problems = [];
                for (const badge of document.querySelectorAll('#job-table-body .state')) {
                    const b = badge.getBoundingClientRect();
                    const cell = badge.closest('td').getBoundingClientRect();
                    if (!b.width || b.left < cell.left - 1 || b.right > cell.right + 1)
                        problems.push(badge.closest('tr').dataset.job + ': status outside cell');
                    const text = badge.querySelector('.status-label').getBoundingClientRect();
                    if (text.left < b.left - 1 || text.right > b.right + 1 ||
                        text.top < b.top - 1 || text.bottom > b.bottom + 1)
                        problems.push(badge.closest('tr').dataset.job + ': label outside badge');
                }
                if (document.documentElement.scrollWidth > innerWidth + 1)
                    problems.push('jobs page overflows horizontally');
                return problems;
            }""")
            assert not problems, (width, zoom, label, problems)
            if args.screenshots and label == 'Rendering PDF':
                page.screenshot(path=str(args.screenshots / f'jobs-{width}-{zoom}.png'), full_page=True)
            live_checks.append({'viewport': width, 'zoom': zoom, 'state': label, 'nodes': 22})
    assert not errors, errors
    browser.close()
print(json.dumps({"engine": args.engine, "layout": checks, "live_layout": live_checks,
                  "selection_and_output": "passed"}))
