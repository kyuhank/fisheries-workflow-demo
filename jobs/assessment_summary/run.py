"""Compare assessments: preserve the workflow calculation and its side effects."""

from workflow.spec import SPEC


async def calculate(workflow, run_id):
    key = 'assessment_summary'
    result = {'series': {SPEC[p]['title']: workflow.output(p)['series'] for p in SPEC[key]['parents']}}
    if key == 'assessment_summary':
        result['diagnostics'] = [{'case': SPEC[p]['title'], 'M': workflow.output(p)['M'],
                                  'boundary_fit': workflow.output(p)['boundary_fit'],
                                  'catch_check': workflow.output(p)['catch_check']}
                                 for p in SPEC[key]['parents']]
    return result
