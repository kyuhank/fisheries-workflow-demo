"""Released-source custody and independent unit/scope checks; no model fitting."""
import csv
import copy
from decimal import Decimal
import hashlib
import io
import json
import os
from pathlib import Path
import shutil
import tempfile
import unittest
from unittest.mock import patch
import zipfile

from tests.coordinator_fixtures import CoordinatorBridge
from workflow.engine import ROOT, Workflow, validate_public_projection

PUBLIC_SHA256 = '0503bfb9a7f114fa41bcbd91315cb57fcf02542ffa019429912b03b211aab30e'
REFERENCE_STRATA = ('20S_170E_Q4', '20S_175E_Q1', '20S_175E_Q2',
                    '20S_175E_Q3', '20S_175E_Q4', '25S_175E_Q3')


def sha256(data):
    return hashlib.sha256(data).hexdigest()


@unittest.skipIf(os.environ.get('PAPER_DATA_MODE') == 'synthetic',
                 'Released-source checks run in the explicit public-data gate.')
class PublicSourceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source = json.loads((ROOT / 'data/public-source.json').read_text())
        cls.receipt = json.loads((ROOT / 'data/public-data.json').read_text())

    def test_hosted_metadata_and_source_identity_cannot_drift_with_identical_rows(self):
        supplied = {**copy.deepcopy(self.source), 'source_sha256': PUBLIC_SHA256}
        supplied['sets'] = [row for row in supplied['sets'] if row['year'] <= 2021]
        supplied['catch'] = [row for row in supplied['catch'] if row['year'] <= 2021]
        validate_public_projection(supplied, self.source, 2021, PUBLIC_SHA256)
        altered = copy.deepcopy(supplied)
        altered['metadata']['units']['hooks'] = 'hundreds of hooks'
        with self.assertRaisesRegex(ValueError, 'metadata or identity'):
            validate_public_projection(altered, self.source, 2021, PUBLIC_SHA256)
        altered = copy.deepcopy(supplied)
        altered['source_sha256'] = '0' * 64
        with self.assertRaisesRegex(ValueError, 'metadata or identity'):
            validate_public_projection(altered, self.source, 2021, PUBLIC_SHA256)

    def test_frozen_snapshot_rejects_an_unavailable_endpoint_before_calculation(self):
        supplied = copy.deepcopy(self.source)
        supplied['sets'] = [row for row in supplied['sets'] if row['year'] <= 2021]
        supplied['catch'] = [row for row in supplied['catch'] if row['year'] <= 2021]
        with tempfile.TemporaryDirectory() as directory, patch.dict(os.environ, {'PAPER_DATA_MODE': 'public'}):
            runner = Workflow(directory, r_bridge=CoordinatorBridge(), source_lock=False)
            runner.hosted_data = supplied
            runner.configure({'last_year': 2021})
            with self.assertRaisesRegex(ValueError, 'not available'):
                runner.configure({'last_year': 2022})

    def raw_rows(self, pin):
        with zipfile.ZipFile(ROOT / pin['file']) as archive:
            with archive.open(pin['member']) as member:
                yield from csv.DictReader(io.TextIOWrapper(member, encoding='utf-8-sig'))

    def test_exact_source_projection_units_and_fixed_support(self):
        self.assertEqual(sha256((ROOT / 'data/public-source.json').read_bytes()), PUBLIC_SHA256)
        self.assertEqual(self.receipt['output_sha256'], PUBLIC_SHA256)
        self.assertEqual(self.source['data_kind'], 'public-wcpfc-albacore')
        self.assertIsNone(self.source['submission'])
        self.assertEqual(len(self.source['sets']), 662)
        self.assertEqual(len(self.source['catch']), 23)
        metadata = self.source['metadata']
        self.assertEqual(metadata, self.receipt['metadata'])
        self.assertEqual(metadata['sources'], self.receipt['sources'])
        self.assertEqual(metadata['reference_strata'], list(REFERENCE_STRATA))
        self.assertEqual(metadata['years'], [2000, 2022])
        self.assertEqual(metadata['prediction_effort_hooks'], 1000)
        self.assertEqual(metadata['prediction_weights'], [1 / 6] * 6)
        self.assertEqual(metadata['units']['catch_t'], 'metric tonnes')
        self.assertIn('numbers', metadata['units']['catch_n'])
        self.assertIn('all gears and fleets', metadata['catch_scope'])
        self.assertTrue(any('not a validated stock-wide' in text for text in metadata['limits']))
        rows = self.source['sets']
        self.assertTrue(all(row['fleet'] == 'FJ' and 'vessel' not in row for row in rows))
        self.assertEqual(len({row['set_id'] for row in rows}), 662)
        support = {(row['year'], row['stratum']) for row in rows
                   if row['stratum'] in REFERENCE_STRATA}
        self.assertEqual(support, {(year, stratum) for year in range(2000, 2023)
                                   for stratum in REFERENCE_STRATA})
        self.assertEqual(sum(year <= 2021 for year, _ in support), 132)
        self.assertEqual(len(support), 138)

    def test_original_archive_and_member_bytes_remain_pinned(self):
        for pin in self.receipt['sources']:
            with self.subTest(source=pin['file']):
                self.assertEqual(sha256((ROOT / pin['file']).read_bytes()), pin['sha256'])
                with zipfile.ZipFile(ROOT / pin['file']) as archive:
                    self.assertEqual(sha256(archive.read(pin['member'])), pin['member_sha256'])
        adapter = self.receipt['adapter']
        self.assertEqual(sha256((ROOT / adapter['path']).read_bytes()), adapter['sha256'])

    def test_aggregate_rows_match_original_csv_values_without_vessel_invention(self):
        # Address original row positions, rather than rerunning the import adapter.
        wanted = {row['source_row']: row for row in self.source['sets']}
        observed = set()
        for position, raw in enumerate(self.raw_rows(self.receipt['sources'][0]), 1):
            if position not in wanted:
                continue
            row = wanted[position]
            observed.add(position)
            self.assertEqual(row['set_id'], 'wcpfc_ll_row_' + str(position))
            self.assertEqual(row['year'], int(raw['YY']))
            self.assertEqual(row['fleet'], raw['flag_code'].strip())
            self.assertEqual(row['quarter'], int(raw['QTR']))
            self.assertEqual(row['cell'], raw['LAT5'] + '_' + raw['LON5'])
            self.assertEqual(row['stratum'], row['cell'] + '_Q' + str(int(raw['QTR'])))
            self.assertEqual(Decimal(str(row['hooks'])), Decimal(raw['HHOOKS']) * 100)
            self.assertEqual(Decimal(row['catch_n']), Decimal(raw['ALB_N']))
            self.assertGreater(row['hooks'], 0)
            self.assertGreaterEqual(row['catch_n'], 0)
        self.assertEqual(observed, set(wanted))

    def test_catch_t_is_the_independent_south_pacific_all_gear_total(self):
        years = {row['year'] for row in self.source['catch']}
        sums = dict.fromkeys(years, Decimal(0))
        count = 0
        for raw in self.raw_rows(self.receipt['sources'][1]):
            year = int(raw['YY'])
            if raw['SP_CODE'] == 'ALB' and year in sums:
                sums[year] += Decimal(raw['SP_MT'])
                count += 1
        self.assertEqual(count, 599)
        for row in self.source['catch']:
            self.assertEqual(Decimal(str(row['catch_t'])), sums[row['year']])
            self.assertGreater(row['catch_t'], 0)

    def copied_source(self, folder):
        files = ['data/public-source.json', 'data/public-data.json', self.receipt['adapter']['path']]
        files += [pin['file'] for pin in self.receipt['sources']]
        for name in files:
            target = folder / name
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(ROOT / name, target)

    def test_changed_prepared_data_metadata_adapter_and_raw_archive_fail_closed(self):
        for changed in ('prepared', 'metadata', 'adapter', 'raw'):
            with self.subTest(changed=changed), tempfile.TemporaryDirectory() as directory:
                folder = Path(directory)
                self.copied_source(folder)
                runner = Workflow(folder / 'run', r_bridge=CoordinatorBridge(), source_lock=False)
                if changed == 'prepared':
                    path = folder / 'data/public-source.json'
                    value = json.loads(path.read_text())
                    value['sets'][0]['catch_n'] += 1
                    path.write_text(json.dumps(value))
                elif changed == 'metadata':
                    path = folder / 'data/public-data.json'
                    value = json.loads(path.read_text())
                    value['metadata']['units']['catch_t'] = 'numbers'
                    path.write_text(json.dumps(value))
                else:
                    name = self.receipt['adapter']['path'] if changed == 'adapter' else self.receipt['sources'][0]['file']
                    path = folder / name
                    path.write_bytes(path.read_bytes() + b'changed fixture bytes')
                with patch('workflow.engine.ROOT', folder), patch.dict(os.environ, {'PAPER_DATA_MODE': 'public'}):
                    with self.assertRaises(ValueError):
                        runner.source_context()
                self.assertFalse((folder / 'run/state.json').exists())

    def test_selected_source_mode_and_hosted_values_enter_submission_identity(self):
        with tempfile.TemporaryDirectory() as directory:
            runner = Workflow(directory, r_bridge=CoordinatorBridge(), source_lock=False)
            with patch.dict(os.environ, {'PAPER_DATA_MODE': 'public'}):
                public = runner.signature('submission')
                files = runner.data_files()
                self.assertEqual(files['data/public-source.json'], PUBLIC_SHA256)
                self.assertTrue(all(pin['file'] in files for pin in self.receipt['sources']))
                self.assertNotIn('scenario.json', files)
            with patch.dict(os.environ, {'PAPER_DATA_MODE': 'synthetic'}):
                synthetic = runner.signature('submission')
                self.assertNotEqual(synthetic, public)
                self.assertNotIn('data/public-source.json', runner.data_files())
            with patch.dict(os.environ, {'PAPER_DATA_MODE': 'public'}):
                runner.hosted_data = json.loads(json.dumps(self.source))
                original = runner.signature('submission')
                runner.hosted_data['sets'][0]['catch_n'] += 1
                self.assertNotEqual(runner.signature('submission'), original)

    def test_public_mode_never_silently_uses_synthetic_data_when_snapshot_missing(self):
        with tempfile.TemporaryDirectory() as directory:
            runner = Workflow(directory, r_bridge=CoordinatorBridge(), source_lock=False)
            with patch('workflow.engine.ROOT', Path(directory)), patch.dict(os.environ, {'PAPER_DATA_MODE': 'public'}):
                with self.assertRaisesRegex(ValueError, 'public-data snapshot is missing'):
                    runner.source_context()
