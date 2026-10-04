"""Pass job inputs to R through the container's Make recipes."""
import asyncio
import json
import os
import re
import signal
from pathlib import Path
import shutil
import subprocess

ROOT = Path(__file__).resolve().parents[1]
_NATIVE_INFO = {}


def make_command(target):
    executable = shutil.which('make')
    if executable is None:
        raise RuntimeError('Make is required in the declared container.')
    return [executable, '--no-print-directory', '--silent', '--jobs=1',
            '-f', str(ROOT / 'workflow/Makefile'), target]


def process_environment():
    environment = dict(os.environ)
    for name in ('MAKEFLAGS', 'MFLAGS', 'GNUMAKEFLAGS'):
        environment.pop(name, None)
    return environment


def kill_process_group(process):
    try:
        os.killpg(process.pid, signal.SIGKILL)
    except ProcessLookupError:
        pass


def run_command(command, timeout, environment=None):
    process = subprocess.Popen(command, cwd=ROOT, env=process_environment() if environment is None else environment,
                               stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                               text=True, start_new_session=True)
    try:
        stdout, stderr = process.communicate(timeout=timeout)
    except BaseException:
        kill_process_group(process)
        process.communicate()
        raise
    return subprocess.CompletedProcess(command, process.returncode, stdout, stderr)


class RBridge:
    @staticmethod
    def require_container():
        if not any(Path(marker).is_file() for marker in ('/.dockerenv', '/run/.containerenv')):
            raise RuntimeError('New workflow calculations require the declared Docker container.')
        image = os.environ.get('PAPER_RUNTIME_IMAGE', '')
        if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9._:/-]*@sha256:[0-9a-f]{64}', image):
            raise RuntimeError('PAPER_RUNTIME_IMAGE must identify the actual resolved container digest.')
        return image

    def software(self):
        image = self.require_container()
        executable = shutil.which('Rscript')
        if executable is None:
            raise RuntimeError('Rscript is required; install the declared R/jsonlite/RTMB runtime.')
        key = (executable, (ROOT / 'workflow/r_driver.R').read_bytes(),
               (ROOT / 'workflow/Makefile').read_bytes())
        if key not in _NATIVE_INFO:
            process = run_command(make_command('info'), timeout=30)
            if process.returncode:
                raise RuntimeError('R runtime prerequisites failed: ' + process.stderr.strip()[-2000:])
            _NATIVE_INFO[key] = json.loads(process.stdout)
        info = dict(_NATIVE_INFO[key])
        info['container'] = image
        url = os.environ.get('PAPER_RUNTIME_IMAGE_URL')
        if url:
            if not re.fullmatch(r'https://[A-Za-z0-9./_%~-]+', url):
                raise RuntimeError('PAPER_RUNTIME_IMAGE_URL must be the actual HTTPS package page.')
            info['container_url'] = url
        for name in ('r', 'r_platform', 'jsonlite', 'RTMB', 'TMB', 'knitr', 'rmarkdown', 'quarto'):
            if not isinstance(info.get(name), str) or not info[name]:
                raise RuntimeError('The calculation runtime did not verify ' + name + '.')
        return info

    async def calculate(self, context):
        request = json.dumps(context, separators=(',', ':'), allow_nan=False)
        self.software()
        process = await asyncio.create_subprocess_exec(
            *make_command('calculate'), cwd=ROOT, env=process_environment(),
            stdin=asyncio.subprocess.PIPE, stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE, start_new_session=True)
        try:
            stdout, stderr = await asyncio.wait_for(process.communicate(request.encode()), 180)
        except BaseException:
            kill_process_group(process)
            await process.communicate()
            raise
        if process.returncode:
            raise RuntimeError(f'R job {context["key"]} failed: ' + stderr.decode().strip()[-2000:])
        value = json.loads(stdout)
        if not isinstance(value, dict) or set(value) != {'result', 'effects'}:
            raise ValueError('The R job must return the declared result/effects envelope.')
        if not isinstance(value['result'], dict) or not isinstance(value['effects'], dict):
            raise ValueError('R job output and effects must be JSON objects.')
        # Reject null/non-finite contamination during normal Python encoding too.
        json.dumps(value, allow_nan=False)
        return value
