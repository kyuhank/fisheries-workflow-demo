"""Create a fixed synthetic fishery with changing catches and vessel composition."""
import json
import math
from pathlib import Path
import random
import sqlite3
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from workflow.age_model import trajectory

SEED = 20260913
random_source = random.Random(SEED)
YEARS = list(range(2000, 2025))
KNOTS = [(2000,300), (2005,650), (2010,1000), (2015,1000), (2019,650), (2024,380)]
VESSELS = [f'v{i+1:02d}' for i in range(8)]
CATCHABILITY = [0.65, 0.78, 0.87, 0.99, 1.10, 1.23, 1.39, 1.58]


def poisson(mean):
    threshold = math.exp(-mean)
    product, count = 1.0, 0
    while product > threshold:
        product *= random_source.random()
        count += 1
    return count - 1


def annual_catch(year):
    for (left, start), (right, end) in zip(KNOTS, KNOTS[1:]):
        if left <= year <= right:
            expected = start + (end-start) * (year-left) / (right-left)
            return round(expected * (1 + 0.035*math.sin((year-2000)*1.1)), 2)


def generate():
    catches = [annual_catch(year) for year in YEARS]
    population = trajectory(14000, 0.20, catches)
    initial = population['rows'][0]['vulnerable_biomass']
    observations, deviation = [], 0.0
    for t, (year, row) in enumerate(zip(YEARS, population['rows'])):
        deviation = 0.45 * deviation + random_source.gauss(0, 0.035)
        fraction = t / (len(YEARS)-1)
        weights = [(1-fraction)*(8-i) + fraction*(i+1) for i in range(8)]
        count = round(250 + 3*t + 14*math.sin(t/3))
        for i in range(count):
            vessel = random_source.choices(range(8), weights=weights)[0]
            hooks = random_source.choice([800, 1200, 1600, 2000, 2400])
            mean = 5 * hooks/1000 * row['vulnerable_biomass']/initial * CATCHABILITY[vessel]
            mean *= math.exp(deviation) * random_source.gammavariate(5, 0.2)
            observations.append([f'{year}-{i:04d}', year, VESSELS[vessel], hooks, poisson(mean)])
    path = ROOT/'data/fishery.sqlite'
    path.unlink(missing_ok=True)
    with sqlite3.connect(path) as db:
        db.execute('CREATE TABLE sets(set_id TEXT PRIMARY KEY,year INTEGER,vessel TEXT,hooks INTEGER CHECK(hooks>0),catch_n INTEGER CHECK(catch_n>=0))')
        db.execute('CREATE TABLE removals(year INTEGER PRIMARY KEY,catch_t REAL CHECK(catch_t>=0))')
        db.executemany('INSERT INTO sets VALUES(?,?,?,?,?)', [r for r in observations if r[1] <= 2023])
        db.executemany('INSERT INTO removals VALUES(?,?)', list(zip(YEARS[:-1], catches[:-1])))
    (ROOT/'data/submission.json').write_text(json.dumps({'sets':[r for r in observations if r[1] == 2024], 'catch':catches[-1]},separators=(',',':'))+'\n')
    scenario = {'seed':SEED, 'generator':'scripts/generate-data.py',
                'purpose':'Illustrate a connected workflow, not infer stock status.',
                'scenario':'Catches increase, then ease; biomass declines and partially recovers. The sample shifts towards vessels with higher catchability.',
                'years':YEARS, 'catch_knots':KNOTS, 'vessel_catchability':CATCHABILITY,
                'generating_B0':14000, 'generating_M':0.20,
                'observation_model':'Poisson catch with gamma variation, vessel effects and a small correlated annual deviation.'}
    (ROOT/'data/scenario.json').write_text(json.dumps(scenario,indent=2)+'\n')
    print(f'Generated {len(observations)} observations for 2000–2024; seed {SEED}.')


if __name__ == '__main__':
    generate()
