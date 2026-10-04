"""Execute selected jobs, verify saved inputs and preserve their original records."""
import asyncio
import hashlib
import io
from importlib import import_module
import json
from pathlib import Path
import platform
import shutil
import sqlite3
import sys
import zipfile

from . import reports
from .spec import DEFAULTS, SPEC, STAGES, active_spec, downstream, handover_groups

ROOT = Path(__file__).resolve().parents[1]


def digest(data):
    return hashlib.sha256(data).hexdigest()


def encoded(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()


def read_json(path):
    return json.loads(path.read_text())


def job_files():
    """Executable jobs and their reader guides, without cached bytecode or outputs."""
    return sorted(path for path in (ROOT / 'jobs').rglob('*')
                  if path.is_file() and path.suffix in ('.py', '.md'))


class Workflow:
    def __init__(self, directory='runs', notify=None, pause=0, before_job=None,
                 manual_transfer=None):
        self.directory = Path(directory)
        self.directory.mkdir(parents=True, exist_ok=True)
        self.notify = notify or (lambda event: None)
        self.pause = pause
        self.before_job = before_job
        self.manual_transfer = manual_transfer
        self.settings = dict(DEFAULTS)
        self.records = {}
        self.events = []
        self.run_number = 0
        self.last_plan = None
        self.running = False
        self.execution = {}
        state = self.directory / 'state.json'
        if state.exists():
            previous = read_json(state)
            self.records = previous['records']
            self.settings = {**DEFAULTS, 'mse': False, **previous['settings']}
            self.run_number = previous['run_number']
            self.last_plan = previous.get('last_plan')

    def configure(self, settings):
        candidate = {**self.settings, **settings}
        if set(candidate) != set(DEFAULTS):
            raise ValueError('Unknown analysis setting.')
        if candidate['last_year'] not in (2021, 2022, 2023, 2024):
            raise ValueError('Select a supplied data snapshot.')
        if candidate['min_hooks_a'] not in (0, 1200):
            raise ValueError('Select one of the supplied CPUE filters.')
        if candidate['mortality_2'] not in (0.25, 0.30, 0.35):
            raise ValueError('Select one of the supplied mortality settings.')
        if type(candidate['mse']) is not bool:
            raise ValueError('Select whether to include the MSE analyses.')
        if (type(candidate['mse_buffer']) not in (int, float) or
                candidate['mse_buffer'] not in (0.6, 0.8, 1.0)):
            raise ValueError('Select one of the supplied MSE catch buffers.')
        self.settings = candidate

    @property
    def spec(self):
        return active_spec(self.settings)

    def output(self, key):
        return read_json(self.directory / key / 'output.json')

    def job_settings(self, key):
        if key == 'submission':
            return {'last_year': self.settings['last_year']}
        if key == 'cpue_a':
            return {'min_hooks': self.settings['min_hooks_a']}
        if key in ('assessment_a2', 'assessment_b2'):
            return {'M': self.settings['mortality_2']}
        if key in ('assessment_a1', 'assessment_b1'):
            return {'M': 0.20}
        if key == 'mse_buffered':
            return {'buffer': self.settings['mse_buffer']}
        return {}

    def code_record(self, key):
        names = ['workflow/engine.py', 'workflow/spec.py', 'workflow/reports.py',
                 'jobs/__init__.py', f'jobs/{key}/__init__.py', f'jobs/{key}/run.py']
        if key.startswith(('cpue_', 'assessment_')) or key == 'database':
            names += ['workflow/models.py', 'workflow/age_model.py']
        if key == 'extract':
            names += ['workflow/extract.sql', 'workflow/extract-catch.sql']
        if key.startswith('mse_'):
            names += ['workflow/mse.py', 'workflow/age_model.py']
        return {name: digest((ROOT / name).read_bytes()) for name in names}

    def signature(self, key):
        parents = {parent: {'signature': self.records.get(parent, {}).get('signature'),
                            'outputs': self.records.get(parent, {}).get('outputs')}
                   for parent in SPEC[key]['parents']}
        material = {'code': self.code_record(key), 'settings': self.job_settings(key),
                    'parents': parents, 'software': self.software()}
        if key == 'submission':
            material['data'] = {name: digest((ROOT / 'data' / name).read_bytes())
                                for name in ['fishery.sqlite', 'submission.json']}
        return digest(encoded(material))

    @staticmethod
    def software():
        return {'python': platform.python_version(), 'platform': sys.platform,
                'runtime': 'Pyodide 0.27.7' if sys.platform == 'emscripten' else 'CPython',
                'sqlite': sqlite3.sqlite_version}

    def valid(self, key):
        record = self.records.get(key)
        if not record or record['signature'] != self.signature(key):
            return False
        return all((self.directory / key / name).is_file()
                   and digest((self.directory / key / name).read_bytes()) == checksum
                   for name, checksum in record['outputs'].items())

    def plan(self, start, scope='workflow'):
        spec = self.spec
        if start not in spec:
            raise ValueError('Unknown starting job.')
        if scope not in ('workflow', 'job'):
            raise ValueError('Select job or workflow execution.')
        changed = [key for key in spec if not self.valid(key)]
        if scope == 'workflow':
            selected = downstream([start, *changed], spec)
        else:
            required = set()

            def include_inputs(key):
                if key in required:
                    return
                required.add(key)
                for parent in spec[key]['parents']:
                    include_inputs(parent)

            include_inputs(start)
            selected = []
            for key, job in spec.items():
                if key in required and (key == start or key in changed or
                                        any(parent in selected for parent in job['parents'])):
                    selected.append(key)
        return {'run': selected,
                'retained': [key for key in spec if key not in selected and key in self.records],
                'changed': changed, 'start': start, 'scope': scope}

    def record_event(self, key, state, message, **details):
        event = {'job': key, 'state': state, 'message': message, **details}
        self.events.append(event)
        self.notify({**event, 'record': self.records.get(key)})

    async def emit(self, key, state, message, **details):
        self.record_event(key, state, message, **details)
        if self.pause and state in ('running', 'failed', 'returned', 'received'):
            await asyncio.sleep(self.pause)

    def source_rows(self):
        with sqlite3.connect(f'file:{ROOT / "data/fishery.sqlite"}?mode=ro', uri=True) as db:
            db.row_factory = sqlite3.Row
            rows = [dict(r) for r in db.execute('SELECT * FROM sets ORDER BY year,set_id')]
            catch = [dict(r) for r in db.execute('SELECT * FROM removals ORDER BY year')]
        if self.settings['last_year'] == 2024:
            batch = read_json(ROOT / 'data/submission.json')
            rows += [dict(zip(['set_id','year','vessel','hooks','catch_n'], row)) for row in batch['sets']]
            catch.append({'year': 2024, 'catch_t': batch['catch']})
        end = self.settings['last_year']
        return {'sets': [r for r in rows if r['year'] <= end],
                'catch': [r for r in catch if r['year'] <= end]}

    def save(self, key, result, run_id):
        folder = self.directory / key
        folder.mkdir(exist_ok=True)
        (folder / 'output.json').write_bytes(encoded(result))
        outputs = {'output.json': digest((folder / 'output.json').read_bytes())}
        if key == 'database':
            outputs['snapshot.sqlite'] = digest((folder / 'snapshot.sqlite').read_bytes())
        record = {'job': key, 'owner': SPEC[key]['owner'], 'run_id': run_id,
                  'signature': self.signature(key), 'settings': self.job_settings(key),
                  'snapshot': self.settings['last_year'], 'code': self.code_record(key),
                  'software': self.software(), 'outputs': outputs,
                  'log': [e['message'] for e in self.events if e['job'] == key or
                          (e['state'] in ('handover', 'received') and key in e.get('group', []))]
                         + [SPEC[key]['title'] + ' complete.'],
                  'inputs': {parent: {'run_id': self.records[parent]['run_id'],
                                      'checksum': self.records[parent]['outputs']['output.json']}
                             for parent in SPEC[key]['parents']}}
        if self.execution:
            record['execution'] = dict(self.execution)
        build = ROOT / 'build-info.json'
        if build.exists():
            record['source'] = read_json(build)
        if self.execution.get('commit'):
            record['source'] = {'repository': 'https://github.com/' + self.execution['repository'],
                                'commit': self.execution['commit']}
        record['data_files'] = {name: digest((ROOT / 'data' / name).read_bytes())
                                for name in ['fishery.sqlite', 'submission.json']}
        self.records[key] = record
        lineage = [{'job': SPEC[parent]['title'], **details} for parent, details in record['inputs'].items()]
        (folder / 'report.html').write_text(reports.output_page(SPEC[key], result, record, lineage))
        record['outputs']['report.html'] = digest((folder / 'report.html').read_bytes())
        (folder / 'record.json').write_text(json.dumps(record, indent=2) + '\n')
        self.persist()

    def persist(self):
        (self.directory / 'state.json').write_bytes(encoded(self.state()))

    def state(self):
        return {'settings': self.settings, 'records': self.records,
                'run_number': self.run_number, 'last_plan': self.last_plan,
                'jobs': list(self.spec.values()), 'events': self.events}

    async def calculate(self, key, run_id):
        if key not in SPEC:
            raise ValueError('No calculation registered for this job.')
        job = import_module(f'jobs.{key}.run')
        return await job.calculate(self, run_id)

    async def run(self, start='submission', scope='workflow'):
        if self.running:
            raise ValueError('An execution is already in progress.')
        self.running = True
        self.events = []
        try:
            plan = self.plan(start, scope)
            self.last_plan = plan
            self.run_number += 1
            run_id = f'Run {self.run_number:03d}'
            self.notify({'state':'plan', **plan, 'run_id':run_id})
            stages = [[key for key in stage if key in plan['run']] for stage in STAGES]
            stages = [keys for keys in stages if keys]
            stage_for = {key: index for index, keys in enumerate(stages) for key in keys}
            tasks = {}
            transfer_lock = asyncio.Lock()

            async def run_stage(index, keys):
                parents = {stage_for[parent] for key in keys for parent in SPEC[key]['parents']
                           if parent in stage_for and stage_for[parent] != index}
                await asyncio.gather(*(tasks[parent] for parent in parents))
                for handover in handover_groups(keys, plan['run']):
                    # Only transfers share this gate; independent reporting keeps
                    # running while a recipient waits for its input files.
                    async with transfer_lock:
                        if self.manual_transfer is None:
                            break
                        recipients = ' and '.join(SPEC[key]['title'] for key in handover['group'])
                        key = handover['group'][0]
                        self.record_event(key, 'handover',
                                          f'Updated inputs are ready for {recipients}. '
                                          'Click Confirm file transfer to continue.', **handover)
                        connected = await self.manual_transfer(handover)
                        await self.emit(key, 'received',
                                        f'File transfer confirmed for {recipients}.', **handover)
                        if connected:
                            self.manual_transfer = None
                for key in keys:
                    if self.before_job:
                        await self.before_job(key)
                for key in keys:
                    self.record_event(key, 'running', SPEC[key]['description'], group=keys)
                if self.pause:
                    await asyncio.sleep(self.pause)
                results = await asyncio.gather(
                    *(self.calculate(key, run_id) for key in keys), return_exceptions=True)
                failures = []
                for key, result in zip(keys, results):
                    try:
                        if isinstance(result, BaseException):
                            raise result
                        self.save(key, result, run_id)
                    except Exception as error:
                        self.records.pop(key, None)
                        self.persist()
                        await self.emit(key, 'failed', str(error))
                        failures.append(error)
                    else:
                        await self.emit(key, 'complete', SPEC[key]['title'] + ' complete.')
                if failures:
                    raise failures[0]
            for index, keys in enumerate(stages):
                tasks[index] = asyncio.create_task(run_stage(index, keys))
            outcomes = await asyncio.gather(*tasks.values(), return_exceptions=True)
            for outcome in outcomes:
                if isinstance(outcome, BaseException):
                    raise outcome
            self.persist()
            return {'run_id':run_id, **plan, **self.state()}
        finally:
            self.running = False

    def bundle(self):
        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, 'w', zipfile.ZIP_DEFLATED) as archive:
            files = [*ROOT.glob('workflow/*.py'), *ROOT.glob('workflow/*.sql'), *ROOT.glob('data/*')]
            files += list(ROOT.glob('tests/*.py'))
            files += list(ROOT.glob('cloud/*.py'))
            files += list(ROOT.glob('scripts/generate-data.py'))
            files += job_files()
            files += [ROOT / 'ADAPT.md', ROOT / 'cloud/README.md']
            files += [ROOT / name for name in ['run.py','verify.py','Makefile','Dockerfile','README.md','LICENSE','THIRD_PARTY.md','build-info.json'] if (ROOT / name).exists()]
            files += list(ROOT.glob('vendor/analysis/*'))
            checksums = {}
            for path in files:
                name = str(path.relative_to(ROOT)); data = path.read_bytes()
                archive.writestr(name, data); checksums[name] = digest(data)
            for path in self.directory.rglob('*'):
                if path.is_file():
                    name = 'reference/' + str(path.relative_to(self.directory))
                    data = path.read_bytes()
                    archive.writestr(name, data); checksums[name] = digest(data)
            job_target = (self.last_plan or {}).get('start') if (self.last_plan or {}).get('scope') == 'job' else None
            bundle_settings = dict(self.settings)
            if job_target:
                # Form changes made after execution do not change the saved job.
                bundle_settings = read_json(self.directory / 'state.json')['settings']
            if 'mse_buffered' in self.records:
                # A planned but unexecuted control change is not the setting of
                # the downloaded result. Historical records used the default.
                bundle_settings['mse_buffer'] = self.records['mse_buffered']['settings'].get(
                    'buffer', DEFAULTS['mse_buffer'])
            settings = encoded(bundle_settings)
            archive.writestr('settings.json', settings)
            checksums['settings.json'] = digest(settings)
            archive.writestr('SHA256SUMS.json', json.dumps(checksums, indent=2))
            run = 'python3 run.py --settings settings.json --output reproduced'
            check = 'python3 verify.py reference reproduced'
            note = ''
            if job_target:
                run += f' --from {job_target} --scope job'
                check += f' --job {job_target}'
                note = (f'This check compares only {job_target}. Other saved results retain their earlier '
                        'records and may use earlier inputs; they are not reproduced by this command.\n')
            archive.writestr('REPRODUCE.txt', f'Run: {run}\nCheck: {check}\n{note}'
                            'The same Python code runs in the browser and container. Software details '
                            'and original run identities are in reference/state.json.\n')
        return buffer.getvalue()
