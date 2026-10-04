"""Compare numerical outputs with explicit, metric-specific tolerances."""
import argparse
import json
import math
from pathlib import Path
import re

from workflow.spec import DEFAULTS, SPEC, active_spec

ASSESSMENT_JOBS = {'assessment_a1', 'assessment_a2', 'assessment_b1', 'assessment_b2'}
CASE_JOBS = {SPEC[job]['title']: job for job in ASSESSMENT_JOBS}
GRADIENT_FIELDS = {'objective_gradient_logK', 'projected_gradient_logK'}
NEAR_ZERO_GRADIENT = 1e-7
RESIDUAL_ABSOLUTE = 1e-8
DIAGNOSTIC_FIELDS = GRADIENT_FIELDS | {'convergence', 'gradient_check', 'active_bound', 'fit_method'}


def numeric(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


def fit_metadata_matches(expected, actual):
    for values in (expected, actual):
        if (type(values.get('convergence')) is not int or values['convergence'] != 0
                or values.get('gradient_check') != 'Pass'
                or values.get('gradient_tolerance') != 1e-4):
            return False
    return (expected.get('active_bound') in {'none', 'lower', 'upper'}
            and expected.get('active_bound') == actual.get('active_bound')
            and expected.get('fit_method') == 'RTMB::MakeADFun + nlminb'
            and expected.get('fit_method') == actual.get('fit_method'))


def near_zero_gradient(expected, actual, key):
    """Bounded stationarity-diagnostic policy; not an RTMB accuracy guarantee."""
    if not fit_metadata_matches(expected, actual):
        return False
    left, right = expected[key], actual[key]
    return (numeric(left) and numeric(right)
            and abs(left) <= NEAR_ZERO_GRADIENT and abs(right) <= NEAR_ZERO_GRADIENT
            and abs(left - right) <= NEAR_ZERO_GRADIENT)


def check_residuals(output, path):
    for index, row in enumerate(output.get('series', [])):
        if 'log_residual' not in row:
            continue
        observed, fitted, residual = (row.get(name) for name in
                                      ('observed_index', 'fitted_index', 'log_residual'))
        assert (numeric(observed) and observed > 0 and numeric(fitted) and fitted > 0
                and numeric(residual) and abs(residual - math.log(observed / fitted)) <= 1e-12), \
            (path, index, 'Residual does not match its observed and fitted indices.')


def same_json_value(left, right):
    if isinstance(left, bool) or isinstance(right, bool):
        return type(left) is type(right) and left == right
    if isinstance(left, (int, float)):
        return numeric(left) and numeric(right) and left == right
    if isinstance(left, dict):
        return (isinstance(right, dict) and left.keys() == right.keys()
                and all(same_json_value(value, right[key]) for key, value in left.items()))
    if isinstance(left, list):
        return (isinstance(right, list) and len(left) == len(right)
                and all(same_json_value(a, b) for a, b in zip(left, right)))
    return type(left) is type(right) and left == right


def check_copies(expected, actual, context, path):
    """Each copied field must equal its own source before numerical comparison."""
    assert set(context) == ASSESSMENT_JOBS, (path, 'Missing direct assessment context.')
    for side, output in enumerate((expected, actual)):
        rows = output.get('diagnostics', [])
        cases = [row.get('case') for row in rows]
        assert len(cases) == 4 and set(cases) == set(CASE_JOBS), (path, 'Invalid assessment cases.')
        assert set(output.get('series', {})) == set(CASE_JOBS), (path, 'Invalid assessment series.')
        for row in rows:
            case = row['case']
            direct = context[CASE_JOBS[case]][side]
            assert DIAGNOSTIC_FIELDS <= set(row), (path, case, 'Missing fit diagnostics.')
            assert all(key in direct and same_json_value(value, direct[key]) for key, value in row.items()
                       if key != 'case'), (path, case, 'Diagnostic copy differs from its source.')
            assert same_json_value(output['series'][case], direct['series']), (path, case, 'Series copy differs from its source.')
            check_residuals(direct, CASE_JOBS[case])


def compare(expected, actual, path='output', assessment_context=None):
    if path in ASSESSMENT_JOBS and isinstance(expected, dict) and isinstance(actual, dict):
        assessment_context = {path: (expected, actual)}
        check_residuals(expected, path)
        check_residuals(actual, path)
    if path in {'assessment_summary', 'assessment_report'} and assessment_context is not None:
        check_copies(expected, actual, assessment_context, path)
    if isinstance(expected, dict):
        assert isinstance(actual, dict) and expected.keys() == actual.keys(), path
        pair = (expected, actual) if path in ASSESSMENT_JOBS else None
        if assessment_context is not None and re.fullmatch(r'assessment_(summary|report)\.diagnostics\[\d+\]', path):
            job = CASE_JOBS.get(expected.get('case'))
            if job in assessment_context and expected.get('case') == actual.get('case'):
                pair = assessment_context[job]
        for key in expected:
            if pair is not None and key in GRADIENT_FIELDS and near_zero_gradient(*pair, key):
                continue
            compare(expected[key], actual[key], path + '.' + key, assessment_context)
    elif isinstance(expected, list):
        assert isinstance(actual, list) and len(expected) == len(actual), path
        for i, (left, right) in enumerate(zip(expected, actual)):
            compare(left, right, f'{path}[{i}]', assessment_context)
    else:
        absolute = 1e-9
        direct = re.fullmatch(r'(assessment_[ab][12])\.series\[\d+\]\.log_residual', path)
        copied = re.fullmatch(r'assessment_(?:summary|report)\.series\.(Assessment [AB][12])\[\d+\]\.log_residual', path)
        job = direct[1] if direct else CASE_JOBS[copied[1]] if copied else None
        if job and assessment_context and job in assessment_context:
            if fit_metadata_matches(*assessment_context[job]):
                absolute = RESIDUAL_ABSOLUTE
        if isinstance(expected, float) or absolute == RESIDUAL_ABSOLUTE:
            assert (numeric(expected) and numeric(actual)
                    and math.isclose(expected, actual, rel_tol=1e-6, abs_tol=absolute)), (path, expected, actual)
        else:
            assert expected == actual, (path, expected, actual)


def verify(reference, result, job=None):
    state = json.loads((reference / 'state.json').read_text())
    spec = active_spec({**DEFAULTS, 'mse': False, **state['settings']})
    if job is not None and job not in spec:
        raise ValueError('Unknown job to compare.')
    selected = [job] if job is not None else spec
    context = None
    if any(key in {'assessment_summary', 'assessment_report'} for key in selected):
        context = {}
        for key in ASSESSMENT_JOBS:
            paths = (reference / key / 'output.json', result / key / 'output.json')
            if not all(path.is_file() for path in paths):
                raise ValueError('Missing direct assessment context for summary/report comparison: ' + key)
            context[key] = tuple(json.loads(path.read_text()) for path in paths)
            compare(*context[key], key)
    for key in selected:
        left = json.loads((reference / key / 'output.json').read_text())
        right = json.loads((result / key / 'output.json').read_text())
        # A resubmission can pass immediately when it uses already corrected data.
        if key == 'qc':
            left.pop('returned', None)
            right.pop('returned', None)
        compare(left, right, key, context)
    return len(selected)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('reference', type=Path)
    parser.add_argument('result', type=Path)
    parser.add_argument('--job', choices=SPEC, help='Compare only this saved job output.')
    args = parser.parse_args()
    count = verify(args.reference, args.result, args.job)
    print(f'{count} job outputs agree (relative 1e-6; absolute 1e-9; assessment log residuals absolute 1e-8; near-zero gradients magnitude and difference 1e-7).')
