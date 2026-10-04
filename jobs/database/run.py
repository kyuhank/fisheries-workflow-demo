"""Prepare and load: preserve the workflow calculation and its side effects."""

import sqlite3
from workflow import models


async def calculate(workflow, run_id):
    key = 'database'
    result = workflow.output('submission')
    folder = workflow.directory / key; folder.mkdir(exist_ok=True)
    dbfile = folder / 'snapshot.sqlite'; dbfile.unlink(missing_ok=True)
    with sqlite3.connect(dbfile) as db:
        db.execute('CREATE TABLE sets(set_id TEXT PRIMARY KEY,year INTEGER,vessel TEXT,hooks INTEGER CHECK(hooks>0),catch_n INTEGER CHECK(catch_n>=0))')
        db.execute('CREATE TABLE removals(year INTEGER PRIMARY KEY,catch_t REAL CHECK(catch_t>=0))')
        db.executemany('INSERT INTO sets VALUES(?,?,?,?,?)', [[r[k] for k in ['set_id','year','vessel','hooks','catch_n']] for r in result['sets']])
        db.executemany('INSERT INTO removals VALUES(?,?)', [[r['year'],r['catch_t']] for r in result['catch']])
    years = [r['year'] for r in result['sets']]
    return {'rows': len(years), 'first_year': min(years), 'last_year': max(years),
            **models.describe_data(result['sets'], result['catch'])}
