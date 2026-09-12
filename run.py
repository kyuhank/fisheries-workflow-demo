"""Run the preserved example with Python's standard library."""
import argparse
import asyncio
import json
from pathlib import Path

from workflow.engine import Workflow
from workflow.spec import SPEC


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--from', dest='start', choices=SPEC, default='submission')
    parser.add_argument('--output', default='runs')
    parser.add_argument('--settings', type=Path)
    args = parser.parse_args()
    workflow = Workflow(args.output, notify=lambda e: print(e.get('job','Workflow'), e['state'], e.get('message',''), flush=True))
    if args.settings:
        workflow.configure(json.loads(args.settings.read_text()))
    result = asyncio.run(workflow.run(args.start))
    print(f"{result['run_id']}: {len(result['run'])} jobs executed; {len(result['retained'])} retained.")
    print(Path(args.output, 'assessment_report/report.html').resolve())


if __name__ == '__main__':
    main()
