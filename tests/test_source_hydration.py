"""Public source transport and custody checks; no R, Quarto or model execution."""
import copy
import gzip
import hashlib
import http.server
import importlib.util
import io
import json
import os
from pathlib import Path
import tarfile
import tempfile
import threading
import unittest
from unittest.mock import patch

from workflow.sources import GROUPS, SourceResolver

ROOT = Path(__file__).resolve().parents[1]
module_spec = importlib.util.spec_from_file_location('hydrate_sources', ROOT / 'scripts/hydrate-sources.py')
hydrate = importlib.util.module_from_spec(module_spec)
module_spec.loader.exec_module(hydrate)


def archive_bytes(files, prefix='fixture-' + 'a' * 40, extra=()):
    stream = io.BytesIO()
    with tarfile.open(fileobj=stream, mode='w:gz') as archive:
        for name, data in files.items():
            member = tarfile.TarInfo(prefix + '/' + name)
            member.size = len(data)
            archive.addfile(member, io.BytesIO(data))
        for member, data in extra:
            archive.addfile(member, io.BytesIO(data) if data is not None else None)
    return stream.getvalue()


class HydrationTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.base = Path(temporary.name)
        self.files = {'R/fixture.R': b'# software fixture\n', 'jobs/fixture/run.R': b'# inert fixture job\n'}
        self.hashes = {name: hashlib.sha256(data).hexdigest() for name, data in self.files.items()}
        self.prefix = 'fixture-' + 'a' * 40

    def unpack(self, data, files=None):
        archive = self.base / 'source.tar.gz'
        archive.write_bytes(data)
        target = self.base / 'unpacked'
        hydrate.unpack_archive(archive, target, self.prefix, self.hashes if files is None else files)
        return target

    def server(self, status, body, headers=None):
        requests = []

        class Handler(http.server.BaseHTTPRequestHandler):
            def do_GET(self):
                requests.append(dict(self.headers))
                # Behaves like a public endpoint rejecting inherited credentials.
                self.send_response(403 if self.headers.get('Authorization') else status)
                for key, value in (headers or {}).items():
                    self.send_header(key, value)
                self.send_header('Content-Length', str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def log_message(self, *args):
                pass

        server = http.server.ThreadingHTTPServer(('127.0.0.1', 0), Handler)
        thread = threading.Thread(target=server.serve_forever, kwargs={'poll_interval': 0.01}, daemon=True)
        thread.start()
        self.addCleanup(thread.join)
        self.addCleanup(server.server_close)
        self.addCleanup(server.shutdown)
        return 'http://127.0.0.1:' + str(server.server_port), requests

    def test_public_download_ignores_poisoned_git_credentials_and_proxy_environment(self):
        body = archive_bytes(self.files)
        url, requests = self.server(200, body)
        config = self.base / 'poison.gitconfig'
        config.write_text('[http]\n extraHeader = Authorization: fixture-forbidden\n[url "https://invalid.example/"]\n insteadOf = http://127.0.0.1\n')
        netrc = self.base / '.netrc'
        netrc.write_text('machine 127.0.0.1 login fixture password forbidden\n')
        environment = {'GIT_CONFIG_GLOBAL': str(config), 'GIT_CONFIG_COUNT': '1',
                       'GIT_CONFIG_KEY_0': 'http.extraHeader', 'GIT_CONFIG_VALUE_0': 'Authorization: fixture-forbidden',
                       'GIT_ASKPASS': '/does/not/exist', 'NETRC': str(netrc),
                       'http_proxy': 'http://fixture:forbidden@127.0.0.1:1',
                       'https_proxy': 'http://fixture:forbidden@127.0.0.1:1', 'no_proxy': ''}
        destination = self.base / 'download.tar.gz'
        with patch.dict(os.environ, environment), patch.object(hydrate.subprocess, 'run', side_effect=AssertionError('No Git retrieval')):
            hydrate.download_archive(url, destination)
            self.assertEqual({key: os.environ[key] for key in environment}, environment)
        self.assertEqual(destination.read_bytes(), body)
        self.assertEqual(config.read_text().splitlines()[1], ' extraHeader = Authorization: fixture-forbidden')
        self.assertEqual(len(requests), 1)
        self.assertNotIn('Authorization', requests[0])
        self.assertNotIn('Proxy-Authorization', requests[0])

    def test_real_http_error_and_redirect_fail_without_following(self):
        for status in (403, 302):
            with self.subTest(status=status):
                url, requests = self.server(status, b'failure', {'Location': 'http://127.0.0.1:1/forbidden'})
                with self.assertRaisesRegex(ValueError, 'HTTP ' + str(status)):
                    hydrate.download_archive(url, self.base / 'download.tar.gz')
                self.assertEqual(len(requests), 1)

    def test_download_and_decompression_limits(self):
        url, _ = self.server(200, b'x' * 128)
        with patch.object(hydrate, 'MAX_DOWNLOAD_BYTES', 64), self.assertRaisesRegex(ValueError, 'download limit'):
            hydrate.download_archive(url, self.base / 'large.tar.gz')
        with patch.object(hydrate, 'MAX_UNPACKED_BYTES', 64), self.assertRaisesRegex(ValueError, 'unpacked limit'):
            self.unpack(gzip.compress(b'x' * 128))

    def test_exact_inventory_and_source_bytes_are_verified(self):
        target = self.unpack(archive_bytes(self.files))
        self.assertEqual({name: (target / name).read_bytes() for name in self.files}, self.files)
        cases = [(dict(self.files, **{'R/fixture.R': b'altered'}), 'checksum mismatch'),
                 ({'R/fixture.R': self.files['R/fixture.R']}, 'missing expected'),
                 (dict(self.files, **{'extra.R': b'unregistered'}), 'Unregistered')]
        for files, message in cases:
            with self.subTest(message=message), self.assertRaisesRegex(ValueError, message):
                self.unpack(archive_bytes(files))

    def test_wrong_root_duplicate_and_unsafe_archive_entries_fail(self):
        for prefix in ('wrong-repository-' + 'a' * 40, 'fixture-' + 'b' * 40):
            with self.subTest(prefix=prefix), self.assertRaisesRegex(ValueError, 'Wrong component archive root'):
                self.unpack(archive_bytes(self.files, prefix=prefix))
        duplicate = tarfile.TarInfo(self.prefix + '/R/fixture.R')
        duplicate.size = len(self.files['R/fixture.R'])
        with self.assertRaisesRegex(ValueError, 'Duplicate'):
            self.unpack(archive_bytes(self.files, extra=[(duplicate, self.files['R/fixture.R'])]))
        for name in ('../escape', '/absolute', self.prefix + '/../escape', self.prefix + '/R//extra', self.prefix + '/R\\extra', '.'):
            member = tarfile.TarInfo(name)
            with self.subTest(name=name), self.assertRaisesRegex(ValueError, 'Unsafe'):
                self.unpack(archive_bytes(self.files, extra=[(member, b'')]))
        for kind in (tarfile.SYMTYPE, tarfile.LNKTYPE, tarfile.FIFOTYPE):
            member = tarfile.TarInfo(self.prefix + '/link')
            member.type = kind
            member.linkname = self.prefix + '/R/fixture.R'
            with self.subTest(kind=kind), self.assertRaisesRegex(ValueError, 'regular source files'):
                self.unpack(archive_bytes(self.files, extra=[(member, None)]))
        self.assertFalse((self.base / 'escape').exists())

    def test_truncated_and_invalid_archives_fail(self):
        for data in (b'not gzip', archive_bytes(self.files)[:-12], gzip.compress(b'not tar')):
            with self.subTest(size=len(data)), self.assertRaisesRegex(ValueError, 'Invalid component source archive'):
                self.unpack(data)

    def fixture(self):
        lock = json.loads((ROOT / 'source-lock.template.json').read_text())
        expected = {'schema_version': 1, 'repositories': {}}
        archives = {}
        for group, spec in lock['repositories'].items():
            files = {f'jobs/{key}/run.R': b'# inert software fixture\n' for key in GROUPS[group]}
            files['R/' + group + '.R'] = b'# inert software fixture library\n'
            files.update({f'jobs/{key}/report.qmd': b'# inert report fixture\n' for key in GROUPS[group] if key.endswith('_report')})
            checksums = {name: hashlib.sha256(data).hexdigest() for name, data in files.items()}
            expected['repositories'][group] = {'repository': spec['repository'], 'commit': spec['commit'], 'files': checksums}
            name = spec['repository'].rsplit('/', 1)[-1]
            archives['https://codeload.github.com/kyuhank/' + name + '/tar.gz/' + spec['commit']] = archive_bytes(files, name + '-' + spec['commit'])
        manifest = self.base / 'expected.json'
        manifest.write_text(json.dumps(expected))
        return lock, manifest, archives

    def test_snapshot_preserves_pins_origins_and_resolver_checks_without_git(self):
        lock, manifest, archives = self.fixture()
        original = copy.deepcopy(lock)

        def download(url, destination):
            destination.write_bytes(archives[url])

        stage = self.base / 'stage'
        stage.mkdir()
        with patch.object(hydrate, 'MANIFEST', manifest), patch.object(hydrate, 'download_archive', side_effect=download), patch('workflow.sources.git', side_effect=AssertionError('Portable snapshots require no Git')):
            hydrate.public_snapshot(lock, stage)
            path = stage / 'source-lock.json'
            path.write_text(json.dumps(lock))
            resolver = SourceResolver(ROOT, path)
            resolver.verify()
            origins = json.loads((stage / 'source-origins.json').read_text())['sources']
            expected = json.loads(manifest.read_text())['repositories']
            for group, spec in original['repositories'].items():
                self.assertEqual(resolver.repositories[group]['commit'], spec['commit'])
                for name, checksum in expected[group]['files'].items():
                    self.assertEqual(origins['components/' + group + '/' + name], {'repository': spec['repository'], 'commit': spec['commit'], 'path': name, 'sha256': checksum})
            # Both declared-pin and portable-only reuse work without any transport.
            template = self.base / 'template.json'
            template.write_text(json.dumps(original))
            for declared in (template, self.base / 'absent-template.json'):
                with patch.object(hydrate, 'download_archive', side_effect=AssertionError('Offline reuse must not download')), patch('sys.argv', ['hydrate-sources.py', '--if-needed', '--lock', str(declared), '--output', str(stage)]), patch('sys.stdout', new=io.StringIO()):
                    hydrate.main()
            resolver.job_path('cpue_a').write_text('# altered after assembly\n')
            with self.assertRaisesRegex(ValueError, 'Source byte mismatch'):
                resolver.verify()

    def test_resolver_still_rejects_manifest_omitting_a_required_job(self):
        lock, manifest, archives = self.fixture()
        expected = json.loads(manifest.read_text())
        del expected['repositories']['cpue']['files']['jobs/cpue_a/run.R']
        manifest.write_text(json.dumps(expected))
        url = next(url for url in archives if 'cpue-demo' in url)
        with tarfile.open(fileobj=io.BytesIO(archives[url]), mode='r:gz') as archive:
            files = {member.name.split('/', 1)[1]: archive.extractfile(member).read() for member in archive if '/jobs/cpue_a/run.R' not in member.name}
        spec = lock['repositories']['cpue']
        archives[url] = archive_bytes(files, spec['repository'].rsplit('/', 1)[-1] + '-' + spec['commit'])
        stage = self.base / 'stage'
        stage.mkdir()
        with patch.object(hydrate, 'MANIFEST', manifest), patch.object(hydrate, 'download_archive', side_effect=lambda url, path: path.write_bytes(archives[url])):
            hydrate.public_snapshot(lock, stage)
        path = stage / 'source-lock.json'
        path.write_text(json.dumps(lock))
        with self.assertRaisesRegex(ValueError, 'Missing required component source: cpue'):
            SourceResolver(ROOT, path)

    def test_wrong_expected_pin_and_duplicate_manifest_fields_fail_before_download(self):
        for field, value in (('commit', '0' * 40), ('repository', 'https://example.invalid/source')):
            lock, manifest, _ = self.fixture()
            expected = json.loads(manifest.read_text())
            expected['repositories']['cpue'][field] = value
            manifest.write_text(json.dumps(expected))
            with self.subTest(field=field), patch.object(hydrate, 'MANIFEST', manifest), patch.object(hydrate, 'download_archive', side_effect=AssertionError('Must reject before network')):
                with self.assertRaisesRegex(ValueError, 'does not match registered pin'):
                    hydrate.public_snapshot(lock, self.base)
        manifest.write_text('{"schema_version":1,"schema_version":1,"repositories":{}}')
        with patch.object(hydrate, 'MANIFEST', manifest), self.assertRaisesRegex(ValueError, 'Duplicate'):
            hydrate.registered_files(lock)


if __name__ == '__main__':
    unittest.main()
