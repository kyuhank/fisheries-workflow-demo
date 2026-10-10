"""Verify registered Git pins, then assemble exact offline source snapshots."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from workflow.sources import SourceResolver, git, GROUPS
import re


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
    template = json.loads(args.lock.read_text())
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
        for group, spec in lock['repositories'].items():
            name = spec['repository'].rsplit('/', 1)[-1]
            target = stage / name
            if args.local_root:
                source = args.local_root.resolve() / name
                subprocess.run(['git', 'clone', '--quiet', '--no-hardlinks', str(source), str(target)], check=True)
            else:
                subprocess.run(['git', 'clone', '--quiet', '--no-checkout', spec['repository'] + '.git', str(target)], check=True)
            subprocess.run(['git', '-C', str(target), 'checkout', '--quiet', '--detach', spec['commit']], check=True)
            spec['checkout'] = name
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
