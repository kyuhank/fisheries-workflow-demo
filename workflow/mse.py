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
from .spec import DEFAULTS

CASES = ('assessment_a1', 'assessment_a2', 'assessment_b1', 'assessment_b2')
RULES = {
    'constant': {'name': 'Constant catch', 'description': 'Keep catch at its recent mean.'},
    'index': {'name': 'Index rule', 'description': 'Adjust catch in proportion to the three-year mean observed index.'},
    'buffered': {'name': 'Buffered rule', 'description': 'Set a stepped catch target from the observed index, apply the selected buffer, then limit annual advice changes.'},
}
ASSUMPTIONS = {
    'seed': 20260915, 'years': 15, 'replicates': 20,
    'recruitment_cv': 0.35, 'observation_cv': 0.15,
    'index_window': 3, 'maximum_catch_multiple': 2.0,
    'annual_change_limit': 0.15,
    'buffered_steps': {'thresholds': [0.8, 1.1], 'multipliers': [0.5, 1.0, 1.25]},
    'maximum_fishing_mortality': 2.0, 'depletion_threshold': 0.2,
    'example_trial': {'case': 'assessment_a1', 'scenario': 'lower', 'replicate': 1},
    'scenarios': [
        {'key': 'baseline', 'name': 'Baseline recruitment', 'recruitment_multiplier': 1.0},
        {'key': 'lower', 'name': 'Recruitment dip and recovery',
         'recruitment_multipliers': [0.5] * 6 + [1.0] * 9},
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
                            'Future recruitment varies around declared annual scenario means, without a stock–recruitment relationship.',
                            'Index-based rules use noisy observations; no assessment is refitted during the simulations.',
                            'The cases and scenarios have equal weight for comparison, not estimated probabilities.']}


def catch_decision(rule, recent_indices, reference_index, reference_catch, previous_catch,
                   assumptions):
    """The decision sees observed indices and past advice, not the true stock."""
    if rule not in RULES:
        raise ValueError('Unknown MSE management rule.')
    ratio = mean(recent_indices[-assumptions['index_window']:]) / reference_index
    band = 'proportional'
    target = reference_catch * min(assumptions['maximum_catch_multiple'], max(0.0, ratio))
    if rule == 'constant':
        target, band = reference_catch, 'constant'
    if rule == 'buffered':
        # Prepared inputs from earlier versions retain their proportional rule.
        steps = assumptions.get('buffered_steps')
        if steps:
            position = sum(ratio >= threshold for threshold in steps['thresholds'])
            target = reference_catch * steps['multipliers'][position]
            band = ('low', 'middle', 'high')[position]
        target *= assumptions.get('buffer', DEFAULTS['mse_buffer'])
        change = assumptions['annual_change_limit']
        requested = min(previous_catch * (1 + change), max(previous_catch * (1 - change), target))
    else:
        requested = target
    return {'index_ratio': ratio, 'target_catch_t': target,
            'requested_catch_t': requested, 'decision_band': band}


def catch_advice(rule, recent_indices, reference_index, reference_catch, previous_catch,
                 assumptions):
    return catch_decision(rule, recent_indices, reference_index, reference_catch,
                          previous_catch, assumptions)['requested_catch_t']


def recruitment_profile(scenario, years):
    """Expand a recorded scenario, also accepting earlier constant-mean inputs."""
    profile = scenario.get('recruitment_multipliers')
    if profile is None:
        profile = [scenario['recruitment_multiplier']] * years
    if len(profile) != years or not all(type(value) in (int, float) and
                                        math.isfinite(value) and value >= 0 for value in profile):
        raise ValueError('Recruitment scenarios need one non-negative finite multiplier per future year.')
    return profile


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
    profile = recruitment_profile(scenario, assumptions['years'])
    if len(errors) != assumptions['years']:
        raise ValueError('Each trial needs recruitment and observation errors for every future year.')
    rows = []
    for offset, (recruitment_error, observation_error) in enumerate(errors):
        vulnerable = sum(n * w * s for n, w, s in zip(numbers, WEIGHT, SELECTIVITY))
        observed = model['q'] * vulnerable * observation_error
        recent.append(observed)
        decision = catch_decision(rule, recent, model['reference_index'],
                                  model['reference_catch_t'], previous_advice, assumptions)
        requested = decision['requested_catch_t']
        maximum = vulnerable * catch_fraction(assumptions['maximum_fishing_mortality'], model['M'])
        realised = min(requested, maximum)
        fishing = fishing_mortality(realised, vulnerable, model['M']) if vulnerable > 0 else 0.0
        if fishing is None:
            raise ValueError('The simulated catch has no feasible fishing mortality.')
        recruitment = model['recruitment'] * profile[offset] * recruitment_error
        following = advance(numbers, model['M'], fishing, recruitment)
        rows.append({
            'year': model['first_year'] + offset, 'observed_index': observed,
            **decision, 'catch_t': realised, 'F': fishing,
            'vulnerable_biomass_t': vulnerable, 'recruitment': recruitment,
            'recruitment_multiplier': profile[offset],
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


def _annual(paths):
    fields = ('catch_t', 'SB_over_SB0', 'start_SB_over_SB0', 'index_ratio',
              'target_catch_t', 'requested_catch_t', 'recruitment_multiplier')
    return [{'year': rows[0]['year'],
             **{field: median(row[field] for row in rows) for field in fields}}
            for rows in zip(*paths)]


def simulate(prepared, rule, buffer=None):
    """Test one rule against paired stochastic trials, preserving compact results."""
    rule = rule.removeprefix('mse_')
    if rule not in RULES:
        raise ValueError('Unknown MSE management rule.')
    if buffer is not None and (rule != 'buffered' or type(buffer) not in (int, float)
                               or buffer not in (0.6, 0.8, 1.0)):
        raise ValueError('Select one of the supplied Buffered rule catch fractions.')
    # Common trial conditions stay independent of the setting of any one MP.
    assumptions = copy.deepcopy(prepared['assumptions'])
    legacy_buffer = assumptions.pop('buffer', DEFAULTS['mse_buffer'])
    rule_settings = {'buffer': legacy_buffer if buffer is None else buffer} if rule == 'buffered' else {}
    effective = {**assumptions, **rule_settings}
    description = RULES[rule]['description']
    if rule == 'buffered':
        description = (f'Use {100 * rule_settings["buffer"]:g}% of index-based catch advice, '
                       f'limiting annual advice changes to {100 * assumptions["annual_change_limit"]:g}%.')
        if assumptions.get('buffered_steps'):
            description = ('Set a stepped catch target from the observed index, '
                           f'apply the {100 * rule_settings["buffer"]:g}% buffer, then limit '
                           f'annual advice changes to {100 * assumptions["annual_change_limit"]:g}%.')
    trials, paths = [], []
    example = None
    selection = assumptions.get('example_trial')
    for case_number, model in enumerate(prepared['operating_models']):
        for scenario_number, scenario in enumerate(assumptions['scenarios']):
            for replicate in range(assumptions['replicates']):
                seed = assumptions['seed'] + case_number * 10000 + scenario_number * 1000 + replicate
                errors = _errors(seed, assumptions['years'], assumptions['recruitment_cv'],
                                 assumptions['observation_cv'])
                result = trial(model, rule, scenario, effective, errors)
                paths.append(result['rows'])
                trials.append({key: value for key, value in result.items()
                               if key not in ('rows', 'final_numbers')})
                trials[-1].update(case=model['case'], scenario=scenario['key'],
                                  replicate=replicate + 1, seed=seed,
                                  random_stream=hashlib.sha256(json.dumps(
                                      random.Random(seed).getstate(), separators=(',', ':')
                                  ).encode()).hexdigest())
                selected = (selection == {'case': model['case'], 'scenario': scenario['key'],
                                          'replicate': replicate + 1})
                if selected or (selection is None and example is None):
                    example = {'case': model['name'], 'scenario': scenario['name'],
                               'case_key': model['case'], 'scenario_key': scenario['key'],
                               'replicate': replicate + 1, 'seed': seed, 'rows': result['rows'],
                               'reference_catch_t': model['reference_catch_t'],
                               'reference_index': model['reference_index'],
                               'selection': 'Specified before simulation; the same trial is shown for every rule.'}
    if example is None:
        raise ValueError('The specified example trial is not among the simulated trials.')
    annual = [{key: row[key] for key in ('year', 'catch_t', 'SB_over_SB0')}
              for row in _annual(paths)]
    scenarios = []
    for scenario in assumptions['scenarios']:
        selected = [(row, path) for row, path in zip(trials, paths)
                    if row['scenario'] == scenario['key']]
        scenarios.append({'key': scenario['key'], 'name': scenario['name'],
                          'series': _annual([path for _, path in selected]),
                          'metrics': _metrics([row for row, _ in selected])})
    cases = []
    for model in prepared['operating_models']:
        for scenario in assumptions['scenarios']:
            selected = [row for row in trials if row['case'] == model['case']
                        and row['scenario'] == scenario['key']]
            cases.append({'case': model['name'], 'scenario': scenario['name'], **_metrics(selected)})
    return {'rule': rule, 'name': RULES[rule]['name'], 'description': description,
            'rule_settings': rule_settings,
            'assumptions': copy.deepcopy(assumptions), 'metrics': _metrics(trials),
            'series': annual, 'scenarios': scenarios,
            'cases': cases, 'trials': trials, 'example': example,
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
    summary = {'series': {by_rule[rule]['name']: by_rule[rule]['series'] for rule in RULES},
            'metrics': [{'rule': rule, 'name': by_rule[rule]['name'], **by_rule[rule]['metrics']}
                        for rule in RULES],
            'cases': [{'rule': by_rule[rule]['name'], **row}
                      for rule in RULES for row in by_rule[rule]['cases']],
            'assumptions': copy.deepcopy(first['assumptions']),
            'rules': {rule: {'name': by_rule[rule]['name'], 'description': by_rule[rule]['description'],
                             'settings': copy.deepcopy(by_rule[rule]['rule_settings'])} for rule in RULES},
            'operating_models': copy.deepcopy(first['operating_models']),
            'limitations': first['limitations'], 'boundary_cases': first['boundary_cases'],
            'scope': first['scope']}
    # Old completed MP outputs remain readable without inventing missing paths.
    if all('scenarios' in result for result in by_rule.values()):
        identities = [(row['key'], row['name']) for row in first['scenarios']]
        selected = {key: first['example'][key]
                    for key in ('case_key', 'scenario_key', 'replicate', 'seed')}
        for result in by_rule.values():
            if ([(row['key'], row['name']) for row in result['scenarios']] != identities or
                    any(result['example'][key] != value for key, value in selected.items())):
                raise ValueError('The MSE comparison requires matching scenarios and example trials.')
        summary['scenarios'] = [
            {'key': key, 'name': name,
             'series': {by_rule[rule]['name']: copy.deepcopy(by_rule[rule]['scenarios'][i]['series'])
                        for rule in RULES},
             'metrics': [{'rule': rule, 'name': by_rule[rule]['name'],
                          **by_rule[rule]['scenarios'][i]['metrics']} for rule in RULES]}
            for i, (key, name) in enumerate(identities)]
        summary['examples'] = {by_rule[rule]['name']: copy.deepcopy(by_rule[rule]['example'])
                               for rule in RULES}
    return summary
