"""Numerical and reporting checks for the illustrative closed-loop MSE."""
import copy
import hashlib
import json
import math
import random
import unittest
from statistics import mean, median

from workflow import age_model, mse
from workflow.reports import output_page


def assessment_cases():
    assessments = {}
    catches = [450 + 30 * year for year in range(10)]
    for key, biomass, mortality in zip(mse.CASES, [20000, 26000, 24000, 30000], [.2, .3, .2, .3]):
        fit = age_model.trajectory(biomass, mortality, catches)
        q = 1 / fit['rows'][0]['vulnerable_biomass']
        assessments[key] = {'B0': biomass, 'M': mortality, 'q': q,
                            'recruitment': fit['R0'], 'boundary_fit': False,
                            'series': [{'year': 2000 + year, 'catch_t': catch,
                                        'observed_index': q * row['vulnerable_biomass']}
                                       for year, (catch, row) in enumerate(zip(catches, fit['rows']))]}
    return assessments


class MSETest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.assessments = assessment_cases()
        cls.prepared = mse.prepare(cls.assessments)
        cls.results = {rule: mse.simulate(cls.prepared, rule) for rule in mse.RULES}
        cls.summary = mse.summarise(cls.results)

    def test_first_future_state_applies_terminal_catch_exactly_once(self):
        for model in self.prepared['operating_models']:
            original = self.assessments[model['case']]
            catches = [row['catch_t'] for row in original['series']]
            continued = age_model.trajectory(model['B0'], model['M'], catches + [0])
            self.assertEqual(model['first_year'], 2010)
            self.assertEqual(model['numbers'], continued['rows'][-1]['numbers'])
            self.assertEqual(model['SB0'], continued['SB0'])
            self.assertNotEqual(model['numbers'], continued['rows'][-2]['numbers'])

    def test_plus_group_survives_and_new_recruits_enter_once(self):
        numbers = list(range(1, 12))
        following = mse.advance(numbers, .2, .1, 100)
        self.assertEqual(following[0], 100)
        self.assertAlmostEqual(following[1], numbers[0] * math.exp(-.2))
        self.assertAlmostEqual(following[-1], (numbers[-2] + numbers[-1]) * math.exp(-.3))
        survivors = sum(n * math.exp(-.2 - .1 * s)
                        for n, s in zip(numbers, age_model.SELECTIVITY))
        self.assertAlmostEqual(sum(following), 100 + survivors)

    def test_rules_use_observed_information_and_feedback_changes_later_observations(self):
        a = self.prepared['assumptions']
        self.assertEqual(mse.catch_advice('constant', [0.1] * 3, 1, 100, 100, a), 100)
        self.assertEqual(mse.catch_advice('index', [.5] * 3, 1, 100, 100, a), 50)
        self.assertEqual(mse.catch_advice('index', [10] * 3, 1, 100, 100, a), 200)
        self.assertEqual(mse.catch_advice('buffered', [.1] * 3, 1, 100, 100, a), 85)
        model = self.prepared['operating_models'][0]
        scenario = a['scenarios'][0]
        constant = mse.trial(model, 'constant', scenario, a, [(1, 1)] * 15)
        adaptive = mse.trial(model, 'buffered', scenario, a, [(1, 1)] * 15)
        self.assertEqual(constant['rows'][0]['observed_index'], adaptive['rows'][0]['observed_index'])
        self.assertNotEqual(constant['rows'][0]['catch_t'], adaptive['rows'][0]['catch_t'])
        self.assertNotEqual(constant['rows'][1]['observed_index'], adaptive['rows'][1]['observed_index'])
        self.assertNotEqual(constant['final_numbers'], adaptive['final_numbers'])
        altered = mse.trial(model, 'index', scenario, a, [(1, .5)] * 15)
        unaltered = mse.trial(model, 'index', scenario, a, [(1, 1)] * 15)
        self.assertLess(altered['rows'][0]['requested_catch_t'], unaltered['rows'][0]['requested_catch_t'])

    def test_overlarge_advice_is_limited_to_feasible_catch_and_recorded(self):
        model = copy.deepcopy(self.prepared['operating_models'][0])
        model['reference_catch_t'] = model['B0'] * 10
        a = self.prepared['assumptions']
        result = mse.trial(model, 'constant', a['scenarios'][1], a, [(.7, 1)] * a['years'])
        self.assertTrue(all(number >= 0 and math.isfinite(number) for number in result['final_numbers']))
        self.assertEqual(result['shortfall_years'], a['years'])
        for row in result['rows']:
            self.assertLess(row['catch_t'], row['vulnerable_biomass_t'])
            self.assertLessEqual(row['F'], a['maximum_fishing_mortality'] + 1e-9)
            realised = row['vulnerable_biomass_t'] * age_model.catch_fraction(row['F'], model['M'])
            self.assertAlmostEqual(row['catch_t'], realised, delta=max(1, row['catch_t']) * 1e-8)
            self.assertAlmostEqual(row['catch_t'] + row['catch_shortfall_t'], row['requested_catch_t'])
            self.assertGreaterEqual(row['SB_over_SB0'], 0)

    def test_paired_trials_are_deterministic_and_have_recorded_recruitment_scenarios(self):
        repeated = mse.simulate(self.prepared, 'index')
        self.assertEqual(repeated, self.results['index'])
        signatures = lambda result: [(t['seed'], t['random_stream']) for t in result['trials']]
        for result in self.results.values():
            self.assertEqual(len(result['trials']), 4 * 2 * 20)
            self.assertEqual(signatures(result), signatures(repeated))
            self.assertEqual({t['scenario'] for t in result['trials']}, {'baseline', 'lower'})
            self.assertEqual(len(result['series']), 15)
            json.dumps(result, allow_nan=False)
        self.assertEqual(self.prepared, mse.prepare(self.assessments))
        first = repeated['trials'][0]
        state = json.dumps(random.Random(first['seed']).getstate(), separators=(',', ':'))
        self.assertEqual(first['random_stream'], hashlib.sha256(state.encode()).hexdigest())
        self.assertNotIn('.', state)

    def test_metrics_match_trials_and_stock_state(self):
        for result in self.results.values():
            trials, metric = result['trials'], result['metrics']
            self.assertEqual(metric['mean_catch_t'], mean(t['mean_catch_t'] for t in trials))
            self.assertEqual(metric['final_SB_over_SB0'], median(t['final_SB_over_SB0'] for t in trials))
            self.assertEqual(metric['below_threshold_percent'], 100 * mean(t['below_threshold'] for t in trials))
            self.assertEqual(metric['shortfall_trials'], sum(t['shortfall_years'] > 0 for t in trials))
        model = self.prepared['operating_models'][0]
        a = self.prepared['assumptions']
        result = mse.trial(model, 'index', a['scenarios'][0], a, [(1, 1)] * 15)
        catches = [model['reference_catch_t'], *[r['catch_t'] for r in result['rows']]]
        expected_change = 100 * sum(abs(b - c) for c, b in zip(catches, catches[1:])) / sum(catches[1:])
        self.assertEqual(result['catch_change_percent'], expected_change)
        self.assertEqual(result['final_SB_over_SB0'], mse.spawning(result['final_numbers']) / model['SB0'])

    def test_comparison_rejects_mismatched_trials_or_missing_rules(self):
        with self.assertRaisesRegex(ValueError, 'three management rules'):
            mse.summarise({'constant': self.results['constant']})
        results = copy.deepcopy(self.results)
        results['index']['trials'][0]['random_stream'] = 'different'
        with self.assertRaisesRegex(ValueError, 'same operating models, scenarios and random trials'):
            mse.summarise(results)
        results = copy.deepcopy(self.results)
        results['index']['operating_models'][0]['numbers'][2] += 1
        with self.assertRaisesRegex(ValueError, 'same operating models'):
            mse.summarise(results)
        invalid = copy.deepcopy(self.assessments)
        invalid['assessment_a1']['series'][-1]['year'] += 1
        with self.assertRaisesRegex(ValueError, 'consecutive annual'):
            mse.prepare(invalid)

    def page(self, key, result):
        return output_page({'key': key, 'title': key, 'description': 'Compare management rules.'},
                           result, {'run_id': 'Run 004'},
                           [{'job': 'Assessment A1', 'run_id': 'Run 001', 'checksum': 'a' * 64}])

    def test_outputs_include_preparation_rule_summary_and_distinct_written_report(self):
        preparation = self.page('mse_prepare', self.prepared)
        rule = self.page('mse_index', self.results['index'])
        summary = self.page('mse_summary', self.summary)
        report = self.page('mse_report', self.summary)
        self.assertIn('Four assessment cases', preparation)
        self.assertIn('Follow one trial', rule)
        self.assertIn('Requested catch', rule)
        self.assertIn('Realised catch', rule)
        self.assertNotIn('narrative-report', summary)
        self.assertIn('data-report="mse_report"', report)
        self.assertIn('<h2>Methods</h2>', report)
        self.assertIn('<h2>Results</h2>', report)
        self.assertIn('<h2>Interpretation</h2>', report)
        self.assertEqual(summary.count('<svg '), 2)
        self.assertEqual(report.count('<svg '), 1)
        saved = json.loads(json.dumps(self.summary, sort_keys=True))
        saved_report = self.page('mse_report', saved)
        self.assertEqual(report, saved_report)
        for page in (preparation, rule, summary, report):
            self.assertIn('Run 004', page)
            self.assertIn('Assessment A1', page)
            self.assertIn('Run 001', page)
        changed = copy.deepcopy(self.summary)
        changed['metrics'][0]['mean_catch_t'] = 9999
        self.assertIn('9,999 tonnes', self.page('mse_report', changed))


if __name__ == '__main__':
    unittest.main()
