"""Verify registered source pins, then assemble exact offline snapshots."""
import argparse
import gzip
import hashlib
import http.client
import io
import json
from pathlib import Path, PurePosixPath
import re
import shutil
import subprocess
import sys
import tarfile
import tempfile
import time
import urllib.error
import urllib.request

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from workflow.sources import SourceResolver, contained, git, GROUPS, unique

MANIFEST = ROOT / 'source-files.sha256.json'
MAX_DOWNLOAD_BYTES = 4 * 1024 * 1024
MAX_UNPACKED_BYTES = 8 * 1024 * 1024
MAX_MEMBERS = 2048


def safe_name(name):
    path = PurePosixPath(name)
    if not path.parts or path.is_absolute() or '..' in path.parts or str(path) != name or '\\' in name or '\0' in name:
        raise ValueError('Unsafe component source path')
    return path


def registered_files(lock):
    # Independent pins from previously verified Git objects, never downloaded bytes.
    manifest = json.loads(MANIFEST.read_text(), object_pairs_hook=unique)
    if set(manifest) != {'schema_version', 'repositories'} or type(manifest['schema_version']) is not int or manifest['schema_version'] != 1 or set(manifest['repositories']) != set(GROUPS):
        raise ValueError('Invalid expected component source manifest')
    for group, spec in lock['repositories'].items():
        expected = manifest['repositories'][group]
        if set(expected) != {'repository', 'commit', 'files'} or expected['repository'] != spec['repository'] or expected['commit'] != spec['commit']:
            raise ValueError('Expected source manifest does not match registered pin: ' + group)
        if not isinstance(expected['files'], dict) or not expected['files']:
            raise ValueError('Missing expected component files: ' + group)
        for name, checksum in expected['files'].items():
            safe_name(name)
            if not isinstance(checksum, str) or not re.fullmatch(r'[a-f0-9]{64}', checksum):
                raise ValueError('Invalid expected component checksum: ' + group)
    return manifest['repositories']


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, request, response, code, message, headers, new_url):
        return None


def download_archive(url, destination):
    # No Git config/helpers, netrc/auth handlers, environment proxies or redirects.
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), NoRedirect())
    request = urllib.request.Request(url, headers={'User-Agent': 'fisheries-source-hydration/1', 'Accept': 'application/gzip'})
    deadline = time.monotonic() + 30
    try:
        with opener.open(request, timeout=10) as response, destination.open('wb') as target:
            if response.status != 200:
                raise ValueError('Public source archive returned HTTP ' + str(response.status))
            total = 0
            while True:
                if time.monotonic() > deadline:
                    raise ValueError('Public source archive download exceeded 30 seconds')
                chunk = response.read1(65536)
                if not chunk:
                    break
                total += len(chunk)
                if total > MAX_DOWNLOAD_BYTES:
                    raise ValueError('Public source archive exceeds download limit')
                target.write(chunk)
    except (urllib.error.URLError, OSError, http.client.HTTPException) as error:
        status = getattr(error, 'code', None)
        raise ValueError('Public source archive download failed' + (' (HTTP ' + str(status) + ')' if status else ': ' + type(error).__name__)) from None


def unpack_archive(archive, target, prefix, files):
    try:
        with gzip.open(archive, 'rb') as compressed:
            data = compressed.read(MAX_UNPACKED_BYTES + 1)
        if len(data) > MAX_UNPACKED_BYTES:
            raise ValueError('Component archive exceeds unpacked limit')
        seen, found = set(), set()
        with tarfile.open(fileobj=io.BytesIO(data), mode='r:') as contents:
            for index, member in enumerate(contents):
                if index >= MAX_MEMBERS:
                    raise ValueError('Component archive has too many entries')
                name = member.name.removesuffix('/') if member.isdir() else member.name
                path = safe_name(name)
                if path.parts[0] != prefix:
                    raise ValueError('Wrong component archive root')
                if name in seen:
                    raise ValueError('Duplicate component archive entry')
                seen.add(name)
                if member.isdir():
                    continue
                if not member.isfile() or len(path.parts) < 2:
                    raise ValueError('Component archive requires regular source files')
                relative = '/'.join(path.parts[1:])
                if relative not in files:
                    raise ValueError('Unregistered component archive file')
                if member.size < 0 or member.size > MAX_UNPACKED_BYTES:
                    raise ValueError('Component archive file exceeds unpacked limit')
                content = contents.extractfile(member).read(MAX_UNPACKED_BYTES + 1)
                if hashlib.sha256(content).hexdigest() != files[relative]:
                    raise ValueError('Component archive source checksum mismatch: ' + relative)
                found.add(relative)
                destination = contained(target, relative)
                destination.parent.mkdir(parents=True, exist_ok=True)
                destination.write_bytes(content)
        if set(files) != found:
            raise ValueError('Component archive is missing expected source files')
    except (OSError, EOFError, tarfile.TarError) as error:
        raise ValueError('Invalid component source archive: ' + type(error).__name__) from None


def public_snapshot(lock, stage):
    expected = registered_files(lock)
    origins = {}
    for group, spec in lock['repositories'].items():
        name = spec['repository'].rsplit('/', 1)[-1]
        archive = stage / (group + '.tar.gz')
        download_archive('https://codeload.github.com/kyuhank/' + name + '/tar.gz/' + spec['commit'], archive)
        target = stage / 'components' / group
        target.mkdir(parents=True)
        unpack_archive(archive, target, name + '-' + spec['commit'], expected[group]['files'])
        spec['checkout'] = 'components/' + group
        for path, checksum in expected[group]['files'].items():
            origins['components/' + group + '/' + path] = {'repository': spec['repository'], 'commit': spec['commit'], 'path': path, 'sha256': checksum}
    lock['snapshot_manifest'] = 'source-origins.json'
    (stage / 'source-origins.json').write_text(json.dumps({'schema_version': 1, 'sources': origins}, indent=2) + '\n')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--lock', type=Path, default=ROOT / 'source-lock.template.json')
    parser.add_argument('--local-root', type=Path, help='Use existing registered component Git repositories instead of network retrieval.')
    parser.add_argument('--output', type=Path, default=ROOT)
    parser.add_argument('--coordinator-commit', help='Actual committed coordinator revision; defaults to checked-out HEAD.')
    parser.add_argument('--if-needed', action='store_true', help='Reuse a verified assembly with exactly the declared component pins.')
    args = parser.parse_args()
    if args.if_needed and not args.lock.is_file() and (args.output / 'source-lock.json').is_file():
        ready = SourceResolver(args.output, args.output / 'source-lock.json')
        ready.verify(); ready.coordinator_identity()
        print('Portable pinned source snapshot verified')
        return
    template = json.loads(args.lock.read_text(), object_pairs_hook=unique)
    if args.if_needed and (args.output / 'source-lock.json').is_file():
        ready = SourceResolver(args.output, args.output / 'source-lock.json')
        if all(ready.repositories[group]['commit'] == spec['commit'] and ready.repositories[group]['repository'] == spec['repository'] for group, spec in template['repositories'].items()):
            ready.verify(); ready.coordinator_identity()
            print('Existing pinned source assembly verified')
            return
    if set(template) != {'schema_version', 'repositories', 'libraries'} or template['schema_version'] != 1 or set(template['repositories']) != set(GROUPS):
        raise ValueError('Invalid registered source lock')
    for group, spec in template['repositories'].items():
        if set(spec) != {'repository', 'commit', 'checkout', 'jobs'} or spec['repository'] != 'https://github.com/kyuhank/fisheries-workflow-' + group + '-demo' or not re.fullmatch(r'[a-f0-9]{40}', spec['commit']) or spec['jobs'] != list(GROUPS[group]):
            raise ValueError('Unregistered component or revision')
    if 'snapshot_manifest' in template:
        raise ValueError('Hydration requires live Git source pins')
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='fisheries-source-') as temporary:
        stage = Path(temporary)
        lock = json.loads(json.dumps(template))
        if args.local_root:
            for group, spec in lock['repositories'].items():
                name = spec['repository'].rsplit('/', 1)[-1]
                target = stage / name
                source = args.local_root.resolve() / name
                subprocess.run(['git', 'clone', '--quiet', '--no-hardlinks', str(source), str(target)], check=True)
                subprocess.run(['git', '-C', str(target), 'checkout', '--quiet', '--detach', spec['commit']], check=True)
                spec['checkout'] = name
        else:
            public_snapshot(lock, stage)
        live = stage / 'source-lock.json'
        live.write_text(json.dumps(lock, indent=2) + '\n')
        resolver = SourceResolver(ROOT, live)
        payload = resolver.archive_payload()
        # Bind the actual committed coordinator bytes, not a dirty linked-worktree HEAD.
        commit = args.coordinator_commit or git(ROOT, 'rev-parse', 'HEAD').decode().strip()
        if git(ROOT, 'rev-parse', 'HEAD').decode().strip() != commit or git(ROOT, 'status', '--porcelain', '--untracked-files=no').strip():
            raise ValueError('Coordinator must be clean at the declared committed candidate')
        tracked = git(ROOT, 'ls-tree', '-r', '--name-only', commit).decode().splitlines()
        from workflow.engine import source_payload
        closure_names = set(source_payload(SourceResolver(ROOT, False)))
        hashes = {}
        for name in tracked:
            actual = (ROOT / name).read_bytes()
            pinned = git(ROOT, 'show', commit + ':' + name)
            if actual != pinned:
                raise ValueError('Coordinator bytes differ from committed candidate: ' + name)
            if name in closure_names:
                hashes[name] = hashlib.sha256(actual).hexdigest()
        payload['coordinator-origin.json'] = (json.dumps({'schema_version': 1, 'repository': 'https://github.com/kyuhank/fisheries-workflow-demo', 'commit': commit, 'files': hashes}, indent=2) + '\n').encode()
        # Generated assembly only; no tracked sources or branch heads are rewritten.
        shutil.rmtree(output / 'components', ignore_errors=True)
        for name, data in payload.items():
            target = output / name
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(data)
        checked = SourceResolver(output, output / 'source-lock.json')
        checked.verify(); checked.coordinator_identity()
        print(json.dumps({'status': 'ASSEMBLED_VERIFIED', 'coordinator_commit': commit, 'components': {k: v['commit'] for k, v in template['repositories'].items()}, 'source_lock': str(output / 'source-lock.json')}, sort_keys=True))


if __name__ == '__main__':
    main()
