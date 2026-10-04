"""Fixture adapter custody using explicit JSON test data; no fishery simulation."""
import hashlib
import importlib.util
import io
import json
import os
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('fixture_import', ROOT / 'scripts/import-r-data.py')
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


def fixture():
    return {'sets': [{'set_id': str(year), 'year': year, 'vessel': 'TEST',
                      'hooks': 1000, 'catch_n': 1} for year in range(2000, 2025)],
            'catch': [{'year': year, 'catch_t': 1} for year in range(2000, 2025)],
            'scenario': {'type': 'synthetic-schaefer-poisson', 'R': 'TEST DOUBLE',
                         'seed': 1, 'rng': ['TEST DOUBLE']}}


class DataImportTests(unittest.TestCase):
    def test_exact_fixture_bytes_truth_and_storage_split_are_preserved(self):
        with tempfile.TemporaryDirectory() as directory, patch.dict(os.environ, {}, clear=True), \
             patch('sys.stdout', new_callable=io.StringIO):
            root = Path(directory)
            source = root / 'fixture.json'
            source.write_text(json.dumps(fixture(), indent=2))
            destination = root / 'data'
            module.import_data(source, destination)
            self.assertEqual((destination / 'source-data.json').read_bytes(), source.read_bytes())
            self.assertEqual(json.loads((destination / 'scenario.json').read_text()), fixture()['scenario'])
            with sqlite3.connect(destination / 'fishery.sqlite') as db:
                self.assertEqual(db.execute('select count(*), max(year) from sets').fetchone(), (24, 2023))
                self.assertEqual(db.execute('select count(*) from removals').fetchone(), (24,))
            submission = json.loads((destination / 'submission.json').read_text())
            self.assertEqual(submission, {'sets': [['2024', 2024, 'TEST', 1000, 1]], 'catch': 1})
            manifest = json.loads((destination / 'generation.json').read_text())
            self.assertNotIn('execution', manifest)
            for name, checksum in manifest['outputs'].items():
                self.assertEqual(hashlib.sha256((destination / name).read_bytes()).hexdigest(), checksum)
            self.assertEqual(manifest['generator']['sha256'],
                             hashlib.sha256((ROOT / 'scripts/generate-data.R').read_bytes()).hexdigest())

    def test_invalid_or_legacy_source_cannot_replace_existing_data(self):
        for mutation in ('legacy', 'nan', 'missing-year'):
            with self.subTest(mutation=mutation), tempfile.TemporaryDirectory() as directory, \
                 patch.dict(os.environ, {}, clear=True):
                data = fixture()
                if mutation == 'legacy': data['scenario']['type'] = 'age-model'
                if mutation == 'nan': data['sets'][0]['hooks'] = float('nan')
                if mutation == 'missing-year': data['catch'].pop()
                root = Path(directory)
                source = root / 'fixture.json'
                source.write_text(json.dumps(data))
                destination = root / 'data'
                destination.mkdir()
                old = destination / 'fishery.sqlite'
                old.write_bytes(b'preserved previous bytes')
                with self.assertRaises(ValueError): module.import_data(source, destination)
                self.assertEqual(old.read_bytes(), b'preserved previous bytes')

    def test_incomplete_claimed_CI_identity_is_rejected_before_mutation(self):
        with tempfile.TemporaryDirectory() as directory, \
             patch.dict(os.environ, {'PAPER_RUNTIME_IMAGE': 'repo@sha256:' + 'a' * 64}, clear=True):
            root = Path(directory)
            source = root / 'fixture.json'
            source.write_text(json.dumps(fixture()))
            with self.assertRaisesRegex(ValueError, 'complete actual CI source and image identity'):
                module.import_data(source, root / 'data')
            self.assertFalse((root / 'data').exists())
