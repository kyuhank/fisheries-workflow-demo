"""Write a compact record of the behavioural checks, without timing claims."""
import hashlib
import json
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


class RecordResult(unittest.TextTestResult):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.passed = []

    def addSuccess(self, test):
        super().addSuccess(test)
        self.passed.append(test.id().split('.')[-1])


suite = unittest.defaultTestLoader.discover(str(ROOT / 'tests'))
result = unittest.TextTestRunner(resultclass=RecordResult, verbosity=1).run(suite)
if not result.wasSuccessful():
    raise SystemExit(1)
files = [*ROOT.glob('workflow/*.py'), *ROOT.glob('tests/*.py')]
record = {
    'scope': 'Synthetic workflow implementation; no assessment-performance or scientific-validity claim.',
    'checks_passed': result.passed,
    'source_files': {str(path.relative_to(ROOT)): hashlib.sha256(path.read_bytes()).hexdigest() for path in files},
    'comparison_tolerances': {'relative': 1e-6, 'absolute': 1e-9},
}
path = Path(sys.argv[1] if len(sys.argv) > 1 else '.test-output/behaviour.json')
path.parent.mkdir(parents=True, exist_ok=True)
path.write_text(json.dumps(record, indent=2) + '\n')
print(f'{len(result.passed)} behavioural checks recorded in {path}')
