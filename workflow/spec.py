"""Read the declared jobs and follow their input connections."""
import json
from pathlib import Path
import re
from .sources import SourceResolver

ROOT = Path(__file__).resolve().parents[1]


def unique_fields(items):
    result = {}
    for key, value in items:
        if key in result:
            raise ValueError(f'Duplicate configuration field: {key}')
        result[key] = value
    return result


def load_spec(path=ROOT / 'workflow/jobs.json'):
    config = json.loads(Path(path).read_text(), object_pairs_hook=unique_fields)
    if set(config) != {'jobs', 'defaults', 'stages', 'handovers'}:
        raise ValueError('Expected jobs, defaults, stages and handovers')
    fields = {'key', 'title', 'module', 'owner', 'parents', 'run', 'description'}
    sources = None
    seen = set()
    for job in config['jobs']:
        key, parents = job.get('key', ''), job.get('parents', [])
        if set(job) != fields or not re.fullmatch(r'[a-z][a-z0-9_]*', key) or key in seen:
            raise ValueError(f'Invalid or duplicate job: {key}')
        if not isinstance(parents, list) or len(parents) != len(set(parents)) or not set(parents) <= seen:
            raise ValueError(f'Parents must be distinct preceding jobs: {key}')
        exists = (ROOT / job['run']).is_file() if isinstance(job.get('run'), str) else False
        if not exists and job.get('run') == f'jobs/{key}/run.R':
            sources = sources or SourceResolver(ROOT)
            exists = sources.job_path(key).is_file()
        if job['run'] != f'jobs/{key}/run.R' or not exists:
            raise ValueError(f'Missing or unexpected R entry point: {key}')
        if any(not isinstance(job[name], str) or not job[name].strip()
               for name in ['title', 'module', 'owner', 'description']):
            raise ValueError(f'Incomplete job description: {key}')
        seen.add(key)
    stages = config['stages']
    flattened = [key for stage in stages for key in stage]
    if not all(isinstance(stage, list) and stage for stage in stages) or len(flattened) != len(seen) or set(flattened) != seen:
        raise ValueError('Each job must appear in exactly one execution stage')
    position = {key: index for index, stage in enumerate(stages) for key in stage}
    if any(position[parent] >= position[job['key']] for job in config['jobs'] for parent in job['parents']):
        raise ValueError('Parents must be ready before their dependent stage')
    spec = {job['key']: job for job in config['jobs']}
    for recipients in config['handovers'].values():
        for key, parents in recipients.items():
            if key not in spec or not parents or len(parents) != len(set(parents)) or not set(parents) <= set(spec[key]['parents']):
                raise ValueError(f'Invalid file-transfer boundary: {key}')
    return config


CONFIG = load_spec()
SPEC = {job['key']: job for job in CONFIG['jobs']}
JOBS = [(job['key'], job['title'], job['module'], job['owner'], job['parents'], job['description'])
        for job in CONFIG['jobs']]
DEFAULTS = CONFIG['defaults']
STAGES = CONFIG['stages']
HANDOVERS = CONFIG['handovers']


def handover_groups(stage, active):
    """Only recipients of revised inputs need a file transfer."""
    for boundary, recipients in HANDOVERS.items():
        group = [key for key in stage if key in recipients
                 and any(parent in active for parent in recipients[key])]
        if group:
            yield {'boundary': boundary, 'group': group}


def active_spec(settings):
    return {key: job for key, job in SPEC.items()
            if settings.get('mse', True) or job['module'] != 'mse'}


def downstream(roots, spec=None):
    spec = SPEC if spec is None else spec
    selected = set(roots)
    for key, job in spec.items():
        if selected.intersection(job['parents']):
            selected.add(key)
    return [key for key in spec if key in selected]
