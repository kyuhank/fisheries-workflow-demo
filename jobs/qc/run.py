"""Quality check: preserve the workflow calculation and its side effects."""


async def calculate(workflow, run_id):
    submission = workflow.output('submission')
    invalid = [r['set_id'] for r in submission['sets'] if r['hooks'] <= 0 or r['catch_n'] < 0]
    if invalid:
        await workflow.emit('qc', 'failed', 'Zero effort found. Return the record to the data provider.')
        await workflow.emit('submission', 'returned', 'The provider corrects the effort field.')
        await workflow.emit('submission', 'running', 'The provider resubmits the corrected records.',
                        activity='resubmit')
        submission = workflow.source_rows()
        workflow.save('submission', submission, run_id)
        await workflow.emit('submission', 'complete', 'Corrected submission received.')
        await workflow.emit('qc', 'running', 'Check the corrected submission.')
    if any(r['hooks'] <= 0 or r['catch_n'] < 0 for r in submission['sets']):
        raise ValueError('The corrected submission still contains invalid records.')
    if len({r['set_id'] for r in submission['sets']}) != len(submission['sets']):
        raise ValueError('Duplicate observation identifiers.')
    return {'returned': invalid, 'rows': len(submission['sets']), 'checks': [
        {'check':'Positive effort', 'result':'Pass'}, {'check':'Non-negative catch', 'result':'Pass'},
        {'check':'Unique observation IDs', 'result':'Pass'}]}
