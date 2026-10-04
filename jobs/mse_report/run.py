"""MSE report: preserve the workflow calculation and its side effects."""

from workflow import mse


async def calculate(workflow, run_id):
    return workflow.output('mse_summary')
