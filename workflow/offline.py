"""Verify a preserved source bundle and the exact local Docker runtime.

The registry digest names the upstream image. A Docker save/load restoration is
verified by config ID and ordered filesystem diff IDs, even without RepoDigests.
No registry access, scientific calculation or Docker call occurs in this module's
validation functions. The command entry point runs only after those checks.
"""
import argparse
import asyncio
import gzip
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import signal
import sys
import tarfile
import time

UPSTREAM_IMAGE = 'ghcr.io/pacificcommunity/fisheries-workflow@sha256:9dea950a713b87daad728517138bcb664a151f0f5b44a1d5370623734a5bca9d'
IMAGE_ID = 'sha256:3f2b5d1eccea99114d3e089f281bdd531cbd2f1cfd8405d4f3b68722136c0158'
IMAGE_URL = 'https://github.com/PacificCommunity/ofp-sam-docker-images/pkgs/container/fisheries-workflow'
DIFF_IDS = (
    'sha256:98effb2dfe85d4c431f97d90482075f19e5fc3a57c2dd423d8bdfd4813620043',
    'sha256:613659109016edd06de370f7bc2025e102bdcddaeac9de63a7b539d8bf3b1ae1',
    'sha256:0b37a25965e9e9119a64e622f3101c8b7ef9f6eacab3a6dd9a4b062e9550f948',
    'sha256:b52c4fe3ae39d7f3c34a04f72ac1e8ea873cbb9645bd2ea9bfe58f841059b60b',
    'sha256:26cd91d7da066e47b7463ffd3d6e1795f3ba2d036f4a078b73cf3579830bc009',
    'sha256:3a4afdc4e1d09235c386e112b3f8c8779ca06dcdeac06099001ba3260d49639d',
    'sha256:853a19e9d9bf3fee97141848b791a845454f147bf9a3c61707b124c676288c6c',
    'sha256:56accf9e26339a6b30b33f4f17954bb9931861898b4e82f41fc3ddce60c59f54',
    'sha256:9d662917e398066bfc676c31a09d46648e38baf92db0ef55a76f1ae800732fca',
    'sha256:655fde5934fb72434f5b0212542cb467d110a5d8c9e6fc2c8d5304643245afd3',
    'sha256:616cadc63d516bc79ef6ffd13f95736739bdd9f8711ed03f93228276e318f545',
    'sha256:60860921f93d2910563d7bb8e2bdcc06b93f70698e6e5c63b96de67f8dbb0700',
)
ARCHIVE_NAME = 'fisheries-workflow-runtime.tar.gz'
RECEIPT_NAME = 'runtime-archive.json'
MAX_ARCHIVE = 2_000_000_000
MAX_TAR = 8_000_000_000


def sha(data):
    return hashlib.sha256(data).hexdigest()


def unique(items):
    result = {}
    for key, value in items:
        if key in result:
            raise ValueError('Duplicate preserved metadata field: ' + key)
        result[key] = value
    return result


def read_json(path):
    return json.loads(Path(path).read_text(), object_pairs_hook=unique)


def safe_file(root, name):
    path = PurePosixPath(name) if isinstance(name, str) else None
    if (not path or not name or path.is_absolute() or '..' in path.parts
            or str(path) != name or '\\' in name):
        raise ValueError('Unsafe preserved file path: ' + str(name))
    target = Path(root)
    for part in path.parts:
        target = target / part
        if target.is_symlink():
            raise ValueError('Symlink in preserved files: ' + name)
    if not target.is_file():
        raise ValueError('Missing preserved file: ' + name)
    return target


def runtime_metadata():
    return {'schema_version': 1, 'upstream_registry_digest': UPSTREAM_IMAGE,
            'config_id': IMAGE_ID, 'platform': 'linux/amd64',
            'rootfs_diff_ids': list(DIFF_IDS),
            'identity_note': 'Docker save/load may omit registry RepoDigests. Verify and launch the config ID with these ordered rootfs diff IDs; the upstream digest remains a source pin.'}


def verify_image(inspect, metadata=None):
    if metadata is not None and metadata != runtime_metadata():
        raise ValueError('Preserved runtime metadata differs from the fixed SPC runtime')
    if (not isinstance(inspect, dict) or inspect.get('Id') != IMAGE_ID
            or inspect.get('Os') != 'linux' or inspect.get('Architecture') != 'amd64'
            or inspect.get('RootFS', {}).get('Type') != 'layers'
            or inspect.get('RootFS', {}).get('Layers') != list(DIFF_IDS)):
        raise ValueError('Local image config, platform or ordered rootfs diff IDs do not match')
    digests = inspect.get('RepoDigests') or []
    if not isinstance(digests, list) or any(not isinstance(item, str) for item in digests):
        raise ValueError('Invalid local image digest metadata')
    present = UPSTREAM_IMAGE in digests
    return {**runtime_metadata(), 'launch_reference': IMAGE_ID,
            'local_repo_digests': digests, 'upstream_reference_present_locally': present,
            'verification_basis': 'config ID, platform and ordered rootfs diff IDs',
            'registry_digest_verified_locally': present, 'pull_policy': 'never', 'network': 'none'}


def verify_manifest(root):
    root = Path(root)
    manifest_path = safe_file(root, 'SHA256SUMS.json')
    manifest = read_json(manifest_path)
    if not isinstance(manifest, dict) or not manifest or len(manifest) > 4096:
        raise ValueError('Invalid preserved source checksum manifest')
    required = {'run.py', 'verify.py', 'workflow/engine.py', 'workflow/spec.py',
                'workflow/sources.py', 'workflow/contracts.py', 'workflow/r_bridge.py',
                'workflow/r_driver.R', 'workflow/Makefile', 'workflow/jobs.json',
                'workflow/reports.py', 'workflow/quarto_reports.py', 'workflow/r/common.R',
                'scripts/offline.sh', 'scripts/offline-runtime.py', 'scripts/preserve-runtime.sh',
                'workflow/offline.py', 'runtime-preservation.json', 'source-lock.json',
                'source-origins.json', 'coordinator-origin.json'}
    # Every importable workflow module and supplied input must be covered too.
    required.update(p.relative_to(root).as_posix() for folder in ('workflow', 'data')
                    for p in (root / folder).rglob('*') if p.is_file()
                    and '__pycache__' not in p.parts and p.suffix != '.pyc')
    if not required <= set(manifest):
        raise ValueError('Source manifest is missing required files: ' + ', '.join(sorted(required - set(manifest))))
    for name, checksum in manifest.items():
        if not isinstance(checksum, str) or not re.fullmatch(r'[0-9a-f]{64}', checksum):
            raise ValueError('Invalid preserved checksum: ' + name)
        if sha(safe_file(root, name).read_bytes()) != checksum:
            raise ValueError('Preserved source byte mismatch: ' + name)
    if read_json(safe_file(root, 'runtime-preservation.json')) != runtime_metadata():
        raise ValueError('Preserved runtime metadata differs from the fixed SPC runtime')
    return {'manifest_sha256': sha(manifest_path.read_bytes()), 'checksummed_files': len(manifest)}


def verify_sources(root):
    manifest = verify_manifest(root)
    # Imports occur after source checks; no Git executable is needed for snapshots.
    from .sources import SourceResolver
    resolver = SourceResolver(root, Path(root) / 'source-lock.json')
    if not resolver.snapshot:
        raise ValueError('Offline execution requires portable component snapshots, not Git checkouts')
    resolver.verify()
    identity = resolver.coordinator_identity()
    if not identity.get('commit'):
        raise ValueError('Preserved coordinator has no committed source identity')
    return {**manifest, 'coordinator_origin': identity,
            'component_origins': {group: {'repository': spec['repository'], 'commit': spec['commit']}
                                  for group, spec in resolver.repositories.items()}}


def deadline(seconds):
    def expired(signum, frame):
        raise TimeoutError('Finite offline command deadline exceeded')
    signal.signal(signal.SIGALRM, expired)
    signal.alarm(seconds)


def hash_file(path):
    checksum = hashlib.sha256()
    with Path(path).open('rb') as stream:
        while data := stream.read(1024 * 1024):
            checksum.update(data)
    return checksum.hexdigest()


def verify_saved_tar(path):
    """Check the one-image Docker save archive without extracting its contents."""
    hashes, small, names, total = {}, {}, set(), 0
    with tarfile.open(path, 'r|gz') as archive:
        for member in archive:
            name = member.name
            p = PurePosixPath(name)
            if p.is_absolute() or '..' in p.parts or '\\' in name or name in names:
                raise ValueError('Unsafe or repeated runtime archive member')
            names.add(name)
            if len(names) > 4096 or not (member.isfile() or member.isdir()):
                raise ValueError('Unsupported runtime archive member')
            if member.isdir():
                continue
            total += member.size
            if total > MAX_TAR:
                raise ValueError('Uncompressed runtime archive exceeds its finite byte bound')
            source = archive.extractfile(member)
            checksum, kept = hashlib.sha256(), bytearray()
            while data := source.read(1024 * 1024):
                checksum.update(data)
                if member.size <= 2_000_000:
                    kept.extend(data)
            hashes[name] = checksum.hexdigest()
            if member.size <= 2_000_000:
                small[name] = bytes(kept)
    if 'manifest.json' not in small:
        raise ValueError('A Docker save archive with manifest.json is required')
    manifest = json.loads(small['manifest.json'], object_pairs_hook=unique)
    if not isinstance(manifest, list) or len(manifest) != 1:
        raise ValueError('Preserve exactly one Docker image')
    config_name, layers = manifest[0].get('Config'), manifest[0].get('Layers')
    if config_name not in small or 'sha256:' + hashes[config_name] != IMAGE_ID:
        raise ValueError('Saved image config bytes differ from the pinned config ID')
    config = json.loads(small[config_name], object_pairs_hook=unique)
    if (config.get('os') != 'linux' or config.get('architecture') != 'amd64'
            or config.get('rootfs') != {'type': 'layers', 'diff_ids': list(DIFF_IDS)}):
        raise ValueError('Saved image platform or rootfs differs from the pinned runtime')
    if (not isinstance(layers, list) or len(layers) != len(DIFF_IDS)
            or ['sha256:' + hashes.get(name, '') for name in layers] != list(DIFF_IDS)):
        raise ValueError('Saved ordered layer bytes differ from the pinned diff IDs')
    return {'saved_config_verified': True, 'saved_layer_bytes_verified': True,
            'tar_payload_bytes': total, 'tar_members': len(names)}


def archive_save(directory, inspect, stream):
    runtime = verify_image(inspect)
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    target = directory / ARCHIVE_NAME
    if target.exists() or (directory / RECEIPT_NAME).exists():
        raise ValueError('Runtime preservation destination already contains an archive or receipt')
    partial = directory / (ARCHIVE_NAME + '.partial')
    with partial.open('xb') as raw:
        with gzip.GzipFile(filename='', fileobj=raw, mode='wb', mtime=0) as compressed:
            total = 0
            while data := stream.read(1024 * 1024):
                total += len(data)
                if total > MAX_TAR:
                    raise ValueError('Runtime Docker-save stream exceeds its finite byte bound')
                compressed.write(data)
                if raw.tell() > MAX_ARCHIVE:
                    raise ValueError('Compressed runtime archive exceeds 2 GB')
    if partial.stat().st_size > MAX_ARCHIVE:
        raise ValueError('Compressed runtime archive exceeds 2 GB')
    proof = verify_saved_tar(partial)
    partial.rename(target)
    receipt = {'schema_version': 1, 'status': 'ARCHIVE_VERIFIED', 'runtime': runtime,
               'archive': {'file': ARCHIVE_NAME, 'sha256': hash_file(target), 'bytes': target.stat().st_size},
               **proof, 'load_note': 'Docker load restores image/config/layers, not necessarily the original registry RepoDigest. Launch by the verified config ID.'}
    data = (json.dumps(receipt, indent=2) + '\n').encode()
    (directory / RECEIPT_NAME).write_bytes(data)
    (directory / 'SHA256SUMS.json').write_text(json.dumps({ARCHIVE_NAME: receipt['archive']['sha256'], RECEIPT_NAME: sha(data)}, indent=2) + '\n')
    return receipt


def archive_verify(directory, inspect):
    runtime = verify_image(inspect)
    directory = Path(directory)
    manifest = read_json(safe_file(directory, 'SHA256SUMS.json'))
    if set(manifest) != {ARCHIVE_NAME, RECEIPT_NAME}:
        raise ValueError('Unexpected runtime archive checksum fields')
    for name, checksum in manifest.items():
        if not isinstance(checksum, str) or not re.fullmatch(r'[0-9a-f]{64}', checksum) or hash_file(safe_file(directory, name)) != checksum:
            raise ValueError('Runtime archive checksum mismatch: ' + name)
    receipt = read_json(safe_file(directory, RECEIPT_NAME))
    if (receipt.get('schema_version') != 1 or receipt.get('status') != 'ARCHIVE_VERIFIED'
            or receipt.get('runtime', {}).get('config_id') != IMAGE_ID
            or receipt.get('runtime', {}).get('rootfs_diff_ids') != list(DIFF_IDS)
            or receipt.get('runtime', {}).get('upstream_registry_digest') != UPSTREAM_IMAGE
            or receipt.get('archive') != {'file': ARCHIVE_NAME, 'sha256': manifest[ARCHIVE_NAME], 'bytes': (directory / ARCHIVE_NAME).stat().st_size}
            or (directory / ARCHIVE_NAME).stat().st_size > MAX_ARCHIVE):
        raise ValueError('Runtime preservation receipt does not match the actual archive')
    return {'status': 'ARCHIVE_AND_LOCAL_IMAGE_VERIFIED', 'runtime': runtime,
            'archive': receipt['archive'], **verify_saved_tar(directory / ARCHIVE_NAME)}


def reference_scope(root, reference, job=None):
    from .spec import SPEC
    state = read_json(safe_file(root, reference + '/state.json'))
    plan = state.get('last_plan') or {}
    selected = job or (plan.get('start') if plan.get('scope') == 'job' else None)
    if selected is not None and selected not in SPEC:
        raise ValueError('Unknown saved job to reproduce/compare')
    settings_path = root / 'settings.json'
    settings = read_json(settings_path) if settings_path.is_file() else state['settings']
    return settings, selected


def run_offline(root, args, inspect):
    source = verify_sources(root)
    runtime = verify_image(inspect, read_json(root / 'runtime-preservation.json'))
    if args.command == 'check':
        return {'status': 'SOURCE_AND_LOCAL_IMAGE_VERIFIED', 'sources': source, 'runtime': runtime}
    from .engine import Workflow
    from .r_bridge import RBridge
    from .spec import SPEC
    from verify import verify
    if args.job is not None and args.job not in SPEC:
        raise ValueError('Unknown job: ' + args.job)
    reference = args.reference or ('reference' if (root / 'reference/state.json').is_file() else 'example')
    # Validate source/reference paths before opening them; checksum verification above
    # includes the complete preserved reference. Caller-supplied settings are recorded.
    if args.command in ('reproduce', 'compare'):
        settings, selected = reference_scope(root, reference, args.job)
    else:
        settings, selected = None, args.job
    output = Path(args.output)
    receipt = {'schema_version': 1, 'status': 'STARTED', 'command': args.command,
               'provider': 'Local Docker', 'purpose': 'offline ' + args.command,
               'selected_job': selected, 'sources': source, 'runtime': runtime,
               'resources': {'docker_cpus': 2, 'docker_memory_bytes': 4294967296, 'command_timeout_seconds': 1200},
               'reader_label': os.environ.get('PAPER_OFFLINE_READER', 'unspecified reader'),
               'reader_identity_verification': 'caller-supplied label; not independently attested'}
    if args.command == 'compare':
        receipt_path = output / 'offline-comparison.json'
        began = time.monotonic()
        try:
            count = verify(root / reference, output, selected)
            receipt.update(status='PASSED', outputs_compared=count)
        except BaseException as error:
            receipt.update(status='FAILED', error_type=type(error).__name__, error=str(error))
            raise
        finally:
            receipt['elapsed_seconds'] = time.monotonic() - began
            if output.is_dir():
                receipt_path.write_text(json.dumps(receipt, indent=2) + '\n')
        return receipt
    if args.command == 'reproduce' and (output / 'state.json').exists():
        raise ValueError('Reproduction requires a fresh output directory; choose PAPER_OFFLINE_OUTPUT')
    class PreservedBridge(RBridge):
        def software(self):
            return {**super().software(), 'container_reference_kind': 'upstream registry source pin',
                    'container_config_id': IMAGE_ID, 'container_rootfs_diff_ids': list(DIFF_IDS),
                    'registry_digest_verified_locally': runtime['registry_digest_verified_locally']}
    output.mkdir(parents=True, exist_ok=True)
    receipt_path = output / 'offline-execution.json'
    began = time.monotonic()
    receipt_path.write_text(json.dumps(receipt, indent=2) + '\n')
    try:
        runner = Workflow(output, r_bridge=PreservedBridge(),
                          notify=lambda event: print(event.get('job', 'Workflow'), event['state'], event.get('message', ''), flush=True))
        # Preserve the original local execution={} default. The frozen report
        # renderer interprets a nonempty execution as GitHub Actions. Actual local
        # custody belongs in this separate receipt and the per-job software fields.
        if args.settings:
            path = safe_file(root, args.settings)
            settings = read_json(path)
            receipt['caller_settings'] = {'path': args.settings, 'sha256': hash_file(path)}
        if settings is not None:
            runner.configure(settings)
        start = selected or 'submission'
        result = asyncio.run(runner.run(start, 'job' if selected else 'workflow'))
        receipt.update(status='PASSED', jobs_executed=result['run'], jobs_retained=result['retained'],
                       analysis_run_id=result['run_id'], state_sha256=hash_file(output / 'state.json'),
                       elapsed_seconds=time.monotonic() - began)
    except BaseException as error:
        receipt.update(status='FAILED', error_type=type(error).__name__, error=str(error),
                       elapsed_seconds=time.monotonic() - began)
        raise
    finally:
        receipt_path.write_text(json.dumps(receipt, indent=2) + '\n')
    return receipt


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=('run', 'job', 'reproduce', 'compare', 'check', 'archive-save', 'archive-verify'))
    parser.add_argument('job', nargs='?')
    parser.add_argument('--reference', help='Relative saved reference directory; default reference/ or example/')
    parser.add_argument('--settings', help='Relative caller settings JSON file (run/job only)')
    parser.add_argument('--output', default='/outputs')
    args = parser.parse_args()
    if args.command == 'job' and not args.job:
        parser.error('Use job JOB, for example job cpue_a')
    if args.job and args.command not in ('job', 'reproduce', 'compare'):
        parser.error('This command does not accept a job argument')
    if args.settings and args.command not in ('run', 'job'):
        parser.error('Use supplied saved settings for reproduce/compare')
    root = Path(__file__).resolve().parents[1]
    inspect = json.loads(os.environ['PAPER_OFFLINE_IMAGE_INSPECT'], object_pairs_hook=unique)
    deadline(900 if args.command.startswith('archive-') else 1200)
    if args.command == 'archive-save':
        result = archive_save(args.output, inspect, sys.stdin.buffer)
    elif args.command == 'archive-verify':
        result = archive_verify(args.output, inspect)
    else:
        result = run_offline(root, args, inspect)
    print(json.dumps(result, indent=2), flush=True)


if __name__ == '__main__':
    main()
