"""CPUE analysis A: preserve the workflow calculation and its side effects."""

from workflow import models


async def calculate(workflow, run_id):
    key = 'cpue_a'
    return models.cpue(workflow.output('extract')['sets'], key == 'cpue_a',
                       workflow.settings['min_hooks_a'] if key == 'cpue_a' else 0)
