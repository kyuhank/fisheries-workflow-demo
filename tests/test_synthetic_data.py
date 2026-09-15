"""Check the recorded synthetic scenario and its supported assessment inputs."""
import contextlib
import hashlib
import io
import json
import math
from pathlib import Path
import runpy
import sqlite3
import tempfile
import unittest

from workflow import age_model, models

ROOT = Path(__file__).resolve().parents[1]


def read_inputs(root):
    with sqlite3.connect(f'file:{root / "data/fishery.sqlite"}?mode=ro', uri=True) as db:
        db.row_factory = sqlite3.Row
        records = [dict(row) for row in db.execute('SELECT * FROM sets ORDER BY year,set_id')]
        catches = [dict(row) for row in db.execute('SELECT * FROM removals ORDER BY year')]
    submission = json.loads((root / 'data/submission.json').read_text())
    records += [dict(zip(['set_id', 'year', 'vessel', 'hooks', 'catch_n'], row))
                for row in submission['sets']]
    catches.append({'year': 2024, 'catch_t': submission['catch']})
    return records, catches


class SyntheticDataTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.records, cls.catches = read_inputs(ROOT)
        cls.scenario = json.loads((ROOT / 'data/scenario.json').read_text())

    def test_source_hashes_describe_the_supplied_data(self):
        sources = json.loads((ROOT / 'data/sources.json').read_text())
        for source in sources:
            if source.get('generator') == self.scenario['generator']:
                self.assertEqual(source['seed'], self.scenario['seed'])
                self.assertEqual(source['sha256'],
                                 hashlib.sha256((ROOT / source['file']).read_bytes()).hexdigest())

    def test_catch_reduction_precedes_a_feasible_biomass_recovery(self):
        catches = [row['catch_t'] for row in self.catches]
        self.assertEqual([row['year'] for row in self.catches], self.scenario['years'])
        population = age_model.trajectory(self.scenario['generating_B0'],
                                          self.scenario['generating_M'], catches)
        self.assertIsNotNone(population)
        rows = population['rows']
        peak = max(range(len(catches)), key=lambda i: catches[i])
        low = min(range(len(rows)), key=lambda i: rows[i]['SB_over_SB0'])
        self.assertLess(peak, low)
        self.assertLess(low, len(rows) - 1)
        self.assertLess(catches[-1], catches[peak])
        self.assertLess(rows[low]['SB_over_SB0'], rows[-1]['SB_over_SB0'])
        self.assertLess(rows[-1]['SB_over_SB0'], rows[0]['SB_over_SB0'])
        for catch, row in zip(catches, rows):
            self.assertTrue(all(math.isfinite(n) and n >= 0 for n in row['numbers']))
            realised = row['vulnerable_biomass'] * age_model.catch_fraction(
                row['F'], self.scenario['generating_M'])
            self.assertAlmostEqual(realised, catch, delta=max(1, catch) * 1e-8)

    def test_all_supported_snapshots_filters_and_mortalities_fit(self):
        for last_year in (2021, 2022, 2023, 2024):
            records = [row for row in self.records if row['year'] <= last_year]
            catches = {row['year']: row['catch_t'] for row in self.catches}
            for vessel_effect, min_hooks in ((True, 0), (True, 1200), (False, 0)):
                index = models.cpue(records, vessel_effect, min_hooks)
                self.assertLess(index['score_residual'], 1e-9)
                inputs = [{**row, 'catch_t': catches[row['year']]} for row in index['series']]
                for mortality in (.20, .25, .30, .35):
                    with self.subTest(year=last_year, vessel=vessel_effect,
                                      hooks=min_hooks, mortality=mortality):
                        fitted = models.assessment(inputs, mortality)
                        self.assertFalse(fitted['boundary_fit'])
                        self.assertEqual(fitted['catch_check'], 'Pass')
                        for row in fitted['series']:
                            for field in ('fitted_index', 'SB_over_SB0', 'F', 'biomass_t'):
                                self.assertTrue(math.isfinite(row[field]) and row[field] > 0)

    @unittest.skipUnless((ROOT / 'scripts/generate-data.py').is_file(),
                         'Generation script is available in the source release.')
    def test_repeated_generation_preserves_inputs_and_provenance(self):
        generate = runpy.run_path(str(ROOT / 'scripts/generate-data.py'))['generate']
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / 'data').mkdir()
            (root / 'data/sources.json').write_bytes((ROOT / 'data/sources.json').read_bytes())
            generate.__globals__['ROOT'] = root
            snapshots = []
            for _ in range(2):
                with contextlib.redirect_stdout(io.StringIO()):
                    generate()
                snapshots.append({p.name: p.read_bytes() for p in (root / 'data').iterdir()})
            self.assertEqual(snapshots[0], snapshots[1])
            self.assertEqual(read_inputs(root), (self.records, self.catches))
            self.assertEqual(json.loads((root / 'data/scenario.json').read_text()), self.scenario)
            for source in json.loads((root / 'data/sources.json').read_text()):
                if source.get('generator') == self.scenario['generator']:
                    self.assertEqual(source['sha256'],
                                     hashlib.sha256((root / source['file']).read_bytes()).hexdigest())


if __name__ == '__main__':
    unittest.main()
