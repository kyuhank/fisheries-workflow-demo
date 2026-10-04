"""Prepare MSE: preserve the workflow calculation and its side effects."""

from workflow import mse
from workflow.spec import SPEC


async def calculate(workflow, run_id):
    key = 'mse_prepare'
    return mse.prepare({parent: workflow.output(parent) for parent in SPEC[key]['parents']})
