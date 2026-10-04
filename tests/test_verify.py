"""Near-zero diagnostic comparison boundaries; no model or runtime execution."""
import copy
import json
import math
from pathlib import Path
import tempfile
import unittest

from verify import compare, near_zero_gradient, verify


ASSESSMENTS = ('assessment_a1', 'assessment_a2', 'assessment_b1', 'assessment_b2')
GRADIENTS = ('objective_gradient_logK', 'projected_gradient_logK')
OBSERVED_LEFT = 5.48891009747709e-13
OBSERVED_RIGHT = 2.35247591981661e-08
RESIDUAL_LEFT = 0.00198045620530427
RESIDUAL_RIGHT = 0.00198045831937885


def assessment(gradient=OBSERVED_LEFT):
    return {'convergence': 0, 'gradient_check': 'Pass', 'active_bound': 'none',
            'fit_method': 'RTMB::MakeADFun + nlminb', 'gradient_tolerance': 1e-4,
            'objective_gradient_logK': gradient, 'projected_gradient_logK': gradient,
            'K': 1000.0, 'objective_value': 0.25,
            'series': [{'year': 2023, 'B_over_K': 0.6}]}


def residual_assessment(residual):
    output = assessment()
    output['series'][0].update(observed_index=1.0, fitted_index=math.exp(-residual),
                               log_residual=residual)
    return output


def copied_assessments():
    context, summaries = {}, [{'diagnostics': [], 'series': {}} for _ in range(2)]
    for job in ASSESSMENTS:
        label = 'Assessment ' + job.split('_')[1].upper()
        pair = (residual_assessment(RESIDUAL_LEFT), residual_assessment(RESIDUAL_RIGHT))
        pair[1].update({field: OBSERVED_RIGHT for field in GRADIENTS})
        context[job] = pair
        for side, direct in enumerate(pair):
            row = {key: copy.deepcopy(value) for key, value in direct.items()
                   if key not in ('series', 'gradient_tolerance')}
            summaries[side]['diagnostics'].append({'case': label, **row})
            summaries[side]['series'][label] = copy.deepcopy(direct['series'])
    return (*summaries, context)


class VerifyGradientTests(unittest.TestCase):
    def test_actual_diagnostic_pair_is_accepted_only_at_four_assessment_roots(self):
        left, right = assessment(), assessment(OBSERVED_RIGHT)
        preserved = copy.deepcopy((left, right))
        for job in ASSESSMENTS:
            with self.subTest(job=job):
                compare(left, right, job)
                compare(right, left, job)
        self.assertEqual((left, right), preserved)

    def test_near_zero_exception_has_absolute_value_and_difference_limits(self):
        for left, right in ((0.0, 1e-7), (-5e-8, 5e-8)):
            with self.subTest(accepted=(left, right)):
                compare(assessment(left), assessment(right), 'assessment_b2')
        for left, right in ((0.0, 1.0001e-7), (1.0001e-7, 0.0),
                            (-1e-7, 1e-7), (1e-7, -1e-7)):
            with self.subTest(rejected=(left, right)):
                self.assertFalse(near_zero_gradient(assessment(left), assessment(right),
                                                    GRADIENTS[0]))
                with self.assertRaises(AssertionError):
                    compare(assessment(left), assessment(right), 'assessment_b2')

    def test_nonfinite_gradients_are_rejected_even_when_identically_nonfinite(self):
        for field in GRADIENTS:
            for value in (float('inf'), -float('inf'), float('nan')):
                for sides in ('left', 'right', 'both'):
                    with self.subTest(field=field, value=value, sides=sides):
                        left, right = assessment(), assessment(OBSERVED_RIGHT)
                        if sides in ('left', 'both'):
                            left[field] = value
                        if sides in ('right', 'both'):
                            right[field] = value
                        self.assertFalse(near_zero_gradient(left, right, field))
                        with self.assertRaises(AssertionError):
                            compare(left, right, 'assessment_b2')

    def test_boolean_and_text_gradients_cannot_use_the_numeric_exception(self):
        for field in GRADIENTS:
            for value in (False, True, '0', None):
                with self.subTest(field=field, value=value):
                    left, right = assessment(), assessment(OBSERVED_RIGHT)
                    right[field] = value
                    self.assertFalse(near_zero_gradient(left, right, field))
                    with self.assertRaises(AssertionError):
                        compare(left, right, 'assessment_b2')

    def test_invalid_shared_optimizer_prerequisites_do_not_relax_comparison(self):
        invalid = {'convergence': 1, 'gradient_check': 'Review',
                   'active_bound': 'unknown', 'fit_method': 'another optimizer',
                   'gradient_tolerance': 1e-3}
        for field, value in invalid.items():
            with self.subTest(field=field):
                left, right = assessment(), assessment(OBSERVED_RIGHT)
                left[field] = right[field] = value
                for gradient in GRADIENTS:
                    self.assertFalse(near_zero_gradient(left, right, gradient))
                with self.assertRaises(AssertionError):
                    compare(left, right, 'assessment_b2')

    def test_boolean_convergence_cannot_satisfy_optimizer_prerequisites(self):
        left, right = assessment(), assessment(OBSERVED_RIGHT)
        left['convergence'] = right['convergence'] = False
        self.assertFalse(near_zero_gradient(left, right, GRADIENTS[0]))
        with self.assertRaises(AssertionError):
            compare(left, right, 'assessment_b2')

    def test_changed_or_missing_optimizer_metadata_remains_a_failure(self):
        changed = {'convergence': 1, 'gradient_check': 'Review', 'active_bound': 'upper',
                   'fit_method': 'another optimizer', 'gradient_tolerance': 1e-3}
        for field, value in changed.items():
            for side in ('left', 'right'):
                with self.subTest(field=field, side=side):
                    left, right = assessment(), assessment(OBSERVED_RIGHT)
                    (left if side == 'left' else right)[field] = value
                    with self.assertRaises(AssertionError):
                        compare(left, right, 'assessment_b2')
            left, right = assessment(), assessment(OBSERVED_RIGHT)
            right.pop(field)
            with self.subTest(missing=field), self.assertRaises(AssertionError):
                compare(left, right, 'assessment_b2')

    def test_boundary_fit_nonzero_raw_gradients_keep_the_ordinary_policy(self):
        for bound, raw in (('lower', 2.0), ('upper', -2.0)):
            with self.subTest(bound=bound):
                left = assessment()
                left.update(active_bound=bound, objective_gradient_logK=raw,
                            projected_gradient_logK=0.0)
                right = copy.deepcopy(left)
                right['objective_gradient_logK'] = raw + 5e-7
                right['projected_gradient_logK'] = OBSERVED_RIGHT
                self.assertFalse(near_zero_gradient(left, right, GRADIENTS[0]))
                compare(left, right, 'assessment_b2')
                right['objective_gradient_logK'] = raw + 1e-3
                with self.assertRaises(AssertionError):
                    compare(left, right, 'assessment_b2')

    def test_ordinary_estimates_series_and_other_diagnostics_remain_strict(self):
        for field, value in (('K', 1000.01), ('objective_value', 0.25001),
                             ('log_index_SSE', OBSERVED_RIGHT)):
            with self.subTest(field=field):
                left, right = assessment(), assessment(OBSERVED_RIGHT)
                if field == 'log_index_SSE':
                    left[field] = OBSERVED_LEFT
                right[field] = value
                with self.assertRaises(AssertionError):
                    compare(left, right, 'assessment_b2')
        left, right = assessment(), assessment(OBSERVED_RIGHT)
        right['series'][0]['B_over_K'] = 0.60001
        with self.assertRaises(AssertionError):
            compare(left, right, 'assessment_b2')

    def test_same_named_gradients_elsewhere_do_not_receive_a_blanket_exception(self):
        for path in ('output', 'cpue_a', 'mse_prepare', 'assessment_a1.diagnostics'):
            with self.subTest(path=path), self.assertRaises(AssertionError):
                compare(assessment(), assessment(OBSERVED_RIGHT), path)
        for job in ('assessment_summary', 'assessment_report'):
            left = {'diagnostics': [assessment()]}
            right = {'diagnostics': [assessment(OBSERVED_RIGHT)]}
            with self.subTest(job=job), self.assertRaises(AssertionError):
                compare(left, right, job)

    def test_ordinary_numerical_tolerance_still_applies(self):
        compare({'value': 1000.0}, {'value': 1000.0005}, 'cpue_a')
        with self.assertRaises(AssertionError):
            compare({'value': OBSERVED_LEFT}, {'value': OBSERVED_RIGHT}, 'cpue_a')

    def test_saved_job_verification_uses_the_job_specific_policy(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            reference, result = root / 'reference', root / 'result'
            for folder in (reference, result):
                (folder / 'assessment_b2').mkdir(parents=True)
            (reference / 'state.json').write_text(json.dumps({'settings': {'mse': True}}))
            (reference / 'assessment_b2/output.json').write_text(json.dumps(assessment()))
            output = result / 'assessment_b2/output.json'
            output.write_text(json.dumps(assessment(OBSERVED_RIGHT)))
            self.assertEqual(verify(reference, result, job='assessment_b2'), 1)
            altered = assessment(OBSERVED_RIGHT)
            altered['K'] = 1000.01
            output.write_text(json.dumps(altered))
            with self.assertRaises(AssertionError):
                verify(reference, result, job='assessment_b2')

    def test_observed_log_residual_pair_requires_valid_assessment_metadata(self):
        left, right = residual_assessment(RESIDUAL_LEFT), residual_assessment(RESIDUAL_RIGHT)
        for job in ASSESSMENTS:
            with self.subTest(job=job):
                compare(left, right, job)
        for field, value in (('convergence', 1), ('gradient_check', 'Review'),
                             ('gradient_tolerance', 1e-3), ('active_bound', 'unknown'),
                             ('fit_method', 'another optimizer')):
            invalid_left, invalid_right = copy.deepcopy(left), copy.deepcopy(right)
            invalid_left[field] = invalid_right[field] = value
            with self.subTest(field=field), self.assertRaises(AssertionError):
                compare(invalid_left, invalid_right, 'assessment_b2')
        with self.assertRaises(AssertionError):
            compare(left, right, 'cpue_a')
        with self.assertRaises(AssertionError):
            compare({'log_residual': 0.0}, {'log_residual': 7e-9}, 'assessment_b2.other')

    def test_json_integer_zero_residual_and_absolute_limit(self):
        zero = json.loads('0')
        self.assertIs(type(zero), int)
        compare(residual_assessment(zero), residual_assessment(7e-9), 'assessment_b2')
        with self.assertRaises(AssertionError):
            compare(residual_assessment(zero), residual_assessment(1.01e-8), 'assessment_b2')
        with self.assertRaises(AssertionError):
            compare({'ordinary_integer': zero}, {'ordinary_integer': 7e-9}, 'cpue_a')

    def test_log_residual_invariant_rejects_even_identical_incoherent_outputs(self):
        output = residual_assessment(0.0)
        output['series'][0]['log_residual'] = 2e-12
        with self.assertRaises(AssertionError):
            compare(output, copy.deepcopy(output), 'assessment_b2')
        for field in ('observed_index', 'fitted_index'):
            for value in (0.0, -1.0, float('inf'), float('nan'), True):
                output = residual_assessment(0.0)
                output['series'][0][field] = value
                with self.subTest(field=field, value=value), self.assertRaises(AssertionError):
                    compare(output, copy.deepcopy(output), 'assessment_b2')

    def test_copied_summary_and_report_require_complete_verified_direct_context(self):
        left, right, context = copied_assessments()
        for job in ('assessment_summary', 'assessment_report'):
            with self.subTest(job=job):
                compare(left, right, job, context)
                with self.assertRaises(AssertionError):
                    compare(left, right, job)
                missing = {key: value for key, value in context.items() if key != 'assessment_b2'}
                with self.assertRaises(AssertionError):
                    compare(left, right, job, missing)

    def test_copied_case_identity_diagnostics_and_series_custody_are_strict(self):
        for mutation in ('missing_case', 'unknown_case', 'duplicate_case', 'missing_field',
                         'diagnostic_drift', 'series_drift', 'boolean_copy'):
            left, right, context = copied_assessments()
            if mutation == 'missing_case':
                right['diagnostics'].pop()
            elif mutation == 'unknown_case':
                right['diagnostics'][0]['case'] = 'Assessment C1'
            elif mutation == 'duplicate_case':
                right['diagnostics'][0]['case'] = right['diagnostics'][1]['case']
            elif mutation == 'missing_field':
                right['diagnostics'][0].pop('gradient_check')
            elif mutation == 'diagnostic_drift':
                right['diagnostics'][0]['objective_gradient_logK'] += 1e-15
            elif mutation == 'boolean_copy':
                right['diagnostics'][0]['convergence'] = False
            else:
                right['series']['Assessment A1'][0]['B_over_K'] += 1e-12
            with self.subTest(mutation=mutation), self.assertRaises(AssertionError):
                compare(left, right, 'assessment_summary', context)

    def test_copied_ordinary_values_are_not_relaxed_by_source_context(self):
        left, right, context = copied_assessments()
        context['assessment_b2'][1]['K'] += 0.01
        right['diagnostics'][3]['K'] += 0.01
        with self.assertRaises(AssertionError):
            compare(left, right, 'assessment_report', context)

    def test_saved_summary_verification_fetches_and_checks_all_four_direct_outputs(self):
        left, right, context = copied_assessments()
        with tempfile.TemporaryDirectory() as directory:
            reference, result = Path(directory) / 'reference', Path(directory) / 'result'
            for side, folder in enumerate((reference, result)):
                folder.mkdir()
                for key, pair in context.items():
                    (folder / key).mkdir()
                    (folder / key / 'output.json').write_text(json.dumps(pair[side]))
                (folder / 'assessment_report').mkdir()
                (folder / 'assessment_report/output.json').write_text(json.dumps((left, right)[side]))
            (reference / 'state.json').write_text(json.dumps({'settings': {'mse': True}}))
            self.assertEqual(verify(reference, result, job='assessment_report'), 1)
            (result / 'assessment_b2/output.json').unlink()
            with self.assertRaisesRegex(ValueError, 'Missing direct assessment context'):
                verify(reference, result, job='assessment_report')
