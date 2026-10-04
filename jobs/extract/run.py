"""Extract data: preserve the workflow calculation and its side effects."""

import sqlite3
from workflow.engine import ROOT


async def calculate(workflow, run_id):
    sql = (ROOT / 'workflow/extract.sql').read_text()
    catch_sql = (ROOT / 'workflow/extract-catch.sql').read_text()
    with sqlite3.connect(workflow.directory / 'database/snapshot.sqlite') as db:
        db.row_factory = sqlite3.Row
        return {'sets': [dict(r) for r in db.execute(sql)],
                'catch': [dict(r) for r in db.execute(catch_sql)], 'sql': sql + '\n' + catch_sql}
