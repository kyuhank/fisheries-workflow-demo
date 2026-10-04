"""Run each readable R job through the declared container's Rscript runtime.

Python owns scheduling, SQLite, reports and output custody. It does not supply a
second implementation of the CPUE, assessment or MSE calculation.
"""
import asyncio
import json
import os
import re
from pathlib import Path
import shutil
import subprocess

ROOT = Path(__file__).resolve().parents[1]
_NATIVE_INFO = {}


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
        key = (executable, (ROOT / 'workflow/r_driver.R').read_bytes())
        if key not in _NATIVE_INFO:
            process = subprocess.run(
                [executable, '--vanilla', str(ROOT / 'workflow/r_driver.R'), '--info'],
                cwd=ROOT, capture_output=True, text=True, timeout=30)
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
        executable = shutil.which('Rscript')
        process = await asyncio.create_subprocess_exec(
            executable, '--vanilla', str(ROOT / 'workflow/r_driver.R'),
            cwd=ROOT, stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
        try:
            stdout, stderr = await asyncio.wait_for(process.communicate(request.encode()), 180)
        except BaseException:
            if process.returncode is None:
                process.kill()
                await process.wait()
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
