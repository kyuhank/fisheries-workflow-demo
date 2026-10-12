"""Bounded GPL-3 study adapter; scheduling/reuse are inherited unchanged."""
import asyncio
import copy
import html
import json
import math
import os
from pathlib import Path
import platform
import shutil
import sys
import zipfile

from .engine import Workflow, ROOT, digest, encoded, read_json
from .r_bridge import RBridge, make_command, process_environment, kill_process_group
from .spec import SPEC
from .reports import STYLE, plot, table

IMAGE = 'ghcr.io/pacificcommunity/fisheries-workflow@sha256:9dea950a713b87daad728517138bcb664a151f0f5b44a1d5370623734a5bca9d'
TOLERANCE = {'absolute': 1e-12, 'relative': 1e-12}
RAW = 'external/MQMF/data/abdat.RData'
FUNCTION = 'external/MQMF/R/spm.r'
CORE = ('workflow/__init__.py', 'workflow/engine.py', 'workflow/spec.py', 'workflow/sources.py',
        'workflow/contracts.py', 'workflow/reports.py', 'workflow/quarto_reports.py',
        'workflow/r_bridge.py', 'workflow/r_driver.R', 'workflow/Makefile',
        'workflow/r/common.R', 'workflow/jobs.json', 'workflow/study_adapter.py',
        'workflow/r/study.R', 'prepare-inputs.R', 'run-study.py', 'study-case.json',
        'workflow/offline.py', 'runtime-preservation.json', 'upstream/origins.json', 'study.sh')


def verify_source():
    manifest = read_json(ROOT / 'source-manifest.json')
    for name, pin in manifest['files'].items():
        path = ROOT / name
        if path.is_symlink() or not path.is_file() or digest(path.read_bytes()) != pin['sha256']:
            raise ValueError('Frozen study byte mismatch: ' + name)
    return manifest


def check_prepared(directory):
    directory = Path(directory).resolve()
    receipt = read_json(directory / 'mapping-manifest.json')
    if receipt['numeric_values'] != 72 or receipt['exact'] is not True:
        raise ValueError('Missing exact 72-value mapping preflight')
    if receipt['raw_sha256'] != digest((ROOT / RAW).read_bytes()):
        raise ValueError('Prepared raw data differs from frozen source')
    if receipt['helper_sha256'] != digest((ROOT / 'prepare-inputs.R').read_bytes()):
        raise ValueError('Prepared mapping helper differs')
    if receipt['study_helper_sha256'] != digest((ROOT / 'workflow/r/study.R').read_bytes()):
        raise ValueError('Prepared receiving helper differs')
    for name in ('abdat.csv', 'abdat.json'):
        if digest((directory / name).read_bytes()) != receipt['files'][name]:
            raise ValueError('Prepared mapping bytes differ: ' + name)
    return receipt


def numeric(value):
    return type(value) in (int, float) and math.isfinite(value)


def check_prediction(value, key, expected_producer):
    expected = {'schema_version': 1, 'quantity': 'predicted_cpue',
                'transformation': 'natural_log', 'numerical_scale': 'MQMF-abdat-source-scale',
                'physical_unit': 'unspecified',
                'normalisation': 'unspecified; none applied by study', 'catch_unit': 'tonnes'}
    if any(value.get(name) != wanted for name, wanted in expected.items()):
        raise ValueError('Prediction contract requires natural log and MQMF source scale: ' + key)
    if value.get('producer') != expected_producer:
        raise ValueError('Actual producer identity mismatch: ' + key)
    producer = expected_producer
    if producer.get('job') != key or not producer.get('run_id') or len(producer.get('signature', '')) != 64:
        raise ValueError('Missing actual producer identity: ' + key)
    series = value.get('series')
    if not isinstance(series, list) or len(series) != 24:
        raise ValueError('Require 24 prediction rows: ' + key)
    if [row.get('year') for row in series] != list(range(1985, 2009)):
        raise ValueError('Require equal ordered consecutive years 1985 to 2008: ' + key)
    if any(not numeric(row.get('predicted_log_cpue')) for row in series):
        raise ValueError('Require finite log predictions: ' + key)
    observed_contract = {'quantity': 'observed_cpue', 'transformation': 'linear',
                         'numerical_scale': 'MQMF-abdat-source-scale', 'physical_unit': 'unspecified'}
    if value.get('observed_contract') != observed_contract:
        raise ValueError('Observed CPUE requires its linear source-scale contract: ' + key)
    if any(not numeric(row.get('observed_cpue')) or row['observed_cpue'] <= 0 for row in series):
        raise ValueError('Require finite positive observed CPUE: ' + key)


class StudyBridge(RBridge):
    """Same original JSON/Make/R driver with the frozen 60-second call bound."""
    def software(self):
        if self.require_container() != IMAGE:
            raise ValueError('Only the protected SPC digest is allowed')
        if os.environ.get('OMP_NUM_THREADS') != '2':
            raise ValueError('Require OMP_NUM_THREADS=2')
        return super().software()

    async def calculate(self, context):
        self.software()
        process = await asyncio.create_subprocess_exec(
            *make_command('calculate'), cwd=ROOT, env=process_environment(),
            stdin=asyncio.subprocess.PIPE, stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE, start_new_session=True)
        try:
            stdout, stderr = await asyncio.wait_for(process.communicate(encoded(context)), 60)
        except BaseException:
            kill_process_group(process)
            await process.communicate()
            raise
        if process.returncode:
            raise RuntimeError('R job ' + context['key'] + ' failed: ' + stderr.decode()[-2000:])
        value = json.loads(stdout)
        if set(value) != {'result', 'effects'} or not isinstance(value['result'], dict) or value['effects'] != {}:
            raise ValueError('Require result object and no workflow effects')
        encoded(value)
        return value


class StudyWorkflow(Workflow):
    """Three registered slots; base Workflow.plan/run/valid are not replaced."""
    def __init__(self, directory, prepared, active='baseline', execution=None, fixture=False):
        self.manifest = verify_source()
        self.prepared = Path(prepared).resolve()
        self.mapping = check_prepared(self.prepared)
        super().__init__(directory=directory, r_bridge=StudyBridge(), source_lock=False)
        self.configure({'active_parameters': 'parameters/active-' + active + '.json'})
        self.execution = execution or {}
        self.fixture = fixture
        self.invocations = []

    def configure(self, settings):
        candidate = {**self.settings, **settings}
        if set(candidate) != {'last_year', 'active_parameters', 'mse'} or candidate['last_year'] != 2008 or candidate['mse'] is not False:
            raise ValueError('Study requires snapshot 2008 and the three-node graph')
        if candidate['active_parameters'] not in ('parameters/active-baseline.json', 'parameters/active-revised.json'):
            raise ValueError('Select a frozen active parameter file')
        self.settings = candidate

    def parameter_file(self, key):
        return self.settings['active_parameters'] if key == 'cpue_a' else 'parameters/reference.json'

    def job_settings(self, key):
        return read_json(ROOT / self.parameter_file(key)) if key != 'cpue_summary' else dict(TOLERANCE)

    def code_record(self, key):
        verify_source()
        names = [*CORE, 'jobs/' + key + '/run.R']
        if key != 'cpue_summary':
            names.append(FUNCTION)
        return {name: digest((ROOT / name).read_bytes()) for name in names}

    def file_inputs(self, key):
        if key == 'cpue_summary':
            return {}
        result = {RAW: ROOT / RAW, self.parameter_file(key): ROOT / self.parameter_file(key)}
        if key == 'cpue_a':
            result.update({'mapped/' + name: self.prepared / name
                           for name in ('abdat.csv', 'abdat.json', 'mapping-manifest.json')})
        return result

    def signature(self, key):
        material = {'code': self.code_record(key), 'settings': self.job_settings(key),
                    'file_inputs': {name: digest(path.read_bytes()) for name, path in self.file_inputs(key).items()},
                    'parents': {parent: {'signature': self.records.get(parent, {}).get('signature'),
                                         'outputs': self.records.get(parent, {}).get('outputs')}
                                for parent in SPEC[key]['parents']}, 'software': self.software()}
        return digest(encoded(material))

    def software(self):
        return {**self.calculator.software(), 'python': platform.python_version(),
                'platform': sys.platform, 'runtime': 'Rscript in protected SPC container',
                'adapter_runtime': 'CPython', 'study': 'MQMF unchanged simpspm adoption'}

    def producer(self, key, run_id):
        origins = read_json(ROOT / 'upstream/origins.json')
        name = 'jobs/' + key + '/run.R'
        return {'job': key, 'run_id': run_id, 'signature': self.signature(key),
                'execution_id': self.execution.get('execution_id'),
                'case': self.execution.get('case'),
                'run_directory': self.directory.as_posix(),
                'wrapper': {'kind': 'local study file bytes', 'commit': None, 'repository': None,
                            'path': name, 'sha256': digest((ROOT / name).read_bytes()),
                            'manifest_sha256': digest((ROOT / 'source-manifest.json').read_bytes())},
                'external_function': {**origins['external'][FUNCTION], 'function': 'simpspm'},
                'raw_input': origins['external'][RAW],
                'parameter_file': {'path': self.parameter_file(key),
                                   'sha256': digest((ROOT / self.parameter_file(key)).read_bytes())}}

    def input_link(self, parent):
        record = self.records[parent]
        record_path = self.directory / parent / 'record.json'
        if not record_path.is_file() or read_json(record_path) != record:
            raise ValueError('Saved producing record differs from checkpoint: ' + parent)
        for name, pin in record.get('source_closure', {}).items():
            path = self.directory / pin['path']
            if path.is_symlink() or not path.is_file() or digest(path.read_bytes()) != pin['sha256']:
                raise ValueError('Actual producer source closure missing or changed: ' + parent + '/' + name)
        if not record.get('source_closure'):
            raise ValueError('Actual producer source closure missing: ' + parent)
        return {'run_id': record['run_id'], 'signature': record['signature'],
                'record_path': parent + '/record.json', 'record_checksum': digest(record_path.read_bytes()),
                'checksum': record['outputs']['output.json'], 'producer': record['producer'],
                'settings': record['settings'], 'file_inputs': record['file_inputs'],
                'source_closure': record['source_closure']}

    async def calculate(self, key, run_id):
        verify_source()
        check_prepared(self.prepared)
        self.invocations.append({'job': key, 'run_id': run_id, 'fixture': self.fixture,
                                 'external_function_calls': int(key != 'cpue_summary')})
        parents = {parent: self.transferred_output(parent) for parent in SPEC[key]['parents']}
        producers = {parent: self.records[parent]['producer'] for parent in parents}
        links = {parent: self.input_link(parent) for parent in parents}
        if self.fixture:
            if key != 'cpue_summary':
                raise ValueError('Controlled fixture may invoke only the consumer')
            # In-memory receiving-contract fixture, not a newly produced scientific result.
            parents = copy.deepcopy(parents)
            parents['cpue_a']['transformation'] = 'linear'
            for row in parents['cpue_a']['series']:
                row['predicted_log_cpue'] = math.exp(row['predicted_log_cpue'])
        for parent, value in parents.items():
            check_prediction(value, parent, producers[parent])
        if parents and [row['observed_cpue'] for row in parents['cpue_b']['series']] != [row['observed_cpue'] for row in parents['cpue_a']['series']]:
            raise ValueError('Producer observations must agree exactly in source scale')
        context = {'key': key, 'run_id': run_id, 'settings': self.settings,
                   'job_settings': self.job_settings(key), 'parents': parents,
                   'input_producers': producers, 'input_links': links,
                   'sources': {'job': str(ROOT / ('jobs/' + key + '/run.R')),
                               'libraries': [str(ROOT / 'workflow/r/common.R'), str(ROOT / 'workflow/r/study.R')]},
                   'study': {'raw_path': str(ROOT / RAW), 'function_path': str(ROOT / FUNCTION),
                             'parameter_path': str(ROOT / self.parameter_file(key)),
                             'csv_path': str(self.prepared / 'abdat.csv'),
                             'json_path': str(self.prepared / 'abdat.json'), 'tolerance': TOLERANCE}}
        if key != 'cpue_summary':
            context['producer'] = self.producer(key, run_id)
        response = await self.calculator.calculate(context)
        value = response['result']
        if key != 'cpue_summary':
            check_prediction(value, key, context['producer'])
        return value

    def save(self, key, result, run_id):
        folder = self.directory / key
        folder.mkdir(exist_ok=True)
        closure = self.directory / 'closure' / run_id.replace(' ', '_') / key
        sources = {name: ROOT / name for name in self.code_record(key)}
        sources['source-manifest.json'] = ROOT / 'source-manifest.json'
        sources.update(self.file_inputs(key))
        source_closure = {}
        for name, path in sources.items():
            destination = closure / name
            destination.parent.mkdir(parents=True, exist_ok=True)
            data = path.read_bytes()
            destination.write_bytes(data)
            source_closure[name] = {'path': destination.relative_to(self.directory).as_posix(),
                                    'sha256': digest(data), 'bytes': len(data)}
        output_bytes = encoded(result)
        record = {'schema_version': 1, 'job': key, 'owner': SPEC[key]['owner'], 'run_id': run_id,
                  'signature': self.signature(key), 'settings': self.job_settings(key), 'snapshot': 2008,
                  'code': self.code_record(key), 'software': self.software(),
                  'file_inputs': {name: digest(path.read_bytes()) for name, path in self.file_inputs(key).items()},
                  'source_closure': source_closure,
                  'inputs': {parent: self.input_link(parent) for parent in SPEC[key]['parents']},
                  'execution': self.execution, 'source': {'kind': 'local study manifest',
                     'repository': None, 'commit': None,
                     'manifest_sha256': digest((ROOT / 'source-manifest.json').read_bytes())},
                  'original_orchestrator': {'repository': 'https://github.com/kyuhank/fisheries-workflow-demo',
                     'commit': '819c67034625b9a30b4196fd5ec17b0c74f60ba7',
                     'scope': 'unchanged copied core; separate declarations and adapter'},
                  'outputs': {'output.json': digest(output_bytes)},
                  'log': [event['message'] for event in self.events if event['job'] == key]}
        if key != 'cpue_summary':
            record['producer'] = result['producer']
        page = '<!doctype html><html lang="en-NZ"><meta charset="utf-8">'
        page += '<meta name="viewport" content="width=device-width,initial-scale=1">'
        page += '<title>' + html.escape(SPEC[key]['title']) + '</title><style>' + STYLE + '</style><body>'
        page += '<h1>' + html.escape(SPEC[key]['title']) + '</h1>'
        if key == 'cpue_summary':
            rows = result['rows']
            page += '<p>Compare the active MQMF prediction with its direct native reference.</p>'
            page += '<p class="feedback-flow">Two saved predictions → check scale and producer → annual comparison</p>'
            series = {'Observed': [{'year': row['year'], 'cpue': row['observed_cpue']} for row in rows]}
            for label, field in [('Reference', 'reference_predicted_log_cpue'), ('Active', 'active_predicted_log_cpue')]:
                series[label] = [{'year': row['year'], 'cpue': math.exp(row[field])} for row in rows]
            columns = [('year', 'Year'), ('observed_cpue', 'Observed CPUE'),
                       ('reference_predicted_log_cpue', 'Reference ln CPUE'),
                       ('active_predicted_log_cpue', 'Active ln CPUE'),
                       ('log_difference', 'Log difference'), ('source_scale_ratio', 'Active / reference')]
            page += plot(series, 'cpue', 'CPUE on the original numerical scale; physical unit unspecified', points=('Observed',))
            if result.get('baseline_preservation') is True:
                page += '<p class="note">The mapped and direct predictions agree within the recorded tolerance.</p>'
            elif result.get('perturbation_detectable') is True:
                page += '<p class="note">Changing the active growth setting changed the conditional predictions.</p>'
            page += '<details><summary>All annual comparisons</summary>' + table(rows, columns) + '</details>'
        else:
            rows = result['series']
            page += '<p>Predict CPUE with the unchanged MQMF routine and supplied teaching parameters.</p>'
            page += '<p class="feedback-flow">' + html.escape(result['input_route'])
            page += ' → unchanged simpspm() → annual log predictions</p>'
            parameters = result['parameters']
            page += '<p>Fixed growth: ' + str(parameters['r']) + ' per year; carrying capacity: '
            page += str(parameters['K']) + ' tonnes; initial biomass: ' + str(parameters['Binit']) + ' tonnes.</p>'
            series = {'Observed': [{'year': row['year'], 'cpue': row['observed_cpue']} for row in rows],
                      'Predicted': [{'year': row['year'], 'cpue': math.exp(row['predicted_log_cpue'])} for row in rows]}
            page += plot(series, 'cpue', 'CPUE on the original numerical scale; physical unit unspecified', points=('Observed',))
            page += '<details><summary>All annual predictions</summary>' + table(rows, [
                ('year', 'Year'), ('observed_cpue', 'Observed CPUE'),
                ('predicted_log_cpue', 'Predicted ln CPUE')]) + '</details>'
            page += '<details><summary>Calculation assumptions</summary><pre>'
            page += html.escape(json.dumps(result['semantics'], indent=2)) + '</pre></details>'
        page += '<p>Predictions are exponentiated only for this plot; saved predictions retain their natural-log scale. '
        page += 'The observed CPUE unit is undocumented. This example does not reproduce CPUE standardisation, '
        page += 'fit population parameters, validate a stock assessment or provide management advice.</p>'
        page += '<p class="muted">Produced in ' + html.escape(run_id) + '.</p>'
        page += '<details><summary>Producer records and exact source closure</summary><pre>'
        page += html.escape(json.dumps(record, indent=2)) + '</pre></details></body></html>'
        report_bytes = page.encode()
        record['outputs']['report.html'] = digest(report_bytes)
        record['report_rendering'] = {'engine': 'study HTML', 'source': 'workflow/study_adapter.py', 'quarto_executed': False}
        for name, data in (('output.json', output_bytes), ('report.html', report_bytes),
                           ('record.json', (json.dumps(record, indent=2, allow_nan=False) + '\n').encode())):
            temporary = folder / (name + '.tmp')
            temporary.write_bytes(data)
            temporary.replace(folder / name)
        self.records[key] = record
        self.persist()

    def bundle(self):
        """Exact source, raw/helper/parameter/mapping bytes plus real result records."""
        destination = self.directory / 'study-bundle.zip'
        with zipfile.ZipFile(destination, 'w', zipfile.ZIP_DEFLATED) as archive:
            checksums = {}
            for path in sorted(ROOT.rglob('*')):
                if path.is_file() and '__pycache__' not in path.parts:
                    name = 'source/' + path.relative_to(ROOT).as_posix()
                    data = path.read_bytes()
                    archive.writestr(name, data)
                    checksums[name] = digest(data)
            for path in sorted(self.prepared.iterdir()):
                if path.is_file():
                    name = 'prepared/' + path.name
                    data = path.read_bytes()
                    archive.writestr(name, data)
                    checksums[name] = digest(data)
            for path in sorted(self.directory.rglob('*')):
                if path.is_file() and path != destination:
                    name = 'results/' + path.relative_to(self.directory).as_posix()
                    data = path.read_bytes()
                    archive.writestr(name, data)
                    checksums[name] = digest(data)
            archive.writestr('SHA256SUMS.json', json.dumps(checksums, indent=2) + '\n')
        return destination
