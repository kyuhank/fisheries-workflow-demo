"""Explicit file contracts at the synthetic CPUE/assessment/MSE boundaries."""
import math

CASES = ('assessment_a1', 'assessment_a2', 'assessment_b1', 'assessment_b2')


def number(value, *, positive=False):
    return type(value) in (int, float) and math.isfinite(value) and (value > 0 if positive else value >= 0)


def annual(rows, boundary):
    if not isinstance(rows, list) or len(rows) < 3 or any(not isinstance(row, dict) or type(row.get('year')) not in (int, float) or not math.isfinite(row['year']) or int(row['year']) != row['year'] for row in rows):
        raise ValueError(boundary + ' contract: at least three integer annual rows required')
    years = [row['year'] for row in rows]
    if any(b != a + 1 for a, b in zip(years, years[1:])):
        raise ValueError(boundary + ' contract: consecutive unique years required')
    return years


def validate_transfer(key, parents, records, settings):
    """Validate the actual loaded payload before fitting or preparing simulations."""
    if key in ('prepare_a', 'prepare_b'):
        boundary = 'CPUE-to-assessment'
        cpue_key = 'cpue_' + key[-1]
        series = parents[cpue_key].get('series')
        years = annual(series, boundary)
        catches = parents['extract'].get('catch')
        if not isinstance(catches, list) or any(not isinstance(row, dict) or not number(row.get('catch_t')) for row in catches):
            raise ValueError(boundary + ' contract: finite non-negative catch_t in tonnes required')
        catch_years = [row.get('year') for row in catches]
        if any(type(year) not in (int, float) or not math.isfinite(year) or year != int(year) for year in catch_years):
            raise ValueError(boundary + ' contract: integer catch years required')
        if len(set(catch_years)) != len(catch_years) or not set(years) <= set(catch_years):
            raise ValueError(boundary + ' contract: each CPUE year requires one matching catch year')
        if any(not number(row.get('index'), positive=True) for row in series):
            raise ValueError(boundary + ' contract: finite positive relative CPUE index required')
        if years[-1] != settings['last_year']:
            raise ValueError(boundary + ' contract: CPUE snapshot year differs from required snapshot')
    elif key == 'mse_prepare':
        boundary = 'assessment-to-MSE'
        if set(parents) != set(CASES):
            raise ValueError(boundary + ' contract: exactly four declared assessment cases required')
        endings = []
        for case in CASES:
            fit = parents[case]
            if not isinstance(fit, dict) or any(not number(fit.get(field), positive=True) for field in ('K', 'r', 'q', 'next_biomass_t')) or fit['r'] >= 1:
                raise ValueError(boundary + ' contract: positive finite K/r/q/next_biomass_t and r<1 required: ' + case)
            years = annual(fit.get('series'), boundary)
            if any(not number(row.get('catch_t')) or not number(row.get('observed_index'), positive=True) for row in fit['series']):
                raise ValueError(boundary + ' contract: tonnes and positive relative observed_index required: ' + case)
            endings.append(years[-1])
        if len(set(endings)) != 1 or endings[0] != settings['last_year']:
            raise ValueError(boundary + ' contract: all cases must end in the required snapshot year')
    else:
        return None
    for parent in parents:
        record = records.get(parent)
        if not record or not record.get('run_id') or not record.get('signature') or 'output.json' not in record.get('outputs', {}):
            raise ValueError(boundary + ' contract: producer identity/checksum missing: ' + parent)
    return {'boundary': boundary, 'schema_version': 1,
            'units': {'catch_t': 'tonnes', 'index': 'relative CPUE', 'biomass_t': 'tonnes'},
            'producers': {parent: {'run_id': records[parent]['run_id'], 'signature': records[parent]['signature'], 'checksum': records[parent]['outputs']['output.json'], 'analysis_source': records[parent].get('analysis_source')} for parent in parents}}
