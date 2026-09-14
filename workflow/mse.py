"""Small closed-loop MSE using assessment-conditioned, age-structured stocks.

The observation-based rules are illustrative, not adopted management procedures.
All rules face the same random recruitment and observation errors in each trial.
"""
import copy
import hashlib
import json
import math
import random
from statistics import mean, median

from .age_model import MATURITY, SELECTIVITY, WEIGHT, catch_fraction, fishing_mortality, trajectory

CASES = ('assessment_a1', 'assessment_a2', 'assessment_b1', 'assessment_b2')
RULES = {
    'constant': {'name': 'Constant catch', 'description': 'Keep catch at its recent mean.'},
    'index': {'name': 'Index rule', 'description': 'Adjust catch in proportion to the three-year mean observed index.'},
    'buffered': {'name': 'Buffered rule', 'description': 'Use 80% of the index-based catch, limiting annual advice changes to 15%.'},
}
ASSUMPTIONS = {
    'seed': 20260915, 'years': 15, 'replicates': 20,
    'recruitment_cv': 0.35, 'observation_cv': 0.15,
    'index_window': 3, 'maximum_catch_multiple': 2.0,
    'buffer': 0.8, 'annual_change_limit': 0.15,
    'maximum_fishing_mortality': 2.0, 'depletion_threshold': 0.2,
    'scenarios': [
        {'key': 'baseline', 'name': 'Baseline recruitment', 'recruitment_multiplier': 1.0},
        {'key': 'lower', 'name': 'Lower recruitment', 'recruitment_multiplier': 0.7},
    ],
}


def spawning(numbers):
    return sum(n * w * m for n, w, m in zip(numbers, WEIGHT, MATURITY))


def advance(numbers, mortality, fishing, recruitment):
    """Survive the fishing year, age survivors, retain the plus group, then recruit."""
    survivors = [n * math.exp(-mortality - fishing * s)
                 for n, s in zip(numbers, SELECTIVITY)]
    following = [recruitment, *survivors[:-1]]
    following[-1] += survivors[-1]
    return following


def prepare(assessments):
    """Retain four fitted cases and reconstruct their first future-year states."""
    if set(assessments) != set(CASES):
        raise ValueError('MSE preparation requires all four assessment cases.')
    operating_models = []
    for key in CASES:
        result = assessments[key]
        rows = result['series']
        if not all(math.isfinite(result[field]) and result[field] > 0
                   for field in ('B0', 'M', 'q', 'recruitment')):
            raise ValueError('Operating-model biomass, mortality, catchability and recruitment must be positive and finite.')
        if len(rows) < 3 or any(b['year'] != a['year'] + 1 for a, b in zip(rows, rows[1:])):
            raise ValueError('MSE preparation requires consecutive annual assessment inputs.')
        if not all(math.isfinite(row['catch_t']) and row['catch_t'] >= 0 for row in rows):
            raise ValueError('MSE preparation requires non-negative finite annual catches.')
        fitted = trajectory(result['B0'], result['M'], [row['catch_t'] for row in rows])
        if fitted is None:
            raise ValueError('The assessment has no feasible terminal stock state.')
        if not math.isclose(fitted['R0'], result['recruitment'], rel_tol=1e-8):
            raise ValueError('The assessment recruitment and reconstructed stock do not agree.')
        indices = [row['observed_index'] for row in rows[-3:]]
        if not all(math.isfinite(value) and value > 0 for value in indices):
            raise ValueError('The reference CPUE indices must be positive and finite.')
        final = fitted['rows'][-1]
        numbers = advance(final['numbers'], result['M'], final['F'], fitted['R0'])
        operating_models.append({
            'case': key, 'name': 'Assessment ' + key[-2:].upper(),
            'first_year': rows[-1]['year'] + 1, 'numbers': numbers,
            'M': result['M'], 'B0': fitted['B0'], 'SB0': fitted['SB0'],
            'q': result['q'], 'recruitment': fitted['R0'],
            'reference_catch_t': mean(row['catch_t'] for row in rows[-3:]),
            'reference_index': mean(indices), 'recent_indices': indices,
            'boundary_fit': result.get('boundary_fit', False),
        })
    if len({model['first_year'] for model in operating_models}) != 1:
        raise ValueError('The MSE cases must end in the same assessment year.')
    return {'operating_models': operating_models, 'assumptions': copy.deepcopy(ASSUMPTIONS),
            'rules': copy.deepcopy(RULES),
            'objectives': ['Compare catches', 'Avoid low spawning biomass', 'Limit catch changes'],
            'scope': 'Illustrative closed-loop MSE; no management advice.',
            'limitations': ['Fixed biology and selectivity; no spatial structure.',
                            'Future recruitment varies around a fixed scenario mean, without a stock–recruitment relationship.',
                            'Index-based rules use noisy observations; no assessment is refitted during the simulations.',
                            'The cases and scenarios have equal weight for comparison, not estimated probabilities.']}


def catch_advice(rule, recent_indices, reference_index, reference_catch, previous_catch,
                 assumptions):
    """The decision sees observed indices and past advice, not the true stock."""
    if rule not in RULES:
        raise ValueError('Unknown MSE management rule.')
    if rule == 'constant':
        return reference_catch
    ratio = mean(recent_indices[-assumptions['index_window']:]) / reference_index
    proposed = reference_catch * min(assumptions['maximum_catch_multiple'], max(0.0, ratio))
    if rule == 'buffered':
        proposed *= assumptions['buffer']
        change = assumptions['annual_change_limit']
        proposed = min(previous_catch * (1 + change), max(previous_catch * (1 - change), proposed))
    return proposed


def _errors(seed, years, recruitment_cv, observation_cv):
    generator = random.Random(seed)
    def multiplier(cv):
        sigma = math.sqrt(math.log1p(cv * cv))
        return math.exp(generator.gauss(0, sigma) - sigma * sigma / 2)
    return [(multiplier(recruitment_cv), multiplier(observation_cv)) for _ in range(years)]


def trial(model, rule, scenario, assumptions, errors):
    """Observe, decide, apply feasible catch, update the stock, and repeat."""
    numbers = model['numbers'][:]
    recent = model['recent_indices'][:]
    previous_advice = model['reference_catch_t']
    rows = []
    for offset, (recruitment_error, observation_error) in enumerate(errors):
        vulnerable = sum(n * w * s for n, w, s in zip(numbers, WEIGHT, SELECTIVITY))
        observed = model['q'] * vulnerable * observation_error
        recent.append(observed)
        requested = catch_advice(rule, recent, model['reference_index'],
                                 model['reference_catch_t'], previous_advice, assumptions)
        maximum = vulnerable * catch_fraction(assumptions['maximum_fishing_mortality'], model['M'])
        realised = min(requested, maximum)
        fishing = fishing_mortality(realised, vulnerable, model['M']) if vulnerable > 0 else 0.0
        if fishing is None:
            raise ValueError('The simulated catch has no feasible fishing mortality.')
        recruitment = model['recruitment'] * scenario['recruitment_multiplier'] * recruitment_error
        following = advance(numbers, model['M'], fishing, recruitment)
        rows.append({
            'year': model['first_year'] + offset, 'observed_index': observed,
            'index_ratio': mean(recent[-assumptions['index_window']:]) / model['reference_index'],
            'requested_catch_t': requested, 'catch_t': realised, 'F': fishing,
            'vulnerable_biomass_t': vulnerable, 'recruitment': recruitment,
            'start_SB_over_SB0': spawning(numbers) / model['SB0'],
            'SB_over_SB0': spawning(following) / model['SB0'],
            'catch_shortfall_t': requested - realised,
        })
        numbers = following
        previous_advice = requested
    catches = [model['reference_catch_t'], *[row['catch_t'] for row in rows]]
    change = sum(abs(b - a) for a, b in zip(catches, catches[1:]))
    return {'rows': rows, 'final_numbers': numbers,
            'mean_catch_t': mean(catches[1:]),
            'final_SB_over_SB0': rows[-1]['SB_over_SB0'],
            'below_threshold': any(min(row['start_SB_over_SB0'], row['SB_over_SB0']) <
                                   assumptions['depletion_threshold'] for row in rows),
            'catch_change_percent': 100 * change / max(sum(catches[1:]), 1e-12),
            'shortfall_years': sum(row['catch_shortfall_t'] > 1e-8 for row in rows)}


def _metrics(trials):
    return {'trials': len(trials),
            'mean_catch_t': mean(row['mean_catch_t'] for row in trials),
            'final_SB_over_SB0': median(row['final_SB_over_SB0'] for row in trials),
            'below_threshold_percent': 100 * mean(row['below_threshold'] for row in trials),
            'catch_change_percent': mean(row['catch_change_percent'] for row in trials),
            'shortfall_trials': sum(row['shortfall_years'] > 0 for row in trials)}


def simulate(prepared, rule):
    """Test one rule against paired stochastic trials, preserving compact results."""
    rule = rule.removeprefix('mse_')
    if rule not in RULES:
        raise ValueError('Unknown MSE management rule.')
    assumptions = prepared['assumptions']
    trials, paths = [], []
    example = None
    for case_number, model in enumerate(prepared['operating_models']):
        for scenario_number, scenario in enumerate(assumptions['scenarios']):
            for replicate in range(assumptions['replicates']):
                seed = assumptions['seed'] + case_number * 10000 + scenario_number * 1000 + replicate
                errors = _errors(seed, assumptions['years'], assumptions['recruitment_cv'],
                                 assumptions['observation_cv'])
                result = trial(model, rule, scenario, assumptions, errors)
                paths.append(result['rows'])
                trials.append({key: value for key, value in result.items()
                               if key not in ('rows', 'final_numbers')})
                trials[-1].update(case=model['case'], scenario=scenario['key'],
                                  replicate=replicate + 1, seed=seed,
                                  random_stream=hashlib.sha256(json.dumps(
                                      random.Random(seed).getstate(), separators=(',', ':')
                                  ).encode()).hexdigest())
                if example is None:
                    example = {'case': model['name'], 'scenario': scenario['name'],
                               'replicate': replicate + 1, 'seed': seed, 'rows': result['rows']}
    annual = []
    for offset in range(assumptions['years']):
        rows = [path[offset] for path in paths]
        annual.append({'year': rows[0]['year'],
                       'catch_t': median(row['catch_t'] for row in rows),
                       'SB_over_SB0': median(row['SB_over_SB0'] for row in rows)})
    cases = []
    for model in prepared['operating_models']:
        for scenario in assumptions['scenarios']:
            selected = [row for row in trials if row['case'] == model['case']
                        and row['scenario'] == scenario['key']]
            cases.append({'case': model['name'], 'scenario': scenario['name'], **_metrics(selected)})
    return {'rule': rule, 'name': RULES[rule]['name'], 'description': RULES[rule]['description'],
            'assumptions': copy.deepcopy(assumptions), 'metrics': _metrics(trials),
            'series': annual, 'cases': cases, 'trials': trials, 'example': example,
            'operating_models': copy.deepcopy(prepared['operating_models']),
            'limitations': prepared['limitations'], 'scope': prepared['scope'],
            'boundary_cases': [model['name'] for model in prepared['operating_models']
                               if model['boundary_fit']]}


def summarise(results):
    """Combine completed rules without rerunning or selecting a preferred rule."""
    by_rule = {result['rule']: result for result in results.values()}
    if len(results) != len(RULES) or set(by_rule) != set(RULES):
        raise ValueError('MSE comparison requires each of the three management rules.')
    first = by_rule['constant']
    paired = [(row['case'], row['scenario'], row['replicate'], row['seed'], row['random_stream'])
              for row in first['trials']]
    for result in by_rule.values():
        if (result['assumptions'] != first['assumptions'] or
                result['operating_models'] != first['operating_models'] or paired != [
            (row['case'], row['scenario'], row['replicate'], row['seed'], row['random_stream'])
            for row in result['trials']]):
            raise ValueError('The MSE rules do not use the same operating models, scenarios and random trials.')
    return {'series': {by_rule[rule]['name']: by_rule[rule]['series'] for rule in RULES},
            'metrics': [{'rule': rule, 'name': by_rule[rule]['name'], **by_rule[rule]['metrics']}
                        for rule in RULES],
            'cases': [{'rule': by_rule[rule]['name'], **row}
                      for rule in RULES for row in by_rule[rule]['cases']],
            'assumptions': copy.deepcopy(first['assumptions']), 'rules': copy.deepcopy(RULES),
            'operating_models': copy.deepcopy(first['operating_models']),
            'limitations': first['limitations'], 'boundary_cases': first['boundary_cases'],
            'scope': first['scope']}
