"""Compare calculated outputs, allowing for small floating-point differences."""
import argparse
import json
import math
from pathlib import Path

from workflow.spec import DEFAULTS, active_spec


def compare(expected, actual, path='output'):
    if isinstance(expected, dict):
        assert isinstance(actual, dict) and expected.keys() == actual.keys(), path
        for key in expected:
            compare(expected[key], actual[key], path + '.' + key)
    elif isinstance(expected, list):
        assert isinstance(actual, list) and len(expected) == len(actual), path
        for i, (left, right) in enumerate(zip(expected, actual)):
            compare(left, right, f'{path}[{i}]')
    elif isinstance(expected, float):
        assert math.isclose(expected, actual, rel_tol=1e-6, abs_tol=1e-9), (path, expected, actual)
    else:
        assert expected == actual, (path, expected, actual)


def verify(reference, result):
    state = json.loads((reference / 'state.json').read_text())
    spec = active_spec({**DEFAULTS, 'mse': False, **state['settings']})
    for key in spec:
        left = json.loads((reference / key / 'output.json').read_text())
        right = json.loads((result / key / 'output.json').read_text())
        # A resubmission can pass immediately when it uses already corrected data.
        if key == 'qc':
            left.pop('returned', None)
            right.pop('returned', None)
        compare(left, right, key)
    return len(spec)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('reference', type=Path)
    parser.add_argument('result', type=Path)
    args = parser.parse_args()
    count = verify(args.reference, args.result)
    print(f'{count} job outputs agree (relative tolerance 1e-6; absolute tolerance 1e-9).')
