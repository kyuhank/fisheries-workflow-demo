"""Assessment B2: preserve the workflow calculation and its side effects."""

from workflow import models


async def calculate(workflow, run_id):
    key = 'assessment_b2'
    return models.assessment(workflow.output('prepare_' + key[-2])['rows'], workflow.job_settings(key)['M'])
