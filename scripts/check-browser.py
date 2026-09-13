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
    page.locator('#offline-fallback:visible').wait_for(timeout=40000)
    page.locator('#offline-fallback').click()
    assert page.locator('#mode').input_value() == 'live'
    assert 'without internet' in page.locator('#mode-help').inner_text()
    # Runtime loading must not overwrite the example if the reader switches away.
    page.locator('#mode').select_option('saved')
    page.wait_for_function('offlineReady === true', timeout=90000)
    page.locator('.job[data-job="cpue_a"]').click()
    assert page.locator('.workflow-node.complete').count() == 16
    assert page.locator('#download').is_enabled()
    page.locator('#mode').select_option('live')
    page.locator('#run:enabled').wait_for(timeout=90000)
    page.evaluate("""() => {
      window.sequence = [];
      new MutationObserver(() => {
        const nodes = [...document.querySelectorAll('.job[data-job]')];
        const running = nodes.filter(n => n.classList.contains('running')).map(n => n.dataset.job);
        const phase = nodes.filter(n => /running|failed|returned/.test(n.getAttribute('class')))
          .map(n => [n.dataset.job, n.getAttribute('class'), n.dataset.activity || '']);
        const signature = JSON.stringify(phase);
        if (window.sequence.at(-1)?.signature !== signature)
          window.sequence.push({time: performance.now(), signature, running, phase});
      }).observe(document.querySelector('#workflow-view'), {subtree:true, attributes:true, childList:true});
    }""")
    page.locator('#run').click()
    page.locator('[data-tab="jobs"]').click()
    page.wait_for_function("document.querySelector('.task.running') !== null")
    assert page.locator('.task.running .task-status').inner_text() == 'Running'
    assert page.locator('.task.running .spinner').count() == 1
    complete(page)
    sequence = page.evaluate('window.sequence')
    assert next(item['running'] for item in sequence if item['running']) == ['submission']
    resubmit = next(i for i, item in enumerate(sequence)
                    if any(job == 'submission' and activity == 'resubmit'
                           for job, _, activity in item['phase']))
    assert sequence[resubmit + 1]['time'] - sequence[resubmit]['time'] >= 850
    assert any(item['running'] == ['database'] for item in sequence)
    assert any(set(item['running']) == {'cpue_a', 'cpue_b'} for item in sequence)
    assert any({'prepare_a', 'prepare_b'} <= set(item['running']) for item in sequence)
    assert any({'assessment_a1', 'assessment_a2', 'assessment_b1', 'assessment_b2'}
               <= set(item['running']) for item in sequence)
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
    # A mode switch must not mix settings, plans or records from different runs.
    page.locator('#snapshot').select_option('2024')
    page.wait_for_function("document.querySelector('#status-title').textContent === 'New settings · previous results kept'")
    assert '2023 → 2024' in page.locator('#status-message').inner_text()
    page.locator('#mode').select_option('saved')
    assert page.locator('#run').is_hidden()
    assert page.locator('#snapshot').input_value() == '2023'
    assert 'does not run code' in page.locator('#mode-note').inner_text()
    page.locator('#mode').select_option('live')
    page.locator('#run:enabled').wait_for()
    assert page.locator('#snapshot').input_value() == '2024'
    assert 'previous results kept' in page.locator('#status-title').inner_text()
    page.locator('#snapshot').select_option('2023')
    page.wait_for_function("document.querySelectorAll('.workflow-node.outdated').length === 0")
    page.locator('#mode').select_option('saved')
    page.locator('#mode').select_option('live')
    page.locator('#run:enabled').wait_for()
    assert page.locator('.workflow-node.outdated').count() == 0
    assert '2 jobs' in page.locator('#completion').inner_text()
    page.locator('#mode').select_option('saved')
    page.locator('[data-tab="jobs"]').click()
    page.locator('#tasks .cpue').click()
    assert page.locator('#job-table-body tr').count() == 4
    page.locator('#job-table-body tr[data-job="cpue_a"] .job-name').click()
    assert page.locator('#selection-title').inner_text() == 'CPUE analysis A'
    page.locator('#job-table-body tr[data-job="cpue_a"] .open-output').click()
    assert page.frame_locator('#output-frame').locator('h1').inner_text() == 'CPUE analysis A'
    page.locator('[data-output="log"]').click()
    assert 'Fit a CPUE index' in page.locator('#output-json').text_content()
    page.locator('#output-close').click()
    page.locator('#mode').select_option('live')
    page.locator('#run:enabled').wait_for()
    page.locator('[data-tab="workflow"]').click()
    page.locator('#reset').click()
    page.locator('#run:enabled').wait_for()
    page.locator('#handover').select_option('manual')
    page.locator('#run').click()
    page.locator('#handover-panel:visible').wait_for(timeout=90000)
    assert page.locator('#handover-title').inner_text() == 'Data manager → CPUE analyst'
    assert page.locator('.job[data-job="cpue_a"]').get_attribute('class').split().count('handover') == 1
    assert 'Fit a CPUE index' not in page.locator('#execution-log').inner_text()
    page.locator('#transfer-files').click()
    page.wait_for_function("document.querySelector('#handover-panel').hidden === false && document.querySelector('#handover-title').textContent === 'CPUE analyst → Assessment analyst'", timeout=90000)
    page.locator('#transfer-files').click()
    complete(page)
    page.locator('#revise-cpue').click()
    page.locator('.job[data-job="assessment_a1"].outdated').wait_for()
    page.locator('#run:enabled').click()
    page.locator('#handover-panel:visible').wait_for(timeout=90000)
    assert page.locator('#handover-title').inner_text() == 'CPUE analyst → Assessment analyst'
    page.locator('[data-tab="jobs"]').click()
    page.locator('#all-tasks').click()
    assert page.locator('#job-table-body tr[data-job="cpue_a"] td').nth(3).inner_text() == 'Run 002'
    assert page.locator('#job-table-body tr[data-job="assessment_a1"] td').nth(3).inner_text() == 'Run 001'
    page.locator('[data-tab="workflow"]').click()
    page.locator('#connect-workflow').click()
    complete(page)
    assert page.locator('#handover').input_value() == 'connected'
    assert '8 jobs completed' in page.locator('#status-message').inner_text()
    page.set_viewport_size({'width':390,'height':844})
    assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')
    assert not errors, errors
    assert not [url for url in requests if '/functions/v1/paper-api/info' not in url], requests
    browser.close()
print('Passed: offline calculations, output comparison, repeated partial runs, task views, saved example and manual transfers after a revision.')
