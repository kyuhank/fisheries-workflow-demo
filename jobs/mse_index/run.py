"""Index rule: preserve the workflow calculation and its side effects."""

from workflow import mse


async def calculate(workflow, run_id):
    key = 'mse_index'
    return mse.simulate(workflow.output('mse_prepare'), key.removeprefix('mse_'),
                        buffer=workflow.settings['mse_buffer'] if key == 'mse_buffered' else None)
