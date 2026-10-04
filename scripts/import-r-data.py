"""Store the container-generated R fixture as real SQLite and raw submission JSON.

This adapter selects file destinations and validates structure. The synthetic
fishery calculation and declared truth are in scripts/generate-data.R.
"""
import argparse
import hashlib
import os
import re
import json
import math
from pathlib import Path
import sqlite3


def import_data(source, destination):
    source_bytes = source.read_bytes()
    data = json.loads(source_bytes)
    # Validate serialisation before replacing any existing data file.
    json.dumps(data, allow_nan=False)
    if set(data) != {'sets', 'catch', 'scenario'}:
        raise ValueError('The R data fixture must declare sets, catch and scenario.')
    sets = data['sets']
    catch = data['catch']
    columns = ('set_id', 'year', 'vessel', 'hooks', 'catch_n')
    if not sets or not catch or len({row['set_id'] for row in sets}) != len(sets):
        raise ValueError('R fixture observation identifiers must be present and unique.')
    if any(set(row) != set(columns) or type(row['year']) is not int or
           type(row['hooks']) not in (int, float) or not math.isfinite(row['hooks']) or
           type(row['catch_n']) not in (int, float) or not math.isfinite(row['catch_n']) or
           row['hooks'] <= 0 or row['catch_n'] < 0 for row in sets):
        raise ValueError('R fixture contains an invalid observation.')
    if len({row['year'] for row in catch}) != len(catch) or any(
            set(row) != {'year', 'catch_t'} or type(row['year']) is not int or
            type(row['catch_t']) not in (int, float) or not math.isfinite(row['catch_t']) or
            row['catch_t'] < 0 for row in catch):
        raise ValueError('R fixture removal years must be unique and catches non-negative.')
    previous = sorted((row for row in sets if row['year'] <= 2023), key=lambda row: (row['year'], row['set_id']))
    latest = sorted((row for row in sets if row['year'] == 2024), key=lambda row: row['set_id'])
    latest_catch = [row['catch_t'] for row in catch if row['year'] == 2024]
    if (not previous or not latest or len(latest_catch) != 1 or
            {row['year'] for row in sets} != set(range(2000, 2025)) or
            {row['year'] for row in catch} != set(range(2000, 2025)) or
            data['scenario'].get('type') != 'synthetic-schaefer-poisson'):
        raise ValueError('R fixture must provide the fixed snapshots through 2024.')
    commit, repository, run_id = (os.environ.get(name) for name in
                                 ('GITHUB_SHA', 'GITHUB_REPOSITORY', 'GITHUB_RUN_ID'))
    image = os.environ.get('PAPER_RUNTIME_IMAGE')
    if any((commit, repository, run_id, image)):
        if (not commit or not re.fullmatch(r'[0-9a-f]{40}', commit) or
                not repository or not re.fullmatch(r'[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+', repository) or
                not run_id or not run_id.isdigit() or
                not image or not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9._:/-]*@sha256:[0-9a-f]{64}', image)):
            raise ValueError('Data preparation requires complete actual CI source and image identity.')
    destination.mkdir(parents=True, exist_ok=True)
    temporary = destination / 'fishery.sqlite.new'
    if temporary.exists():
        raise ValueError('An interrupted fixture import already exists; inspect it before retrying.')
    with sqlite3.connect(temporary) as db:
        db.execute('CREATE TABLE sets(set_id TEXT PRIMARY KEY,year INTEGER,vessel TEXT,hooks INTEGER CHECK(hooks>0),catch_n INTEGER CHECK(catch_n>=0))')
        db.execute('CREATE TABLE removals(year INTEGER PRIMARY KEY,catch_t REAL CHECK(catch_t>=0))')
        db.executemany('INSERT INTO sets VALUES(?,?,?,?,?)', [[row[name] for name in columns] for row in previous])
        db.executemany('INSERT INTO removals VALUES(?,?)', [[row['year'], row['catch_t']] for row in catch if row['year'] <= 2023])
    temporary.replace(destination / 'fishery.sqlite')
    submission = {'sets': [[row[name] for name in columns] for row in latest], 'catch': latest_catch[0]}
    for name, value in [('submission.json', submission), ('scenario.json', data['scenario'])]:
        (destination / name).write_text(json.dumps(value, indent=2, allow_nan=False) + '\n')
    (destination / 'source-data.json').write_bytes(source_bytes)
    root = Path(__file__).resolve().parents[1]
    sha = lambda path: hashlib.sha256(path.read_bytes()).hexdigest()
    manifest = {
        'schema_version': 1, 'type': 'R-fixture-import',
        'generator': {'path': 'scripts/generate-data.R', 'sha256': sha(root / 'scripts/generate-data.R')},
        'adapter': {'path': 'scripts/import-r-data.py', 'sha256': sha(Path(__file__))},
        'input': {'path': 'data/source-data.json', 'sha256': hashlib.sha256(source_bytes).hexdigest()},
        'truth': {'path': 'data/scenario.json', 'sha256': sha(destination / 'scenario.json'),
                  'type': data['scenario'].get('type'), 'R': data['scenario'].get('R'),
                  'seed': data['scenario'].get('seed'), 'rng': data['scenario'].get('rng')},
        'outputs': {name: sha(destination / name) for name in
                    ('fishery.sqlite', 'submission.json', 'scenario.json', 'source-data.json')},
    }
    if any((commit, repository, run_id, image)):
        manifest['source'] = {'repository': 'https://github.com/' + repository, 'commit': commit}
        manifest['execution'] = {'provider': 'GitHub Actions', 'purpose': 'source-data-preparation',
                                 'github_run': run_id, 'container': image}
        if os.environ.get('PAPER_RUNTIME_IMAGE_URL'):
            manifest['execution']['container_url'] = os.environ['PAPER_RUNTIME_IMAGE_URL']
    (destination / 'generation.json').write_text(json.dumps(manifest, indent=2, allow_nan=False) + '\n')
    print(json.dumps({'stored_observations': len(previous), 'submission_observations': len(latest),
                      'scenario': 'R-generated declared truth', 'destination': str(destination)}))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('source', type=Path)
    parser.add_argument('--output', type=Path, default=Path(__file__).resolve().parents[1] / 'data')
    args = parser.parse_args()
    import_data(args.source, args.output)
