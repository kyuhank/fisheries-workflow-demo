"""Execute selected jobs, verify saved inputs and preserve their original records."""
import asyncio
import hashlib
import io
import json
from pathlib import Path
import platform
import shutil
import shlex
import sqlite3
import sys
import zipfile

from . import reports
from .r_bridge import RBridge
from .quarto_reports import render_report
from .spec import DEFAULTS, SPEC, STAGES, active_spec, downstream, handover_groups
from .sources import SourceResolver
from .contracts import validate_transfer

ROOT = Path(__file__).resolve().parents[1]
FROZEN_SOURCE = 'data/frozen-source.json'
DATA_FILES = ('fishery.sqlite', 'submission.json', 'scenario.json', 'source-data.json',
              'generation.json', 'frozen-source.json')


def digest(data):
    return hashlib.sha256(data).hexdigest()


def encoded(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()


def read_json(path):
    return json.loads(path.read_text())


def job_files():
    """List job source files and reader guides."""
    return sorted(path for path in (ROOT / 'jobs').rglob('*')
                  if path.is_file() and path.suffix in ('.md', '.R', '.qmd'))


def calculation_files():
    """Shared calculation sources, job declarations and execution recipes."""
    return sorted([ROOT / 'workflow/jobs.json', ROOT / 'workflow/Makefile', ROOT / 'workflow/r_driver.R',
                   *(ROOT / 'workflow/r').glob('*.R')])


def source_payload(sources=None):
    """Canonical exact source closure used by run, page and release downloads."""
    sources = sources or SourceResolver(ROOT)
    files = [*ROOT.glob('workflow/*.py'), *ROOT.glob('workflow/*.sql'), *ROOT.glob('data/*'),
             *calculation_files(), *ROOT.glob('tests/*.py'), *ROOT.glob('tests/*.R'),
             *ROOT.glob('cloud/*.py'), *ROOT.glob('vendor/analysis/*')]
    files += job_files()
    files += [ROOT / name for name in ['run.py', 'verify.py', 'Makefile', 'Dockerfile', 'README.md',
              'LICENSE', 'THIRD_PARTY.md', 'build-info.json', 'ADAPT.md', 'cloud/README.md',
              'examples/analyst-repositories.yaml', 'scripts/generate-data.R', 'scripts/import-r-data.py',
              'scripts/hydrate-sources.py', 'scripts/check-multi-repository.py', 'scripts/MULTI_REPOSITORY.md']]
    result = {p.relative_to(ROOT).as_posix(): p.read_bytes() for p in files if p.is_file()}
    result.update(sources.archive_payload())
    if (ROOT / 'coordinator-origin.json').is_file():
        result['coordinator-origin.json'] = (ROOT / 'coordinator-origin.json').read_bytes()
    return result


class Workflow:
    def __init__(self, directory='runs', notify=None, pause=0, before_job=None,
                 manual_transfer=None, r_bridge=None, source_lock=None):
        self.directory = Path(directory)
        self.directory.mkdir(parents=True, exist_ok=True)
        self.notify = notify or (lambda event: None)
        self.pause = pause
        self.before_job = before_job
        self.manual_transfer = manual_transfer
        self.calculator = r_bridge or RBridge()
        self.sources = SourceResolver(ROOT, source_lock)
        if r_bridge is None and self.sources.multi_repository and not self.sources.coordinator_identity()['commit']:
            raise ValueError('Actual component execution requires a committed coordinator-origin.json; hydrate sources before running')
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
            if 'mortality_2' in previous.get('settings', {}):
                raise ValueError('This checkpoint uses the earlier age-model version. '
                                 'Keep its saved results and start a fresh v1.8 R session.')
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
        if candidate['growth_rate_2'] not in (0.25, 0.30, 0.35):
            raise ValueError('Select one of the supplied intrinsic-growth settings.')
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

    def transferred_output(self, parent):
        """Decode the same current producer bytes that were checksum-verified."""
        record = self.records.get(parent)
        if not record or record.get('signature') != self.signature(parent):
            raise ValueError('Transfer input stale or checksum mismatch: ' + parent)
        path = self.directory / parent / 'output.json'
        if not path.is_file():
            raise ValueError('Transfer input missing: ' + parent)
        data = path.read_bytes()
        if digest(data) != record.get('outputs', {}).get('output.json'):
            raise ValueError('Transfer input checksum mismatch: ' + parent)
        return json.loads(data)

    def job_settings(self, key):
        if key == 'submission':
            return {'last_year': self.settings['last_year']}
        if key == 'cpue_a':
            return {'min_hooks': self.settings['min_hooks_a']}
        if key in ('assessment_a2', 'assessment_b2'):
            return {'r': self.settings['growth_rate_2']}
        if key in ('assessment_a1', 'assessment_b1'):
            return {'r': 0.25}
        if key == 'mse_buffered':
            return {'buffer': self.settings['mse_buffer']}
        return {}

    def code_record(self, key):
        self.sources.verify()
        names = ['Makefile', 'workflow/Makefile', 'workflow/jobs.json', 'workflow/engine.py',
                 'workflow/spec.py', 'workflow/reports.py', 'workflow/r_bridge.py',
                 'workflow/r_driver.R', 'workflow/quarto_reports.py',
                 'workflow/sources.py', 'workflow/contracts.py']
        if key == 'extract':
            names += ['workflow/extract.sql', 'workflow/extract-catch.sql']
        files = {name: ROOT / name for name in names}
        files.update(self.sources.required_files(key))
        return {name: digest(path.read_bytes()) for name, path in files.items()}

    def signature(self, key):
        parents = {parent: {'signature': self.records.get(parent, {}).get('signature'),
                            'outputs': self.records.get(parent, {}).get('outputs')}
                   for parent in SPEC[key]['parents']}
        material = {'code': self.code_record(key), 'settings': self.job_settings(key),
                    'parents': parents, 'software': self.software()}
        if key == 'submission':
            material['data'] = {name: digest((ROOT / 'data' / name).read_bytes())
                                for name in DATA_FILES if (ROOT / 'data' / name).is_file()}
        return digest(encoded(material))

    def software(self):
        return {**self.calculator.software(),
                'python': platform.python_version(), 'platform': sys.platform,
                'runtime': 'Rscript (container)', 'adapter_runtime': 'CPython',
                'sqlite': sqlite3.sqlite_version}

    def valid(self, key):
        record = self.records.get(key)
        if not record or record['signature'] != self.signature(key):
            return False
        if self.sources.multi_repository:
            expected = self.sources.origin(key)
            actual = record.get('analysis_source', {})
            if any(actual.get(field) != expected[field] for field in ('repository', 'path', 'sha256')):
                return False
            if not isinstance(actual.get('commit'), str) or len(actual['commit']) != 40:
                return False
            for name, origin in self.sources.code_sources(key).items():
                saved = record.get('code_sources', {}).get(name, {})
                if any(saved.get(field) != origin[field] for field in ('repository', 'path', 'sha256')):
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

    def source_context(self):
        """Read source bytes; year selection and the QC example are R jobs."""
        if hasattr(self, 'hosted_data'):
            return {**json.loads(json.dumps(self.hosted_data)), 'submission': None}
        frozen = ROOT / FROZEN_SOURCE
        if frozen.is_file():
            return {**read_json(frozen), 'submission': None}
        with sqlite3.connect(f'file:{ROOT / "data/fishery.sqlite"}?mode=ro', uri=True) as db:
            db.row_factory = sqlite3.Row
            rows = [dict(r) for r in db.execute('SELECT * FROM sets ORDER BY year,set_id')]
            catch = [dict(r) for r in db.execute('SELECT * FROM removals ORDER BY year')]
        return {'sets': rows, 'catch': catch, 'submission': read_json(ROOT / 'data/submission.json')}

    def extracted_context(self):
        sql = (ROOT / 'workflow/extract.sql').read_text()
        catch_sql = (ROOT / 'workflow/extract-catch.sql').read_text()
        with sqlite3.connect(self.directory / 'database/snapshot.sqlite') as db:
            db.row_factory = sqlite3.Row
            return {'sets': [dict(r) for r in db.execute(sql)],
                    'catch': [dict(r) for r in db.execute(catch_sql)], 'sql': sql + '\n' + catch_sql}

    def store_snapshot(self, data):
        """Load rows accepted by R into the SQLite snapshot."""
        folder = self.directory / 'database'
        folder.mkdir(exist_ok=True)
        dbfile = folder / 'snapshot.sqlite'
        dbfile.unlink(missing_ok=True)
        with sqlite3.connect(dbfile) as db:
            db.execute('CREATE TABLE sets(set_id TEXT PRIMARY KEY,year INTEGER,vessel TEXT,hooks INTEGER CHECK(hooks>0),catch_n INTEGER CHECK(catch_n>=0))')
            db.execute('CREATE TABLE removals(year INTEGER PRIMARY KEY,catch_t REAL CHECK(catch_t>=0))')
            db.executemany('INSERT INTO sets VALUES(?,?,?,?,?)', [[row[name] for name in ('set_id','year','vessel','hooks','catch_n')] for row in data['sets']])
            db.executemany('INSERT INTO removals VALUES(?,?)', [[row['year'],row['catch_t']] for row in data['catch']])

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
        if self.sources.multi_repository:
            record['analysis_source'] = self.sources.origin(key)
            record['code_sources'] = self.sources.code_sources(key)
            for name, checksum in record['code'].items():
                if name not in record['code_sources']:
                    record['code_sources'][name] = {**self.sources.coordinator_identity(), 'path': name, 'sha256': checksum}
            for parent, details in record['inputs'].items():
                details['signature'] = self.records[parent]['signature']
                details['analysis_source'] = self.records[parent].get('analysis_source')
            transferred = validate_transfer(key, {p: self.output(p) for p in SPEC[key]['parents']}, self.records, self.settings)
            if transferred:
                record['input_contract'] = transferred
        if self.execution:
            record['execution'] = dict(self.execution)
        build = ROOT / 'build-info.json'
        if build.exists():
            record['source'] = read_json(build)
        if self.sources.multi_repository and self.sources.coordinator_identity()['commit']:
            record['source'] = self.sources.coordinator_identity()
        if self.execution.get('commit'):
            record['source'] = {'repository': 'https://github.com/' + self.execution['repository'],
                                'commit': self.execution['commit']}
        record['data_files'] = {name: digest((ROOT / 'data' / name).read_bytes())
                                for name in DATA_FILES if (ROOT / 'data' / name).is_file()}
        self.records[key] = record
        lineage = [{'job': SPEC[parent]['title'], **details} for parent, details in record['inputs'].items()]
        page = reports.output_page(SPEC[key], result, record, lineage)
        if self.sources.multi_repository and key.endswith('_report'):
            rendered = render_report(ROOT, key, result, record, folder, page, source_path=self.sources.job_path(key, 'report.qmd'))
        else:
            rendered = render_report(ROOT, key, result, record, folder, page)
        record['report_rendering'] = rendered
        record['outputs']['report.html'] = digest((folder / 'report.html').read_bytes())
        if rendered['quarto_executed']:
            for name in ('report.qmd', 'report-data.json'):
                record['outputs'][name] = digest((folder / name).read_bytes())
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
        self.sources.verify()
        if self.sources.multi_repository:
            for parent in SPEC[key]['parents']:
                if not self.valid(parent):
                    raise ValueError('Transfer input stale or checksum mismatch: ' + parent)
        load = self.transferred_output if self.sources.multi_repository else self.output
        parents = {parent: load(parent) for parent in SPEC[key]['parents']}
        if key == 'database':
            parents['submission'] = load('submission')
        context = {'key': key, 'settings': self.settings, 'job_settings': self.job_settings(key),
                   'run_id': run_id, 'parents': parents}
        if key in ('submission', 'qc'):
            context['source'] = self.source_context()
        if key == 'extract':
            context['extracted'] = self.extracted_context()
        if self.sources.multi_repository:
            validate_transfer(key, parents, self.records, self.settings)
        context['sources'] = self.sources.runtime(key)
        response = await self.calculator.calculate(context)
        result, effects = response['result'], response['effects']
        if effects:
            if key != 'qc' or set(effects) != {'resubmit_submission'}:
                raise ValueError('The R job requested undeclared workflow side effects.')
            await self.emit('qc', 'failed', 'Zero effort found. Return the record to the data provider.')
            await self.emit('submission', 'returned', 'The provider corrects the effort field.')
            await self.emit('submission', 'running', 'The provider resubmits the corrected records.', activity='resubmit')
            self.save('submission', effects['resubmit_submission'], run_id)
            await self.emit('submission', 'complete', 'Corrected submission received.')
            await self.emit('qc', 'running', 'Check the corrected submission.')
        if key == 'database':
            self.store_snapshot(parents['submission'])
        return result

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
                    # Gate transfers only; reporting continues while inputs await receipt.
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
            checksums = {}
            for name, data in source_payload(self.sources).items():
                if name == FROZEN_SOURCE and hasattr(self, 'hosted_data'):
                    continue
                archive.writestr(name, data)
                checksums[name] = digest(data)
            if hasattr(self, 'hosted_data'):
                # Freeze hosted inputs; the checkout may contain a different example.
                data = encoded(self.hosted_data)
                archive.writestr(FROZEN_SOURCE, data)
                checksums[FROZEN_SOURCE] = digest(data)
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
                # Use executed settings, not pending form changes; older records used defaults.
                bundle_settings['mse_buffer'] = self.records['mse_buffered']['settings'].get(
                    'buffer', DEFAULTS['mse_buffer'])
            settings = encoded(bundle_settings)
            archive.writestr('settings.json', settings)
            checksums['settings.json'] = digest(settings)
            archive.writestr('SHA256SUMS.json', json.dumps(checksums, indent=2))
            software = self.software()
            image = software['container']
            image_option = ' IMAGE=' + shlex.quote(image)
            if not self.sources.multi_repository:
                image_option += ' PAPER_SOURCE_MODE=monorepo'
            image_option += ' IMAGE_URL=' + shlex.quote(software.get('container_url', ''))
            pull = 'docker pull --platform linux/amd64 ' + image
            selected = ' JOB=' + shlex.quote(job_target) if job_target else ''
            run = 'make reproduce' + image_option + selected
            check = 'make compare' + image_option + selected
            note = ''
            if job_target:
                note = (f'This check compares only {job_target}. Other saved results retain their earlier '
                        'records and may use earlier inputs; they are not reproduced by this command.\n')
            archive.writestr('REPRODUCE.txt', f'Pull: {pull}\nRun: {run}\nCheck: {check}\n{note}'
                            'Run these commands from the extracted folder with Docker and Make available. '
                            'Make uses the recorded image, pulling it if needed, and starts the coordinator inside it; no host '
                            'Python, R or Quarto is needed. The coordinator checks inputs and schedules jobs; '
                            'workflow/Makefile launches the R calculations and three Quarto reports. The '
                            'offline page displays saved outputs. Container digest and original run identities '
                            'are in reference/state.json.\n')
        return buffer.getvalue()
