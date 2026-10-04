"""Data submission: preserve the workflow calculation and its side effects."""


async def calculate(workflow, run_id):
    result = workflow.source_rows()
    result['sets'][0]['hooks'] = 0
    return result
