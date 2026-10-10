"""Resolve registered, immutable analysis sources and portable offline snapshots."""
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import subprocess

ROOT = Path(__file__).resolve().parents[1]
GROUPS = {
    'cpue': ('submission', 'qc', 'database', 'extract', 'cpue_a', 'cpue_b', 'cpue_summary', 'cpue_report'),
    'assessment': ('prepare_a', 'prepare_b', 'assessment_a1', 'assessment_a2', 'assessment_b1', 'assessment_b2', 'assessment_summary', 'assessment_report'),
    'mse': ('mse_prepare', 'mse_constant', 'mse_index', 'mse_buffered', 'mse_summary', 'mse_report'),
}
JOB_LIBRARIES = {key: () for keys in GROUPS.values() for key in keys}
JOB_LIBRARIES.update({key: ('cpue',) for key in ('database', 'cpue_a', 'cpue_b')})
JOB_LIBRARIES.update({key: ('assessment',) for key in GROUPS['assessment'] if key.startswith('assessment_') and key[-2:] in ('a1', 'a2', 'b1', 'b2')})
JOB_LIBRARIES['mse_prepare'] = ('assessment', 'mse')
JOB_LIBRARIES.update({key: ('mse',) for key in ('mse_constant', 'mse_index', 'mse_buffered', 'mse_summary')})


def sha(data):
    return hashlib.sha256(data).hexdigest()


def unique(items):
    result = {}
    for key, value in items:
        if key in result:
            raise ValueError('Duplicate source-lock field: ' + key)
        result[key] = value
    return result


def contained(base, name):
    """Accept explicit relative regular files/directories, never traversal/symlinks."""
    if not isinstance(name, str):
        raise ValueError('Unsafe source path: ' + str(name))
    p = PurePosixPath(name)
    if not isinstance(name, str) or not name or p.is_absolute() or '..' in p.parts or str(p) != name or '\\' in name:
        raise ValueError('Unsafe source path: ' + str(name))
    current = base
    for part in p.parts:
        current = current / part
        if current.is_symlink():
            raise ValueError('Symlink source path: ' + name)
    if not current.resolve().is_relative_to(base.resolve()):
        raise ValueError('Source path escapes registered checkout: ' + name)
    return current


def git(repo, *args):
    process = subprocess.run(['git', '-c', 'safe.directory=' + str(repo.resolve()), '-C', str(repo), *args],
                             capture_output=True, timeout=15)
    if process.returncode:
        raise ValueError('Source Git check failed: ' + process.stderr.decode(errors='replace')[-1000:])
    return process.stdout


class SourceResolver:
    def __init__(self, root=ROOT, lock_path=None):
        self.root = Path(root).resolve()
        monorepo = lock_path is False or (lock_path is None and os.environ.get('PAPER_SOURCE_MODE') == 'monorepo')
        selected = None if monorepo else lock_path or os.environ.get('PAPER_SOURCE_LOCK')
        if not monorepo and selected is None and (self.root / 'source-lock.json').is_file():
            selected = self.root / 'source-lock.json'
        if not monorepo and not selected and (self.root / 'source-lock.template.json').is_file():
            raise ValueError('Pinned component sources are not hydrated; run scripts/hydrate-sources.py or explicitly select monorepo mode')
        if selected and Path(selected).is_symlink():
            raise ValueError('Symlink source lock is not allowed')
        self.lock_path = Path(selected).resolve() if selected else None
        self.repositories = {}
        self._files = {}
        self._lock_bytes = None
        self.snapshot = False
        if self.lock_path:
            self._lock_bytes = self.lock_path.read_bytes()
            lock = json.loads(self._lock_bytes, object_pairs_hook=unique)
            if set(lock) not in ({'schema_version', 'repositories', 'libraries'},
                                 {'schema_version', 'repositories', 'libraries', 'snapshot_manifest'}):
                raise ValueError('Unexpected source-lock fields')
            if type(lock['schema_version']) is not int or lock['schema_version'] != 1:
                raise ValueError('Unsupported source-lock schema')
            if set(lock['repositories']) != set(GROUPS) or set(lock['libraries']) != set(GROUPS):
                raise ValueError('Register exactly the CPUE, assessment and MSE repositories/libraries')
            self.lock = lock
            self.snapshot = 'snapshot_manifest' in lock
            snapshot = None
            if self.snapshot:
                snapshot = json.loads(contained(self.lock_path.parent, lock['snapshot_manifest']).read_text(), object_pairs_hook=unique)
                if set(snapshot) != {'schema_version', 'sources'} or snapshot['schema_version'] != 1:
                    raise ValueError('Invalid offline source origin manifest')
                self._snapshot_bytes = json.dumps(snapshot, sort_keys=True)
            for group, spec in lock['repositories'].items():
                if set(spec) != {'repository', 'commit', 'checkout', 'jobs'}:
                    raise ValueError('Unexpected repository registration fields')
                expected = 'https://github.com/kyuhank/fisheries-workflow-' + group + '-demo'
                if spec['repository'] != expected or not re.fullmatch(r'[a-f0-9]{40}', spec['commit']):
                    raise ValueError('Unregistered repository or incomplete source revision')
                if spec['jobs'] != list(GROUPS[group]):
                    raise ValueError('Repository job ownership must preserve the declared 8/8/6 partition')
                checkout = contained(self.lock_path.parent, spec['checkout'])
                if not checkout.is_dir():
                    raise ValueError('Missing registered source checkout: ' + group)
                self.repositories[group] = {**spec, 'root': checkout}
                if self.snapshot:
                    prefix = 'components/' + group + '/'
                    entries = {name[len(prefix):]: origin for name, origin in snapshot['sources'].items() if name.startswith(prefix)}
                    if not entries:
                        raise ValueError('Missing component snapshot origins: ' + group)
                    for name, origin in entries.items():
                        if set(origin) != {'repository', 'commit', 'path', 'sha256'} or origin['repository'] != expected or origin['commit'] != spec['commit'] or origin['path'] != name or not re.fullmatch(r'[a-f0-9]{64}', origin['sha256']):
                            raise ValueError('Inconsistent offline source origin: ' + group)
                    self._files[group] = {name: origin['sha256'] for name, origin in entries.items()}
                else:
                    if git(checkout, 'rev-parse', 'HEAD').decode().strip() != spec['commit']:
                        raise ValueError('Wrong pinned source revision: ' + group)
                    names = git(checkout, 'ls-tree', '-r', '--name-only', spec['commit']).decode().splitlines()
                    self._files[group] = {name: sha(git(checkout, 'show', spec['commit'] + ':' + name)) for name in names}
                library = lock['libraries'][group]
                if library != {'repository': group, 'path': 'R/' + group + '.R'}:
                    raise ValueError('Unexpected component calculation library: ' + group)
                required = [f'jobs/{key}/run.R' for key in GROUPS[group]] + ['R/' + group + '.R']
                required += [f'jobs/{key}/report.qmd' for key in GROUPS[group] if key.endswith('_report')]
                if not set(required) <= set(self._files[group]):
                    raise ValueError('Missing required component source: ' + group)
            self.verify()

    @property
    def multi_repository(self):
        return bool(self.lock_path)

    def verify(self):
        if not self.multi_repository:
            return
        if self.lock_path.read_bytes() != self._lock_bytes:
            raise ValueError('Source lock changed during resolved session')
        if self.snapshot:
            current = json.loads(contained(self.lock_path.parent, self.lock['snapshot_manifest']).read_text(), object_pairs_hook=unique)
            if json.dumps(current, sort_keys=True) != self._snapshot_bytes:
                raise ValueError('Offline source origin manifest changed')
        for group, spec in self.repositories.items():
            root = spec['root']
            if not self.snapshot:
                if git(root, 'rev-parse', 'HEAD').decode().strip() != spec['commit']:
                    raise ValueError('Wrong pinned source revision: ' + group)
                if git(root, 'status', '--porcelain', '--untracked-files=all').strip():
                    raise ValueError('Source checkout must be clean: ' + group)
            for name, checksum in self._files[group].items():
                path = contained(root, name)
                if not path.is_file() or sha(path.read_bytes()) != checksum:
                    raise ValueError('Source byte mismatch: ' + group + '/' + name)

    def group(self, key):
        for group, keys in GROUPS.items():
            if key in keys:
                return group
        raise ValueError('Unregistered analysis job: ' + key)

    def job_path(self, key, name='run.R'):
        if name not in ('run.R', 'report.qmd', 'README.md'):
            raise ValueError('Unregistered job source file')
        group = self.group(key)
        root = self.repositories[group]['root'] if self.multi_repository else self.root
        return contained(root, 'jobs/' + key + '/' + name)

    def library_paths(self, key):
        common = self.root / 'workflow/r/common.R'
        if not self.multi_repository:
            return [common, self.root / 'workflow/r/models.R', self.root / 'workflow/r/mse.R']
        return [common, *(contained(self.repositories[group]['root'], self.lock['libraries'][group]['path']) for group in JOB_LIBRARIES[key])]

    def runtime(self, key):
        self.verify()
        return {'job': str(self.job_path(key).resolve()), 'libraries': [str(p.resolve()) for p in self.library_paths(key)]}

    def coordinator_identity(self):
        path = self.root / 'coordinator-origin.json'
        if path.is_file():
            origin = json.loads(path.read_text(), object_pairs_hook=unique)
            if set(origin) != {'schema_version', 'repository', 'commit', 'files'} or origin['schema_version'] != 1 or origin['repository'] != 'https://github.com/kyuhank/fisheries-workflow-demo' or not re.fullmatch(r'[a-f0-9]{40}', origin['commit']):
                raise ValueError('Invalid frozen coordinator identity')
            required = {'run.py', 'verify.py', 'Makefile', 'workflow/engine.py', 'workflow/spec.py',
                        'workflow/r_bridge.py', 'workflow/r_driver.R', 'workflow/Makefile',
                        'workflow/jobs.json', 'workflow/sources.py', 'workflow/contracts.py',
                        'workflow/reports.py', 'workflow/quarto_reports.py', 'workflow/r/common.R'}
            if not isinstance(origin['files'], dict) or not required <= set(origin['files']):
                raise ValueError('Frozen coordinator identity is missing executable source pins')
            for name, checksum in origin['files'].items():
                if not isinstance(checksum, str) or not re.fullmatch(r'[a-f0-9]{64}', checksum):
                    raise ValueError('Invalid coordinator source checksum')
                actual = contained(self.root, name)
                if not actual.is_file() or sha(actual.read_bytes()) != checksum:
                    raise ValueError('Coordinator source byte mismatch: ' + name)
            return {'repository': origin['repository'], 'commit': origin['commit']}
        # Unassembled development fixtures have file hashes, without a certified commit.
        return {'repository': 'https://github.com/kyuhank/fisheries-workflow-demo', 'commit': None}

    def origin(self, key, name='run.R'):
        path = self.job_path(key, name)
        if self.multi_repository:
            group = self.group(key)
            spec = self.repositories[group]
            return {'repository': spec['repository'], 'commit': spec['commit'], 'path': f'jobs/{key}/{name}', 'sha256': sha(path.read_bytes())}
        info = json.loads((self.root / 'build-info.json').read_text()) if (self.root / 'build-info.json').exists() else {}
        return {'repository': info.get('repository', 'https://github.com/kyuhank/fisheries-workflow-demo'), 'commit': info.get('commit'), 'path': f'jobs/{key}/{name}', 'sha256': sha(path.read_bytes())}

    def required_files(self, key):
        result = {}
        job = self.job_path(key)
        result[self.archive_name(job)] = job
        for path in self.library_paths(key):
            result[self.archive_name(path)] = path
        if key.endswith('_report'):
            qmd = self.job_path(key, 'report.qmd')
            result[self.archive_name(qmd)] = qmd
        return result

    def archive_name(self, path):
        path = Path(path)
        for group, spec in self.repositories.items():
            if path.is_relative_to(spec['root']):
                return 'components/' + group + '/' + path.relative_to(spec['root']).as_posix()
        return path.relative_to(self.root).as_posix()

    def code_sources(self, key):
        result = {}
        for name, path in self.required_files(key).items():
            if name.startswith('components/'):
                group = name.split('/')[1]
                spec = self.repositories[group]
                result[name] = {'repository': spec['repository'], 'commit': spec['commit'], 'path': path.relative_to(spec['root']).as_posix(), 'sha256': sha(path.read_bytes())}
            else:
                result[name] = {**self.coordinator_identity(), 'path': name, 'sha256': sha(path.read_bytes())}
        return result

    def archive_files(self):
        if not self.multi_repository:
            return {p.relative_to(self.root).as_posix(): p for p in (self.root / 'jobs').rglob('*') if p.is_file() and p.suffix in ('.md', '.R', '.qmd')}
        self.verify()
        return {'components/' + group + '/' + name: contained(spec['root'], name)
                for group, spec in self.repositories.items() for name in self._files[group]}

    def archive_payload(self):
        files = {name: path.read_bytes() for name, path in self.archive_files().items()}
        if self.multi_repository:
            lock = json.loads(self._lock_bytes)
            origins = {}
            for group, spec in self.repositories.items():
                lock['repositories'][group]['checkout'] = 'components/' + group
                for name, checksum in self._files[group].items():
                    origins['components/' + group + '/' + name] = {'repository': spec['repository'], 'commit': spec['commit'], 'path': name, 'sha256': checksum}
            lock['snapshot_manifest'] = 'source-origins.json'
            files['source-lock.json'] = (json.dumps(lock, indent=2) + '\n').encode()
            files['source-origins.json'] = (json.dumps({'schema_version': 1, 'sources': origins}, indent=2) + '\n').encode()
        return files
