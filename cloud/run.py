"""Run the preserved calculations on GitHub, with hosted inputs and event records."""
import asyncio
import base64
from concurrent.futures import ProcessPoolExecutor
from http.client import IncompleteRead
import io
import json
import multiprocessing
import os
from pathlib import Path
import sys
import time
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError
import uuid
import zipfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from workflow.engine import Workflow, digest, encoded
from workflow.spec import SPEC, STAGES

API = 'https://gvunwnpsfmylmqfqowzp.supabase.co/functions/v1/paper-api'
REQUEST = str(uuid.UUID(os.environ['PAPER_REQUEST_ID']))
_token, _expires = '', 0
PARALLEL_JOBS = {key for stage in STAGES if len(stage) > 1 for key in stage}


def calculate_independent_job(directory, key, settings, run_id):
    if key not in PARALLEL_JOBS:
        raise ValueError('This job requires the workflow coordinator.')
    runner = Workflow(directory)
    runner.configure(settings)
    return asyncio.run(runner.calculate(key, run_id))


class TemporaryAPIError(RuntimeError):
    """A transient service failure; calculation status can wait for reconnection."""


def api(path, body=None):
    global _token, _expires
    if body is not None and path in ('event', 'finish'):
        body = {'operation_id': str(uuid.uuid4()), **body}
    payload = json.dumps(body).encode() if body is not None else None
    for attempt in range(3):
        identity = False
        try:
            if time.time() >= _expires:
                identity = True
                url = os.environ['ACTIONS_ID_TOKEN_REQUEST_URL'] + '&audience=fisheries-paper-demo'
                request = Request(url, headers={'Authorization': 'Bearer ' + os.environ['ACTIONS_ID_TOKEN_REQUEST_TOKEN']})
                with urlopen(request, timeout=30) as response:
                    _token = json.load(response)['value']
                _expires = time.time() + 240
            identity = False
            request = Request(API + '/runner/' + path + '?request=' + REQUEST,
                              data=payload, headers={'Authorization': 'Bearer ' + _token,
                                                     'Content-Type': 'application/json'})
            with urlopen(request, timeout=30) as response:
                return json.load(response)
        except HTTPError as error:
            try:
                message = json.load(error).get('error', 'Request rejected.')
            except (ValueError, AttributeError):
                message = 'Request rejected.'
            # Older API deployments reported a database timeout as HTTP 400.
            legacy = message == 'The database connection was interrupted.' or any(
                message == f'The database request could not be completed (HTTP {code}).'
                for code in (429, 500, 502, 503, 504))
            transient = error.code in (408, 429, 500, 502, 503, 504) or (
                not identity and error.code == 400 and legacy)
            if identity:
                message = 'Runner identity request failed.'
            failure = f'{path}: HTTP {error.code}: {str(message)[:240]}'
            if not transient:
                raise RuntimeError(failure) from None
        except (URLError, TimeoutError, ConnectionError, IncompleteRead, json.JSONDecodeError):
            failure = f'{path}: The service connection was interrupted.'
        if attempt == 2:
            raise TemporaryAPIError(failure) from None
        time.sleep(.5 * 2 ** attempt)


class EventDelivery:
    """Keep immutable event snapshots in order across temporary service failures."""
    def __init__(self):
        self.pending = []
        self.retry_at = 0

    def publish(self, body):
        self.pending.append(json.loads(json.dumps({'operation_id': str(uuid.uuid4()), **body})))
        self.flush()

    def flush(self, required=False):
        if not required and time.monotonic() < self.retry_at:
            return
        while self.pending:
            try:
                api('event', self.pending[0])
            except TemporaryAPIError:
                self.retry_at = time.monotonic() + 30
                if required:
                    raise
                print('Status delivery delayed; calculations and records continue locally.', flush=True)
                return
            self.pending.pop(0)
        self.retry_at = 0


def restore(encoded, directory):
    if not encoded:
        return
    with zipfile.ZipFile(io.BytesIO(base64.b64decode(encoded))) as archive:
        for member in archive.infolist():
            path = Path(member.filename)
            if path.is_absolute() or '..' in path.parts or member.file_size > 8_000_000:
                raise ValueError('Invalid preserved file.')
            archive.extract(member, directory)


def checkpoint(directory):
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, 'w', zipfile.ZIP_DEFLATED) as archive:
        for path in directory.rglob('*'):
            if path.is_file():
                archive.write(path, str(path.relative_to(directory)))
    return base64.b64encode(buffer.getvalue()).decode()


class HostedWorkflow(Workflow):
    def __init__(self, context):
        self.context = context
        self.hosted_data = api('data')
        self.transfer_count = 0
        self.delivery = EventDelivery()
        super().__init__('/tmp/paper-results', notify=self.publish, pause=1,
                         manual_transfer=self.handover if context['handover'] == 'manual' else None)
        self.pool = None
        self.execution = {'provider': 'GitHub Actions', 'repository': 'kyuhank/fisheries-workflow-demo',
                          'commit': context['commit_sha'], 'github_run': context['github_run'],
                          'container': 'ghcr.io/pacificcommunity/cpue-workshop@sha256:17b03d6e06da229b17524997d8a3fc8eb5f8f25233894b5ab99f89109b3890c5',
                          'data_source': 'Supabase PostgreSQL: fixed synthetic records',
                          'data_checksum': digest(encoded(self.hosted_data))}
        self.configure({'mse': False, **context['settings']})

    def code_record(self, key):
        return {**super().code_record(key), 'cloud/run.py': digest(Path(__file__).read_bytes())}

    def signature(self, key):
        value = super().signature(key)
        if key == 'submission':
            return digest(encoded({'calculation': value, 'hosted_data': digest(encoded(self.hosted_data))}))
        return value

    def source_rows(self):
        # Copy the PostgreSQL response: the first QC example modifies one field.
        return json.loads(json.dumps(self.hosted_data))

    async def calculate(self, key, run_id):
        if key not in PARALLEL_JOBS:
            return await super().calculate(key, run_id)
        if self.pool is None:
            self.pool = ProcessPoolExecutor(max_workers=4,
                                            mp_context=multiprocessing.get_context('spawn'))
        return await asyncio.get_running_loop().run_in_executor(
            self.pool, calculate_independent_job, str(self.directory), key, self.settings, run_id)

    async def run(self, start='submission', scope='workflow'):
        try:
            return await super().run(start, scope)
        finally:
            if self.pool is not None:
                self.pool.shutdown(wait=True, cancel_futures=True)
                self.pool = None

    def publish(self, event):
        output = None
        if event.get('state') == 'complete':
            key = event['job']
            output = {'html': (self.directory / key / 'report.html').read_text(),
                      'record': self.records[key], 'output': self.output(key)}
        self.delivery.publish({'event': event, 'state': self.state(), 'output': output})
        print(event.get('job', 'workflow'), event['state'], event.get('message', ''), flush=True)

    async def handover(self, handover):
        deadline = time.monotonic() + 180
        while time.monotonic() < deadline:
            try:
                # A transfer must be visible before waiting for acknowledgement.
                self.delivery.flush(required=True)
                control = api('control')
            except TemporaryAPIError:
                await asyncio.sleep(1.5)
                continue
            if control['transfer_count'] > self.transfer_count or control['connected']:
                self.transfer_count = control['transfer_count']
                return control['connected']
            await asyncio.sleep(1.5)
        raise TimeoutError('File transfer was not acknowledged within three minutes. Start again to continue.')


async def main():
    context = api('context')
    directory = Path('/tmp/paper-results'); directory.mkdir(exist_ok=True)
    restore(context['checkpoint'], directory)
    runner = HostedWorkflow(context)
    result, error = None, None
    try:
        result = await runner.run(context['start_job'], context.get('scope', 'workflow'))
    except Exception as caught:
        error = str(caught)
    api('finish', {'checkpoint':checkpoint(directory), 'bundle':base64.b64encode(runner.bundle()).decode(),
                   'state':runner.state(), 'result':result, 'error':error,
                   'pending_events':runner.delivery.pending})
    if error:
        raise RuntimeError(error)


if __name__ == '__main__':
    asyncio.run(main())
