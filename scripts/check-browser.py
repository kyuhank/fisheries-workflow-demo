"""Check offline browser execution, partial reruns, saved outputs and task views."""
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import zipfile

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from verify import verify


def complete(page):
    page.wait_for_function("document.querySelector('#status-title').textContent === 'Results are ready'", timeout=90000)


with tempfile.TemporaryDirectory() as directory, sync_playwright() as playwright:
    directory = Path(directory)
    options = {'headless': True}
    if os.environ.get('CHROME_PATH'):
        options['executable_path'] = os.environ['CHROME_PATH']
    browser = playwright.chromium.launch(**options)
    context = browser.new_context(offline=True, accept_downloads=True, viewport={'width':1440,'height':1000})
    page = context.new_page()
    errors, requests = [], []
    page.on('pageerror', lambda error: errors.append(str(error)))
    page.on('request', lambda request: requests.append(request.url) if request.url.startswith('http') else None)
    page.goto((ROOT/'docs/index.html').as_uri())
    page.locator('#run:enabled').wait_for(timeout=90000)
    page.locator('#run').click()
    page.locator('[data-tab="jobs"]').click()
    page.wait_for_function("document.querySelector('.task.running') !== null")
    complete(page)
    with page.expect_download() as download:
        page.locator('#download').click()
    download.value.save_as(directory/'browser.zip')
    with zipfile.ZipFile(directory/'browser.zip') as archive:
        archive.extractall(directory/'browser')
    subprocess.run([sys.executable, str(ROOT/'run.py'), '--output', str(directory/'native')],
                   check=True, stdout=subprocess.DEVNULL)
    verify(directory/'browser/reference', directory/'native')
    page.locator('[data-tab="workflow"]').click()
    page.locator('.job[data-job="prepare_a"]').click()
    page.wait_for_function("document.querySelector('#completion').textContent.includes('5 jobs')")
    for _ in range(2):
        page.locator('#run').click(); complete(page)
        assert '5 jobs completed' in page.locator('#status-message').text_content()
    page.locator('.job[data-job="cpue_summary"]').click()
    page.wait_for_function("document.querySelector('#completion').textContent.includes('2 jobs')")
    page.locator('#run').click(); complete(page)
    assert '2 jobs completed' in page.locator('#status-message').text_content()
    page.locator('#mode').select_option('saved')
    assert page.locator('#run').is_hidden()
    page.locator('[data-tab="jobs"]').click()
    page.locator('#tasks .cpue').click()
    assert page.locator('#job-table-body tr').count() == 4
    page.locator('#job-table-body tr[data-job="cpue_a"] button').click()
    assert page.frame_locator('#output-frame').locator('h1').inner_text() == 'CPUE analysis A'
    page.locator('[data-output="log"]').click()
    assert 'Fit a CPUE index' in page.locator('#output-json').text_content()
    page.locator('#output-close').click()
    page.locator('#mode').select_option('live')
    page.locator('#run:enabled').wait_for()
    page.set_viewport_size({'width':390,'height':844})
    assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')
    assert not errors, errors
    assert not requests, requests
    browser.close()
print('Passed: offline calculations, output comparison, repeated partial runs, task views and saved example.')
