"""Prepare inputs A: preserve the workflow calculation and its side effects."""


async def calculate(workflow, run_id):
    key = 'prepare_a'
    index = workflow.output('cpue_' + key[-1])['series']
    catch = {r['year']: r['catch_t'] for r in workflow.output('extract')['catch']}
    if any(r['year'] not in catch for r in index):
        raise ValueError('A CPUE year has no matching catch.')
    return {'rows': [{**r, 'catch_t': catch[r['year']]} for r in index]}
