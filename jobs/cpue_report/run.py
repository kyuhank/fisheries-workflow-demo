"""CPUE report: preserve the workflow calculation and its side effects."""

from workflow.spec import SPEC


async def calculate(workflow, run_id):
    key = 'cpue_report'
    return workflow.output(SPEC[key]['parents'][0])
