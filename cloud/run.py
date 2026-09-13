"""Run the preserved calculations on GitHub, with hosted inputs and event records."""
import asyncio
import base64
import io
import json
import os
from pathlib import Path
import sys
import time
from urllib.request import Request, urlopen
import uuid
import zipfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from workflow.engine import Workflow, digest, encoded
from workflow.spec import SPEC

API = 'https://gvunwnpsfmylmqfqowzp.supabase.co/functions/v1/paper-api'
REQUEST = str(uuid.UUID(os.environ['PAPER_REQUEST_ID']))
_token, _expires = '', 0


def api(path, body=None):
    global _token, _expires
    if time.time() >= _expires:
        url = os.environ['ACTIONS_ID_TOKEN_REQUEST_URL'] + '&audience=fisheries-paper-demo'
        request = Request(url, headers={'Authorization': 'Bearer ' + os.environ['ACTIONS_ID_TOKEN_REQUEST_TOKEN']})
        with urlopen(request, timeout=30) as response:
            _token = json.load(response)['value']
        _expires = time.time() + 240
    request = Request(API + '/runner/' + path + '?request=' + REQUEST,
                      data=json.dumps(body).encode() if body is not None else None,
                      headers={'Authorization': 'Bearer ' + _token, 'Content-Type': 'application/json'})
    with urlopen(request, timeout=45) as response:
        return json.load(response)


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
        self.transferred = set()
        self.transfer_count = 0
        self.connected = context['handover'] != 'manual'
        super().__init__('/tmp/paper-results', pause=.65, before_job=self.handover)
        self.execution = {'provider': 'GitHub Actions', 'repository': 'kyuhank/fisheries-workflow-demo',
                          'commit': context['commit_sha'], 'github_run': context['github_run'],
                          'container': 'ghcr.io/pacificcommunity/cpue-workshop@sha256:17b03d6e06da229b17524997d8a3fc8eb5f8f25233894b5ab99f89109b3890c5',
                          'data_source': 'Supabase PostgreSQL: fixed synthetic records',
                          'data_checksum': digest(encoded(self.hosted_data))}
        self.configure(context['settings'])
        self.active = self.plan(context['start_job'])['run']

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

    async def emit(self, key, state, message):
        await super().emit(key, state, message)
        self.publish({**self.events[-1], 'record': self.records.get(key)})

    def publish(self, event):
        output = None
        if event.get('state') == 'complete':
            key = event['job']
            output = {'html': (self.directory / key / 'report.html').read_text(),
                      'record': self.records[key], 'output': self.output(key)}
        api('event', {'event': event, 'state': self.state(), 'output': output})
        print(event.get('job', 'workflow'), event['state'], event.get('message', ''), flush=True)

    async def handover(self, key):
        if self.connected:
            return
        boundary = 'data' if key in ('cpue_a', 'cpue_b') and 'extract' in self.active else (
            'cpue' if key.startswith('prepare_') and any(k in self.active for k in ('extract','cpue_a','cpue_b')) else None)
        if boundary is None or boundary in self.transferred:
            return
        event = {'job':key, 'state':'handover', 'boundary':boundary,
                 'message':'The updated output is ready. Pass the files to the next analyst to continue.'}
        self.events.append(event); self.publish(event)
        deadline = time.monotonic() + 180
        while time.monotonic() < deadline:
            control = api('control')
            if control['transfer_count'] > self.transfer_count or control['connected']:
                self.transfer_count = control['transfer_count']; self.connected = control['connected']
                self.transferred.add(boundary)
                await self.emit(key, 'received', 'The next analyst received the updated inputs.')
                return
            await asyncio.sleep(1.5)
        raise TimeoutError('File transfer was not acknowledged within three minutes. Start again to continue.')


async def main():
    context = api('context')
    directory = Path('/tmp/paper-results'); directory.mkdir(exist_ok=True)
    restore(context['checkpoint'], directory)
    runner = HostedWorkflow(context)
    runner.notify = lambda event: runner.publish(event) if event['state'] == 'plan' else None
    result, error = None, None
    try:
        result = await runner.run(context['start_job'])
    except Exception as caught:
        error = str(caught)
    api('finish', {'checkpoint':checkpoint(directory), 'bundle':base64.b64encode(runner.bundle()).decode(), 'state':runner.state(), 'result':result, 'error':error})
    if error:
        raise RuntimeError(error)


if __name__ == '__main__':
    asyncio.run(main())
