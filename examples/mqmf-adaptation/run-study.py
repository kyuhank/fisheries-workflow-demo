"""Offline bounded runner for source- and image-verified study execution."""
import argparse
import asyncio
import json
import math
import os
from pathlib import Path
import shutil
import signal
import time
import uuid

from workflow.engine import ROOT, digest, encoded, read_json
from workflow.offline import verify_image
from workflow.r_bridge import run_command
from workflow.study_adapter import StudyWorkflow, StudyBridge, TOLERANCE, RAW, verify_source, check_prepared

CASES = {'baseline': (3, 2), 'update': (2, 1), 'fresh': (3, 2), 'wrong-scale': (1, 0)}


def write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + '.tmp')
    temporary.write_bytes(encoded(value))
    temporary.replace(path)


def capture(folder, names=('cpue_b', 'cpue_a', 'cpue_summary')):
    return {key + '/' + name: digest((folder / key / name).read_bytes())
            for key in names for name in ('output.json', 'record.json', 'report.html')}


def near(a, b):
    return math.isclose(a, b, rel_tol=TOLERANCE['relative'], abs_tol=TOLERANCE['absolute'])


def compare_series(first, second):
    a, b = first['series'], second['series']
    if len(a) != 24 or len(b) != 24 or [row['year'] for row in a] != [row['year'] for row in b]:
        raise ValueError('Comparison needs identical 24 annual rows')
    differences = [abs(x['predicted_log_cpue'] - y['predicted_log_cpue']) for x, y in zip(a, b)]
    if any(not near(x['predicted_log_cpue'], y['predicted_log_cpue']) for x, y in zip(a, b)):
        raise ValueError('Frozen 1e-12 preservation rule failed')
    return {'values_compared': 24, 'max_absolute_difference': max(differences), 'passed': True}


def compare_rows(first, second):
    fields = ('observed_cpue', 'reference_predicted_log_cpue', 'active_predicted_log_cpue', 'log_difference', 'source_scale_ratio')
    a, b = first['rows'], second['rows']
    if len(a) != 24 or len(b) != 24 or [row['year'] for row in a] != [row['year'] for row in b]:
        raise ValueError('Consumer comparisons require equal 24 annual rows')
    if any(not near(x[field], y[field]) for x, y in zip(a, b) for field in fields):
        raise ValueError('Selective/fresh consumer comparison failed fixed tolerance')
    return {'numeric_values_compared': 120, 'passed': True, 'producing_records_compared_numerically': False}


class Runner:
    def __init__(self, output):
        self.started = time.monotonic()
        self.output = Path(output).resolve()
        if self.output == ROOT or ROOT in self.output.parents:
            raise ValueError('Results must be outside the read-only study source')
        self.output.mkdir(parents=True, exist_ok=True)
        self.source = verify_source()
        inspect = json.loads(os.environ.get('PAPER_OFFLINE_IMAGE_INSPECT', '{}'))
        self.runtime = verify_image(inspect, read_json(ROOT / 'runtime-preservation.json'))
        self.ledger_path = self.output / 'execution-ledger.json'
        self.ledger = read_json(self.ledger_path) if self.ledger_path.exists() else {
            'schema_version': 1, 'attempts': {}, 'elapsed_seconds': 0.0,
            'limits': {'steps': 9, 'external_function_calls': 5, 'total_seconds': 1200, 'per_R_call_seconds': 60}}
        self.prepared = self.output / 'prepared'
        self.selective = self.output / 'selective'
        self.execution_id = str(uuid.uuid4())
        def expired(signum, frame):
            raise TimeoutError('Total 1200-second study deadline exceeded; no retry')
        signal.signal(signal.SIGALRM, expired)
        signal.setitimer(signal.ITIMER_REAL, self.remaining())

    def remaining(self):
        seconds = 1200 - self.ledger['elapsed_seconds'] - (time.monotonic() - self.started)
        if seconds <= 0:
            raise TimeoutError('Total study deadline exhausted; no retry')
        return seconds

    def receipt(self, case):
        return {'actual_route': 'Local Docker', 'actual_client': 'offline study runner',
                'execution_id': self.execution_id, 'case': case,
                'reader': os.environ.get('STUDY_READER', 'unspecified reader'),
                'runtime_verification': self.runtime,
                'resources_declared_by_launcher': {'cpus': 2, 'memory_bytes': 4294967296,
                    'OMP_NUM_THREADS': 2, 'platform': 'linux/amd64', 'network': 'none',
                    'pull': 'never', 'source_mount': 'read-only'},
                'source_manifest_sha256': digest((ROOT / 'source-manifest.json').read_bytes()),
                'mapping_manifest_sha256': digest((self.prepared / 'mapping-manifest.json').read_bytes())}

    def prepare(self):
        if self.prepared.exists():
            raise ValueError('Prepared directory already exists; verify it without repeating preparation')
        self.remaining()
        software = StudyBridge().software()
        process = run_command(['Rscript', '--vanilla', 'prepare-inputs.R', str(ROOT / RAW),
                               str(self.prepared)], timeout=min(60, self.remaining()))
        if process.returncode:
            raise RuntimeError('Mapping preflight failed; no calculation launched: ' + process.stderr[-2000:])
        result = json.loads(process.stdout)
        if result['numeric_values'] != 72 or result['exact'] is not True or result['function_calls'] != 0:
            raise ValueError('Exact mapping receipt failed')
        receipt = {**result, 'raw_sha256': digest((ROOT / RAW).read_bytes()),
                   'helper_sha256': digest((ROOT / 'prepare-inputs.R').read_bytes()),
                   'study_helper_sha256': digest((ROOT / 'workflow/r/study.R').read_bytes()),
                   'files': {name: digest((self.prepared / name).read_bytes()) for name in ('abdat.csv', 'abdat.json')},
                   'software': software, 'runtime_verification': self.runtime,
                   'scope': 'Lossless preparation only; no simpspm invocation'}
        write(self.prepared / 'mapping-manifest.json', receipt)
        check_prepared(self.prepared)
        write(self.output / 'preflight.json', receipt)
        return receipt

    def reserve(self, case):
        if case in self.ledger['attempts']:
            raise ValueError('Case already attempted; no automatic or implicit retry: ' + case)
        steps, calls = CASES[case]
        previous = self.ledger['attempts'].values()
        if sum(item['reserved_steps'] for item in previous) + steps > 9:
            raise ValueError('Nine-step study cap exceeded')
        if sum(item['reserved_external_calls'] for item in self.ledger['attempts'].values()) + calls > 5:
            raise ValueError('Five-external-call study cap exceeded')
        self.ledger['attempts'][case] = {'status': 'STARTED', 'reserved_steps': steps,
                                       'reserved_external_calls': calls, 'execution_id': self.execution_id}
        write(self.ledger_path, self.ledger)

    async def case(self, case):
        check_prepared(self.prepared)
        workflow = None
        expected_steps, expected_calls = CASES[case]
        if case == 'baseline':
            if self.selective.exists():
                raise ValueError('Baseline destination must be fresh')
            workflow = StudyWorkflow(self.selective, self.prepared, execution=self.receipt(case))
            start, scope = 'cpue_a', 'workflow'
            expected = ['cpue_b', 'cpue_a', 'cpue_summary']
        elif case == 'update':
            if self.ledger['attempts'].get('baseline', {}).get('status') != 'COMPLETE':
                raise ValueError('Update requires the completed baseline')
            before = capture(self.selective, ('cpue_b',))
            baseline_active = read_json(self.selective / 'cpue_a/record.json')
            workflow = StudyWorkflow(self.selective, self.prepared, active='revised', execution=self.receipt(case))
            start, scope, expected = 'cpue_a', 'workflow', ['cpue_a', 'cpue_summary']
        elif case == 'fresh':
            if self.ledger['attempts'].get('update', {}).get('status') != 'COMPLETE':
                raise ValueError('Fresh comparison requires completed selective update')
            folder = self.output / 'fresh'
            if folder.exists():
                raise ValueError('Fresh destination already exists')
            workflow = StudyWorkflow(folder, self.prepared, active='revised', execution=self.receipt(case))
            start, scope = 'cpue_a', 'workflow'
            expected = ['cpue_b', 'cpue_a', 'cpue_summary']
        else:
            if self.ledger['attempts'].get('update', {}).get('status') != 'COMPLETE':
                raise ValueError('Wrong-scale fixture requires completed selective update')
            folder = self.output / 'fixture'
            if folder.exists():
                raise ValueError('Fixture destination already exists')
            accepted_before = capture(self.selective)
            shutil.copytree(self.selective, folder, ignore=shutil.ignore_patterns('study-bundle.zip'))
            fixture_before = capture(folder)
            workflow = StudyWorkflow(folder, self.prepared, active='revised', execution=self.receipt(case), fixture=True)
            start, scope, expected = 'cpue_summary', 'job', ['cpue_summary']
        plan = workflow.plan(start, scope)
        if plan['run'] != expected:
            raise ValueError('Unexpected original scheduler selection: ' + repr(plan))
        self.reserve(case)
        try:
            if case == 'wrong-scale':
                try:
                    await asyncio.wait_for(workflow.run(start, scope), self.remaining())
                except ValueError as error:
                    if 'Prediction contract requires natural log and MQMF source scale' not in str(error):
                        raise
                    if capture(self.selective) != accepted_before or capture(folder) != fixture_before:
                        raise ValueError('Fixture changed prior accepted output/record bytes')
                    result = {'status': 'EXPECTED_REJECTION', 'error': str(error),
                              'fixture_scope': 'In-memory linear conversion after reading genuine saved producer bytes; receiving contract only',
                              'native_upstream_result_produced': False, 'consumer_R_invoked': False,
                              'new_consumer_output_accepted': False, 'accepted_bytes_preserved': accepted_before}
                else:
                    raise ValueError('Wrong-scale fixture was accepted')
            else:
                state = await asyncio.wait_for(workflow.run(start, scope), self.remaining())
                result = {'status': 'COMPLETE', 'run_id': state['run_id'], 'plan': plan,
                          'output_checksums': capture(workflow.directory)}
                if case == 'baseline':
                    result['native_adapter_comparison'] = compare_series(workflow.output('cpue_b'), workflow.output('cpue_a'))
                    checkpoint = self.output / 'checkpoints/baseline'
                    checkpoint.parent.mkdir(exist_ok=True)
                    shutil.copytree(self.selective, checkpoint)
                elif case == 'update':
                    if capture(self.selective, ('cpue_b',)) != before:
                        raise ValueError('Retained native reference bytes changed')
                    updated_active = workflow.records['cpue_a']
                    if baseline_active['code'] != updated_active['code']:
                        raise ValueError('Parameter-only update changed code bytes')
                    if workflow.records['cpue_summary']['inputs']['cpue_b']['run_id'] != 'Run 001' or workflow.records['cpue_summary']['inputs']['cpue_a']['run_id'] != 'Run 002':
                        raise ValueError('Mixed actual producer run links were relabelled')
                    result.update(reference_bytes_preserved=before, code_changed=False,
                                  changed_parameter='r: 0.4 -> 0.35', actual_producer_links=workflow.records['cpue_summary']['inputs'])
                else:
                    result['selective_fresh_predictions'] = compare_series(
                        read_json(self.selective / 'cpue_a/output.json'), workflow.output('cpue_a'))
                    result['selective_fresh_consumer'] = compare_rows(
                        read_json(self.selective / 'cpue_summary/output.json'), workflow.output('cpue_summary'))
                    result['reference_numeric_agreement'] = compare_series(
                        read_json(self.selective / 'cpue_b/output.json'), workflow.output('cpue_b'))
                workflow.bundle()
            if len(workflow.invocations) != expected_steps or sum(item['external_function_calls'] for item in workflow.invocations) != expected_calls:
                raise ValueError('Invocation bound differs from frozen case')
            result.update(invocations=workflow.invocations, step_invocations=expected_steps,
                          external_function_calls=expected_calls, tolerance=TOLERANCE,
                          scientific_validity_established=False)
            write(self.output / ('reports/' + case + '.json'), result)
            self.ledger['attempts'][case].update(status='COMPLETE', report='reports/' + case + '.json',
                                                actual_steps=expected_steps, external_function_calls=expected_calls)
            write(self.ledger_path, self.ledger)
            return result
        except BaseException as error:
            self.ledger['attempts'][case].update(status='FAILED', error=str(error),
                invocations=[] if workflow is None else workflow.invocations,
                actual_external_completion='unknown for a failed R call; no replay')
            write(self.ledger_path, self.ledger)
            raise

    def finish(self):
        signal.setitimer(signal.ITIMER_REAL, 0)
        self.ledger['elapsed_seconds'] += time.monotonic() - self.started
        write(self.ledger_path, self.ledger)


async def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=('prepare', 'baseline', 'update', 'fresh', 'wrong-scale', 'all', 'check'))
    parser.add_argument('--output', default='/outputs')
    args = parser.parse_args()
    runner = Runner(args.output)
    try:
        if args.command == 'check':
            result = {'status': 'SOURCE_AND_LOCAL_IMAGE_VERIFIED', 'runtime': runner.runtime,
                      'manifest_sha256': digest((ROOT / 'source-manifest.json').read_bytes()),
                      'calculation_performed': False}
            if runner.prepared.exists():
                result['mapping'] = check_prepared(runner.prepared)
        elif args.command == 'prepare':
            result = runner.prepare()
        elif args.command == 'all':
            if not runner.prepared.exists():
                runner.prepare()
            result = {case: await runner.case(case) for case in CASES}
        else:
            result = await runner.case(args.command)
        print(json.dumps(result, indent=2, allow_nan=False))
    finally:
        runner.finish()


if __name__ == '__main__':
    asyncio.run(main())
