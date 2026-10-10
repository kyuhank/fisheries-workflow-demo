"""Authored offline guard tests; no Docker, R or numerical model execution."""
import argparse
import base64
import copy
import hashlib
import io
import importlib.util
import json
import os
from pathlib import Path
import re
import shlex
import shutil
import subprocess
import tarfile
import tempfile
import unittest
from unittest.mock import patch
import zipfile

from workflow import offline

ROOT = Path(__file__).resolve().parents[1]


def inspect_image():
    return {'Id': offline.IMAGE_ID, 'Os': 'linux', 'Architecture': 'amd64',
            'RootFS': {'Type': 'layers', 'Layers': list(offline.DIFF_IDS)},
            'RepoDigests': [offline.UPSTREAM_IMAGE]}


class RuntimeIdentityTest(unittest.TestCase):
    def test_loaded_image_without_registry_reference_is_honestly_verified(self):
        image = inspect_image()
        image['RepoDigests'] = []
        result = offline.verify_image(image)
        self.assertEqual(result['launch_reference'], offline.IMAGE_ID)
        self.assertFalse(result['registry_digest_verified_locally'])
        self.assertEqual(result['upstream_registry_digest'], offline.UPSTREAM_IMAGE)

    def test_wrong_config_platform_layer_order_and_metadata_are_rejected(self):
        variants = []
        for field, value in [('Id', 'sha256:' + '0' * 64), ('Architecture', 'arm64'), ('Os', 'windows')]:
            image = inspect_image(); image[field] = value; variants.append(image)
        image = inspect_image(); image['RootFS']['Layers'].reverse(); variants.append(image)
        for value in variants:
            with self.subTest(value=value), self.assertRaises(ValueError):
                offline.verify_image(value)
        metadata = offline.runtime_metadata(); metadata['config_id'] = 'different'
        with self.assertRaises(ValueError):
            offline.verify_image(inspect_image(), metadata)


class PreservedSourceTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        page = ROOT / 'docs/offline.html'
        if not page.is_file():
            raise unittest.SkipTest('This test requires the preserved Saved page; no source hydration or numerical run is attempted')
        match = re.search(r'<script id="demo-payload" type="application/json">(.*?)</script>', page.read_text(), re.S)
        cls.bundle = base64.b64decode(json.loads(match[1])['saved']['bundle'])

    def setUp(self):
        temporary = tempfile.TemporaryDirectory(); self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        with zipfile.ZipFile(io.BytesIO(self.bundle)) as archive:
            archive.extractall(self.root)
        self.old_origin = (self.root / 'coordinator-origin.json').read_bytes()
        for name in ('workflow/offline.py', 'scripts/offline-runtime.py', 'scripts/offline.sh', 'scripts/preserve-runtime.sh', 'runtime-preservation.json'):
            target = self.root / name; target.parent.mkdir(exist_ok=True, parents=True)
            shutil.copyfile(ROOT / name, target)
        self.manifest = offline.read_json(self.root / 'SHA256SUMS.json')
        for name in ('workflow/offline.py', 'scripts/offline-runtime.py', 'scripts/offline.sh', 'scripts/preserve-runtime.sh', 'runtime-preservation.json'):
            self.manifest[name] = offline.sha((self.root / name).read_bytes())
        self.write_manifest()

    def write_manifest(self):
        (self.root / 'SHA256SUMS.json').write_text(json.dumps(self.manifest))

    def test_new_support_manifest_accepts_exact_old_origin_without_git(self):
        with patch('workflow.sources.git', side_effect=AssertionError('Offline must not invoke Git')):
            result = offline.verify_sources(self.root)
        self.assertRegex(result['coordinator_origin']['commit'], r'^[0-9a-f]{40}$')
        self.assertEqual((self.root / 'coordinator-origin.json').read_bytes(), self.old_origin)
        self.assertEqual(set(result['component_origins']), {'cpue', 'assessment', 'mse'})

    def test_source_or_stock_input_tamper_fails_before_workflow_construction(self):
        for name in ('workflow/engine.py', 'components/mse/R/mse.R', 'data/source-data.json'):
            path = self.root / name; original = path.read_bytes(); path.write_bytes(original + b'\n')
            args = argparse.Namespace(command='run', job=None, reference=None, settings=None, output=self.root / 'outputs')
            with patch('workflow.engine.Workflow') as calculator, self.assertRaisesRegex(ValueError, 'byte mismatch'):
                offline.run_offline(self.root, args, inspect_image())
            calculator.assert_not_called(); path.write_bytes(original)

    def test_manifest_missing_imported_file_and_traversal_and_symlinks_rejected(self):
        del self.manifest['workflow/contracts.py']; self.write_manifest()
        with self.assertRaisesRegex(ValueError, 'missing required'):
            offline.verify_manifest(self.root)
        self.manifest['workflow/contracts.py'] = offline.sha((self.root / 'workflow/contracts.py').read_bytes())
        self.manifest['../escape'] = '0' * 64; self.write_manifest()
        with self.assertRaisesRegex(ValueError, 'Unsafe'):
            offline.verify_manifest(self.root)
        del self.manifest['../escape']; self.write_manifest()
        (self.root / 'run.py').unlink(); (self.root / 'run.py').symlink_to(ROOT / 'run.py')
        with self.assertRaisesRegex(ValueError, 'Symlink'):
            offline.verify_manifest(self.root)

    def test_reference_settings_and_selected_job_scope_are_preserved(self):
        state = offline.read_json(self.root / 'reference/state.json')
        settings, selected = offline.reference_scope(self.root, 'reference')
        self.assertEqual(settings, offline.read_json(self.root / 'settings.json'))
        self.assertEqual(selected, state['last_plan']['start'] if state['last_plan']['scope'] == 'job' else None)
        self.assertEqual(offline.reference_scope(self.root, 'reference', 'cpue_a')[1], 'cpue_a')
        with self.assertRaises(ValueError):
            offline.reference_scope(self.root, '../reference')

    def test_comparison_receipt_preserves_pass_and_failure_from_comparator(self):
        output = self.root / 'comparison'; output.mkdir()
        args = argparse.Namespace(command='compare', job=None, reference=None, settings=None, output=output)
        with patch('verify.verify', return_value=22) as compare:
            result = offline.run_offline(self.root, args, inspect_image())
        self.assertEqual(result['outputs_compared'], 22)
        compare.assert_called_once_with(self.root / 'reference', output, None)
        self.assertEqual(offline.read_json(output / 'offline-comparison.json')['status'], 'PASSED')
        with patch('verify.verify', side_effect=AssertionError('explicit comparator fixture rejection')):
            with self.assertRaises(AssertionError):
                offline.run_offline(self.root, args, inspect_image())
        self.assertEqual(offline.read_json(output / 'offline-comparison.json')['status'], 'FAILED')

    def test_frozen_renderer_has_no_GitHub_execution_claim_for_local_records(self):
        # Execute the actual immutable Saved report renderer on an already saved
        # output; this does not run or alter any scientific model.
        spec = importlib.util.spec_from_file_location('frozen_saved_reports', self.root / 'workflow/reports.py')
        reports = importlib.util.module_from_spec(spec); spec.loader.exec_module(reports)
        jobs = offline.read_json(self.root / 'workflow/jobs.json')['jobs']
        job = next(value for value in jobs if value['key'] == 'submission')
        record = copy.deepcopy(offline.read_json(self.root / 'reference/state.json')['records']['submission'])
        result = offline.read_json(self.root / 'reference/submission/output.json')
        record['execution'] = {'provider': 'Local Docker', 'purpose': 'explicit regression fixture'}
        with self.assertRaises(KeyError):
            reports.output_page(job, result, record, [])
        record.pop('execution')
        record['software'].update(container_config_id=offline.IMAGE_ID,
                                  container_rootfs_diff_ids=list(offline.DIFF_IDS),
                                  container_reference_kind='upstream registry source pin')
        page = reports.output_page(job, result, record, [])
        self.assertNotIn('Executed on GitHub Actions', page)
        self.assertIn(offline.IMAGE_ID, page)

    def test_helper_keeps_local_execution_default_and_binds_external_receipt(self):
        # Explicit orchestration double: no R backend or numerical calculation.
        output = self.root / 'local-fixture'
        seen = {}
        class PresentationFixture:
            def __init__(self, directory, **kwargs):
                self.execution = {}; seen['runner'] = self
            def configure(self, settings):
                seen['settings'] = settings
            async def run(self, start, scope):
                seen['execution_at_run'] = self.execution
                (output / 'state.json').write_text('{"explicit_test_double":true}')
                return {'run': ['submission'], 'retained': [], 'run_id': 'EXPLICIT PRESENTATION TEST DOUBLE'}
        args = argparse.Namespace(command='run', job=None, reference=None, settings=None, output=output)
        with patch('workflow.engine.Workflow', PresentationFixture):
            result = offline.run_offline(self.root, args, inspect_image())
        self.assertEqual(seen['execution_at_run'], {})
        self.assertEqual(result['provider'], 'Local Docker')
        self.assertEqual(result['purpose'], 'offline run')
        self.assertEqual(result['analysis_run_id'], 'EXPLICIT PRESENTATION TEST DOUBLE')
        self.assertEqual(result['state_sha256'], offline.hash_file(output / 'state.json'))
        self.assertEqual(result['jobs_executed'], ['submission'])
        self.assertEqual(offline.read_json(output / 'offline-execution.json'), result)


class RuntimeArchiveTest(unittest.TestCase):
    def setUp(self):
        self.layers = [b'layer one', b'layer two']
        self.diff_ids = tuple('sha256:' + offline.sha(value) for value in self.layers)
        self.config = json.dumps({'os': 'linux', 'architecture': 'amd64', 'rootfs': {'type': 'layers', 'diff_ids': list(self.diff_ids)}}).encode()
        self.config_id = 'sha256:' + offline.sha(self.config)
        self.addCleanup(patch.stopall)
        patch.object(offline, 'DIFF_IDS', self.diff_ids).start()
        patch.object(offline, 'IMAGE_ID', self.config_id).start()
        temporary = tempfile.TemporaryDirectory(); self.addCleanup(temporary.cleanup); self.root = Path(temporary.name)

    def tar_stream(self, reverse=False):
        output = io.BytesIO()
        files = {'config.json': self.config, 'one/layer.tar': self.layers[0], 'two/layer.tar': self.layers[1]}
        layers = ['one/layer.tar', 'two/layer.tar']
        if reverse: layers.reverse()
        files['manifest.json'] = json.dumps([{'Config': 'config.json', 'RepoTags': None, 'Layers': layers}]).encode()
        with tarfile.open(fileobj=output, mode='w') as archive:
            for name, value in files.items():
                member = tarfile.TarInfo(name); member.size = len(value); archive.addfile(member, io.BytesIO(value))
        output.seek(0); return output

    def test_save_verify_and_restored_config_without_repo_digest(self):
        receipt = offline.archive_save(self.root, inspect_image(), self.tar_stream())
        self.assertTrue(receipt['saved_layer_bytes_verified'])
        restored = inspect_image(); restored['RepoDigests'] = []
        checked = offline.archive_verify(self.root, restored)
        self.assertEqual(checked['status'], 'ARCHIVE_AND_LOCAL_IMAGE_VERIFIED')
        self.assertFalse(checked['runtime']['registry_digest_verified_locally'])
        with self.assertRaises(ValueError):
            offline.archive_save(self.root, inspect_image(), self.tar_stream())

    def test_bad_stream_reordered_layers_and_modified_archive_are_rejected(self):
        with self.assertRaises((ValueError, tarfile.TarError)):
            offline.archive_save(self.root, inspect_image(), io.BytesIO(b''))
        (self.root / (offline.ARCHIVE_NAME + '.partial')).unlink()
        with self.assertRaisesRegex(ValueError, 'ordered layer'):
            offline.archive_save(self.root, inspect_image(), self.tar_stream(reverse=True))
        (self.root / (offline.ARCHIVE_NAME + '.partial')).unlink()
        offline.archive_save(self.root, inspect_image(), self.tar_stream())
        with (self.root / offline.ARCHIVE_NAME).open('ab') as stream: stream.write(b'tampered')
        with self.assertRaisesRegex(ValueError, 'checksum mismatch'):
            offline.archive_verify(self.root, inspect_image())


class ShellEntryTest(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(); self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name); self.bin = self.root / 'bin'; self.bin.mkdir()
        self.log = self.root / 'docker-arguments.txt'
        script = '#!/bin/sh\nif [ "$1 $2" = "image inspect" ]; then\n [ "${FAKE_MISSING:-0}" = 0 ] || exit 1\n printf "%s\\n" ' + shlex.quote(json.dumps(inspect_image())) + '\nelse\n printf "%s\\n" "$@" >> "$DOCKER_TEST_LOG"\nfi\n'
        (self.bin / 'docker').write_text(script); (self.bin / 'docker').chmod(0o755)
        # Only Docker is on PATH: no host Python, Make, Git, id, mkdir or gzip.
        self.env = {'PATH': str(self.bin), 'DOCKER_TEST_LOG': str(self.log), 'PAPER_OFFLINE_OUTPUT': str(self.root / 'result')}

    def test_shell_launch_has_config_id_no_pull_no_network_and_readonly_sources(self):
        result = subprocess.run(['/bin/sh', str(ROOT / 'scripts/offline.sh'), 'job', 'cpue_a'], env=self.env, capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        args = self.log.read_text().splitlines()
        self.assertIn('never', args); self.assertIn('none', args); self.assertIn(offline.IMAGE_ID, args)
        self.assertIn(str(ROOT) + ':/workspace:ro', args)
        self.assertEqual(args[-4:], ['python3', 'scripts/offline-runtime.py', 'job', 'cpue_a'])
        self.assertNotIn('pull', args); self.assertNotIn('https://github.com', args)

    def test_inspect_templates_render_complete_JSON_objects(self):
        # Exercise each actual template's enclosing JSON, which the command double
        # alone does not check. Docker itself is checked separately on the real cache.
        values = inspect_image()
        for name in ('offline.sh', 'preserve-runtime.sh'):
            with self.subTest(script=name):
                template = re.search(r"--format '([^']+)'", (ROOT / 'scripts' / name).read_text())[1]
                rendered = re.sub(r'\{\{json \.(\w+)\}\}', lambda match: json.dumps(values[match[1]]), template)
                self.assertEqual(json.loads(rendered), values)

    def test_missing_image_is_helpful_and_never_attempts_run_or_pull(self):
        self.env['FAKE_MISSING'] = '1'
        result = subprocess.run(['/bin/sh', str(ROOT / 'scripts/offline.sh'), 'run'], env=self.env, capture_output=True, text=True)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('never pulls', result.stderr)
        self.assertFalse(self.log.exists())

    def test_load_uses_local_archive_before_verified_runtime_entry(self):
        result = subprocess.run(['/bin/sh', str(ROOT / 'scripts/preserve-runtime.sh'), 'load', str(self.root)], env=self.env, capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        args = self.log.read_text().splitlines()
        self.assertEqual(args[:3], ['image', 'load', '--input'])
        self.assertEqual(args[-3:], ['python3', 'scripts/offline-runtime.py', 'archive-verify'])
        self.assertIn('checks follow before analysis', result.stderr)


if __name__ == '__main__':
    unittest.main()
