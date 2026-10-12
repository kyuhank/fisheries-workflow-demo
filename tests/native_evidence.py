"""Optional evidence capture around actual native adapters; never a test verdict.

PAPER_TEST_EVIDENCE selects a writable parent directory outside source Git.
Every invocation gets a fresh child directory, retaining failures and incomplete
ADAPTER_STARTED entries. The recorder neither submits nor retries a calculation.
"""
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import shutil
import tempfile
import time
from unittest.mock import patch

from workflow.engine import Workflow
from workflow.r_bridge import RBridge


def encoded(value):
    return json.dumps(value, separators=(',', ':'), allow_nan=False).encode()


def sha256(data):
    return hashlib.sha256(data).hexdigest()


class NativeEvidence:
    def __init__(self, label):
        self.root = None
        self.patches = []
        self.calculations = self.workflows = 0
        self.case = label + '.setUpClass'
        self.case_started = None
        destination = os.environ.get('PAPER_TEST_EVIDENCE')
        if not destination:
            return
        parent = Path(destination).resolve()
        parent.mkdir(parents=True, exist_ok=True)
        mode = os.environ.get('PAPER_SOURCE_MODE', 'unspecified')
        data = os.environ.get('PAPER_DATA_MODE', 'unspecified')
        self.root = Path(tempfile.mkdtemp(prefix=f'{label}-{mode}-{data}-', dir=parent))
        self.write('capture.json', {
            'schema_version': 1, 'type': 'native-test-evidence', 'label': label,
            'created_utc': datetime.now(timezone.utc).isoformat(),
            'source_mode': mode, 'data_mode': data,
            'declared_runtime_image': os.environ.get('PAPER_RUNTIME_IMAGE'),
            'execution_host': os.environ.get('PAPER_EXECUTION_HOST'),
            'compute_selection_receipt': os.environ.get('PAPER_COMPUTE_SELECTION_RECEIPT'),
            'github_run_id': os.environ.get('GITHUB_RUN_ID'),
            'github_commit': os.environ.get('GITHUB_SHA'),
            'parent_case': os.environ.get('PAPER_TEST_EVIDENCE_PARENT_CASE'),
            'test_verdict': 'Recorded by enclosing unittest/registered execution, not this recorder.',
            'timing_scope': 'Instrumented workflow wall time excludes final snapshot copy; '
                            'includes adapter journal I/O. Adapter time excludes its capture I/O. '
                            'This is not an uninstrumented product speed benchmark.',
            'response_representation': 'JSON of parsed R adapter envelope; raw R stdout is not captured.'})

    def write(self, name, value):
        if self.root:
            path = self.root / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(encoded(value) + b'\n')

    def event(self, value):
        if self.root:
            with (self.root / 'events.jsonl').open('ab') as stream:
                stream.write(encoded(value) + b'\n')

    def install(self):
        if not self.root:
            return
        original_calculate, original_run = RBridge.calculate, Workflow.run
        recorder = self

        async def calculate(bridge, context):
            recorder.calculations += 1
            identity = f'calculation-{recorder.calculations:04d}-{context["key"]}'
            # Match the Python request encoding handed to the actual R bridge.
            request = encoded(context)
            folder = recorder.root / identity
            folder.mkdir()
            (folder / 'request.json').write_bytes(request)
            source_files = [context.get('sources', {}).get('job')]
            source_files += context.get('sources', {}).get('libraries', [])
            hashes = {str(path): sha256(Path(path).read_bytes()) for path in source_files
                      if path and Path(path).is_file()}
            receipt = {'id': identity, 'case': recorder.case, 'job': context['key'],
                       'run_id': context.get('run_id'), 'request_sha256': sha256(request),
                       'source_files': hashes, 'state': 'ADAPTER_STARTED'}
            recorder.write(identity + '/receipt.json', receipt)
            recorder.event(receipt)
            started = time.perf_counter()
            try:
                response = await original_calculate(bridge, context)
            except BaseException as error:
                receipt.update(state='ADAPTER_FAILED', elapsed_seconds=time.perf_counter() - started,
                               error_type=type(error).__name__, error=str(error))
                recorder.write(identity + '/receipt.json', receipt)
                recorder.event(receipt)
                raise
            elapsed = time.perf_counter() - started
            content = encoded(response)
            (folder / 'response.json').write_bytes(content)
            receipt.update(state='ADAPTER_RETURNED', elapsed_seconds=elapsed,
                           response_sha256=sha256(content))
            recorder.write(identity + '/receipt.json', receipt)
            recorder.event(receipt)
            return response

        async def run(workflow, start='submission', scope='workflow'):
            recorder.workflows += 1
            identity = f'workflow-{recorder.workflows:04d}-{start}-{scope}'
            receipt = {'id': identity, 'case': recorder.case, 'start': start, 'scope': scope,
                       'settings': dict(workflow.settings), 'state': 'WORKFLOW_STARTED'}
            recorder.event(receipt)
            started = time.perf_counter()
            try:
                result = await original_run(workflow, start, scope)
            except BaseException as error:
                receipt.update(state='WORKFLOW_FAILED', elapsed_seconds=time.perf_counter() - started,
                               error_type=type(error).__name__, error=str(error))
                raise
            else:
                receipt.update(state='WORKFLOW_RETURNED', elapsed_seconds=time.perf_counter() - started,
                               run_id=result['run_id'], executed=result['run'], retained=result['retained'])
                return result
            finally:
                copied = time.perf_counter()
                folder = recorder.root / identity / 'outputs'
                shutil.copytree(workflow.directory, folder)
                manifest = {path.relative_to(folder).as_posix(): sha256(path.read_bytes())
                            for path in folder.rglob('*') if path.is_file()}
                recorder.write(identity + '/SHA256SUMS.json', manifest)
                receipt['snapshot_capture_seconds'] = time.perf_counter() - copied
                receipt['output_directory'] = identity + '/outputs'
                recorder.write(identity + '/receipt.json', receipt)
                recorder.event(receipt)

        for item in (patch.object(RBridge, 'calculate', calculate), patch.object(Workflow, 'run', run)):
            item.start()
            self.patches.append(item)

    def begin_case(self, name):
        self.case = name
        self.case_started = time.perf_counter()
        self.event({'case': name, 'state': 'TEST_ENTERED'})

    def end_case(self):
        if self.case_started is not None:
            self.event({'case': self.case, 'state': 'TEST_LEFT',
                        'elapsed_seconds': time.perf_counter() - self.case_started,
                        'test_verdict': 'See enclosing unittest result.'})
        self.case_started = None

    def close(self):
        self.write('inventory.json', {'adapter_calls_entered': self.calculations,
                                     'workflow_calls_entered': self.workflows,
                                     'coverage': 'This process only; child reproduction has its own capture directory.'})
        for item in reversed(self.patches):
            item.stop()


if __name__ == '__main__':
    # The Make entry forwards the ordinary run.py arguments without rewriting them.
    from run import main
    recorder = NativeEvidence('reproduction')
    recorder.install()
    try:
        main()
    finally:
        recorder.close()
