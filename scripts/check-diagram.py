"""Check SVG layout and output controls in Chromium or WebKit."""
import argparse
from contextlib import contextmanager
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
from threading import Thread

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[1]
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("--engine", choices=("chromium", "webkit"), default="chromium")
parser.add_argument("--executable", default=os.environ.get("CHROME_PATH"))
args = parser.parse_args()


@contextmanager
def hosted_docs():
    """The lightweight page fetches its runtime from the same web origin."""
    class QuietHandler(SimpleHTTPRequestHandler):
        def log_message(self, *_):
            pass

    with ThreadingHTTPServer(('127.0.0.1', 0), partial(QuietHandler, directory=ROOT/'docs')) as server:
        Thread(target=server.serve_forever, daemon=True).start()
        try:
            yield f'http://127.0.0.1:{server.server_port}/index.html'
        finally:
            server.shutdown()


with hosted_docs() as url, sync_playwright() as playwright:
    options = {"executable_path": args.executable} if args.executable else {}
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
                if (!group.querySelector('.node-status').textContent.includes('Complete'))
                    problems.push(node.key + ': missing state text');
            }
            if (document.documentElement.scrollWidth > innerWidth + 1)
                problems.push('page overflows horizontally');
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
    node.locator(".node-view").press("Enter")
    assert page.frame_locator("#output-frame").locator("h1").inner_text() == "CPUE analysis A"
    page.locator("#output-close").click()
    page.locator('.job[data-job="prepare_a"]').press("Enter")
    assert page.locator("#selection-title").inner_text() == "Prepare inputs A"
    page.locator('[data-tab="jobs"]').click()
    assert page.locator('#tasks .task').count() == page.evaluate('taskGroups.length')
    assert page.locator('#workspace-activity').bounding_box()['height'] < 50
    page.locator('#tasks .assessment').click()
    assert page.locator('#job-table-body tr').count() == 8
    page.locator('#job-table-body tr[data-job="assessment_a1"] .open-output').click()
    assert page.frame_locator('#output-frame').locator('h1').inner_text() == 'Assessment A1'
    page.locator('#output-close').click()
    page.locator('#show-tasks').click()
    page.locator('#tasks .mse').click()
    assert page.locator('#job-table-body tr').count() == 6
    page.locator('#job-table-body tr[data-job="mse_report"] .open-output').click()
    assert page.frame_locator('#output-frame').locator('h1').inner_text() == 'MSE report'
    page.locator('#output-close').click()
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
    for edge in edges:
        source, target = nodes[edge['from']], nodes[edge['to']]
        assert edge['points'][0] == [source['x'] + source['width'], source['y'] + source['height'] / 2]
        assert edge['points'][-1] == [target['x'] + target['width'] / 2, target['y']]
    page.locator('#output-close').click()
    page.locator('[data-tab="jobs"]').click()
    page.locator('#running-jobs').click()
    assert page.locator('#job-table-body').inner_text() == 'No jobs in this state.'
    page.locator('#show-tasks').click()
    page.set_viewport_size({'width': 390, 'height': 844})
    assert page.evaluate('document.documentElement.scrollWidth <= innerWidth + 1')
    assert not errors, errors
    browser.close()
print(json.dumps({"engine": args.engine, "layout": checks, "selection_and_output": "passed"}))
