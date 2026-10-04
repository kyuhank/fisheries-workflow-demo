"""Assessment report: preserve the workflow calculation and its side effects."""

from workflow.spec import SPEC


async def calculate(workflow, run_id):
    key = 'assessment_report'
    return workflow.output(SPEC[key]['parents'][0])
