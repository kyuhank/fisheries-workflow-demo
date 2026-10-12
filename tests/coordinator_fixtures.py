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
                  'fixture': 'scheduler-only TEST DOUBLE; no scientific calculation',
                  'parents': {name: digest(encoded(value)) for name, value in context['parents'].items()}}
        years = range(context['settings']['last_year'] - 2, context['settings']['last_year'] + 1)
        effects = {}
        if key == 'submission':
            result.update(sets=[], catch=[])
        elif key == 'extract':
            result.update(sets=[], catch=[{'year': year, 'catch_t': 1.0} for year in years])
        elif key in ('cpue_a', 'cpue_b'):
            result['series'] = [{'year': year, 'index': 1.0} for year in years]
        elif key in ('prepare_a', 'prepare_b'):
            catches = {row['year']: row['catch_t'] for row in context['parents']['extract']['catch']}
            result['series'] = [{**row, 'catch_t': catches[row['year']]}
                                for row in context['parents']['cpue_' + key[-1]]['series']]
            result['units'] = {'catch_t': 'tonnes', 'index': 'relative CPUE'}
        elif key in ('assessment_a1', 'assessment_a2', 'assessment_b1', 'assessment_b2'):
            result.update(K=10.0, r=context['job_settings']['r'], q=1.0, next_biomass_t=5.0)
            result['series'] = [{'year': row['year'], 'catch_t': row['catch_t'],
                                 'observed_index': row['index']}
                                for row in context['parents']['prepare_' + key[-2]]['series']]
            result['units'] = {'catch_t': 'tonnes', 'biomass_t': 'tonnes', 'observed_index': 'relative CPUE'}
        if key == 'qc':
            corrected = copy.deepcopy(context['parents']['submission'])
            corrected['corrected'] = True
            effects = {'resubmit_submission': corrected}
        return {'result': result, 'effects': effects}


def test_report(root, key, result, record, folder, result_html, source_path=None):
    (folder / 'report.html').write_text('Explicit scheduler test double: ' + key + ' · ' + record['run_id'])
    return {'engine': 'TEST DOUBLE', 'quarto_executed': False}


class CoordinatorWorkflow(NativeWorkflow):
    def __init__(self, *args, **kwargs):
        kwargs['r_bridge'] = CoordinatorBridge()
        super().__init__(*args, **kwargs)

    def source_context(self):
        # The bridge supplies empty synthetic rows and the corresponding SQLite
        # schema. Public/hosted/frozen input selection belongs to native tests.
        return {'data_kind': 'synthetic-scheduler-fixture', 'sets': [], 'catch': [],
                'submission': None}

    def save(self, key, result, run_id):
        with patch('workflow.engine.reports.output_page', return_value='TEST DOUBLE'), \
             patch('workflow.engine.render_report', side_effect=test_report):
            return super().save(key, result, run_id)
