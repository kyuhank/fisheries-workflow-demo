"""Check SVG layout and output controls in Chromium or WebKit."""
import argparse
import json
import os
from pathlib import Path

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[1]
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("--engine", choices=("chromium", "webkit"), default="chromium")
parser.add_argument("--executable", default=os.environ.get("CHROME_PATH"))
args = parser.parse_args()

with sync_playwright() as playwright:
    options = {"executable_path": args.executable} if args.executable else {}
    browser = getattr(playwright, args.engine).launch(**options)
    page = browser.new_page(viewport={"width": 1440, "height": 1050})
    page.route("https://**/*", lambda route: route.abort())
    errors = []
    page.on("pageerror", lambda error: errors.append(str(error)))
    page.goto((ROOT / "docs/index.html").as_uri(), wait_until="domcontentloaded")
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
        checks.append({"viewport": width, "zoom": zoom, "nodes": 16})
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
    assert not errors, errors
    browser.close()
print(json.dumps({"engine": args.engine, "layout": checks, "selection_and_output": "passed"}))
