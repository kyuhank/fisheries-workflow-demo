"""Explicit scheduler-only doubles. They perform no scientific calculation.

Production save/signature/SQLite paths remain in use, while rendering and the R
backend are replaced for bounded scheduling tests. Native integration has its
own actual R/RTMB/Quarto gate.
"""
import copy
from unittest.mock import patch
from workflow.engine import Workflow as NativeWorkflow, digest, encoded


class CoordinatorBridge:
    def software(self):
        return {'r': 'TEST DOUBLE', 'RTMB': 'TEST DOUBLE', 'jsonlite': 'TEST DOUBLE',
                'container': 'scheduler-only test double; no container execution'}

    async def calculate(self, context):
        key = context['key']
        result = {'job': key, 'job_settings': copy.deepcopy(context['job_settings']),
                  'parents': {name: digest(encoded(value)) for name, value in context['parents'].items()}}
        effects = {}
        if key == 'submission':
            result.update(sets=[], catch=[])
        if key == 'qc':
            corrected = copy.deepcopy(context['parents']['submission'])
            corrected['corrected'] = True
            effects = {'resubmit_submission': corrected}
        return {'result': result, 'effects': effects}


def test_report(root, key, result, record, folder, page):
    (folder / 'report.html').write_text('Explicit scheduler test double: ' + key + ' · ' + record['run_id'])
    return {'engine': 'TEST DOUBLE', 'quarto_executed': False}


class CoordinatorWorkflow(NativeWorkflow):
    def __init__(self, *args, **kwargs):
        kwargs['r_bridge'] = CoordinatorBridge()
        super().__init__(*args, **kwargs)

    def save(self, key, result, run_id):
        with patch('workflow.engine.reports.output_page', return_value='TEST DOUBLE'), \
             patch('workflow.engine.render_report', side_effect=test_report):
            return super().save(key, result, run_id)
