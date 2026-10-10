"""Compare live previews and scheduler scopes using explicit software fixtures.

The minimal CoordinatorWorkflow doubles select monorepo compatibility here;
this planning check performs no numerical or scientific input-contract validation.
"""
import asyncio
import json
from pathlib import Path
import sys
import tempfile

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from tests.coordinator_fixtures import CoordinatorWorkflow as Workflow


async def scenarios(directory):
    runner = Workflow(directory, source_lock=False)
    assert not runner.sources.multi_repository, 'Planning doubles require explicit compatibility mode'
    cases = []

    def save(label):
        plans = [runner.plan(key, scope) for key in runner.spec
                 for scope in ('job', 'workflow')]
        cases.append(json.loads(json.dumps({'label': label, 'state': runner.state(), 'plans': plans})))

    save('Fresh session')
    await runner.run('cpue_summary', scope='job')
    save('Only CPUE summary and its inputs exist')
    await runner.run()
    save('Complete workflow')
    runner.configure({'growth_rate_2': .35, 'min_hooks_a': 1200})
    save('Two independent settings changed')
    await runner.run('cpue_a', scope='job')
    save('CPUE updated; existing descendants need an update')
    await runner.run('assessment_a2', scope='job')
    save('Only one revised growth fit completed')
    return cases


with tempfile.TemporaryDirectory() as directory:
    cases = asyncio.run(scenarios(directory))

with sync_playwright() as playwright:
    browser = playwright.chromium.launch(headless=True)
    page = browser.new_page()
    page.add_script_tag(content=(ROOT / 'app/cloud.js').read_text())
    checked = 0
    for case in cases:
        page.evaluate("""state => {
          window.preview = new CloudRun({url: ''}, state.jobs, () => {}, () => {});
          preview.records = state.records;
        }""", case['state'])
        for expected in case['plans']:
            actual = page.evaluate('args => preview.plan(args.start, args.settings, args.scope)',
                                   {**expected, 'settings': case['state']['settings']})
            assert actual == expected, (case['label'], actual, expected)
            checked += 1
        print('PASS:', case['label'], flush=True)
    browser.close()
    print(f'Passed {checked} live-preview and scheduler comparisons.')
