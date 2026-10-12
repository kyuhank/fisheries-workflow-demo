"""Compare live previews and scheduler scopes using explicit software fixtures.

The minimal CoordinatorWorkflow doubles select monorepo compatibility here;
public source selection retains native byte and metadata checks. Downstream
results remain scheduler fixtures, without numerical or scientific validation.
"""
import asyncio
from copy import deepcopy
import json
from pathlib import Path
import sys
import tempfile

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from tests.coordinator_fixtures import CoordinatorBridge, CoordinatorWorkflow
from workflow.engine import Workflow as NativeWorkflow


class PublicPlanningBridge(CoordinatorBridge):
    """Preserve actual public rows for SQLite; downstream calculations remain doubles."""
    async def calculate(self, context):
        response = await super().calculate(context)
        if context['key'] == 'submission':
            source = context['source']
            assert source['data_kind'] == 'public-wcpfc-albacore'
            last_year = context['settings']['last_year']
            response['result'].update(
                data_kind=source['data_kind'], metadata=deepcopy(source['metadata']),
                sets=deepcopy([row for row in source['sets'] if row['year'] <= last_year]),
                catch=deepcopy([row for row in source['catch'] if row['year'] <= last_year]))
        return response


class Workflow(CoordinatorWorkflow):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.calculator = PublicPlanningBridge()

    def source_context(self):
        return NativeWorkflow.source_context(self)


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
    runner.configure({'last_year': 2022, 'growth_rate_2': .35})
    save('Two independent settings changed')
    await runner.run('extract', scope='job')
    save('Snapshot updated; existing descendants need an update')
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
