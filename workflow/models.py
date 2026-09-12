"""Small deterministic calculations used by the browser and command-line demo."""
import math

from .age_model import fit


def describe_data(records, catches):
    """Summarise the coverage and composition of a synthetic data snapshot."""
    annual = []
    vessels = sorted({row['vessel'] for row in records})
    catch_by_year = {row['year']: row['catch_t'] for row in catches}
    for year in sorted({row['year'] for row in records}):
        rows = [row for row in records if row['year'] == year]
        hooks = sum(row['hooks'] for row in rows)
        annual.append({'year': year, 'observations': len(rows), 'hooks': hooks,
                       'catch_n': sum(row['catch_n'] for row in rows),
                       'catch_t': catch_by_year[year],
                       'zero_catch_percent': 100 * sum(row['catch_n'] == 0 for row in rows) / len(rows),
                       'vessels': {v: sum(row['vessel'] == v for row in rows) for v in vessels}})
    return {'annual': annual, 'vessels': vessels, 'observations': len(records),
            'fields': [
                {'name':'set_id','meaning':'Unique fishing observation','type':'text'},
                {'name':'year','meaning':'Year of fishing','type':'integer'},
                {'name':'vessel','meaning':'Synthetic vessel identifier','type':'text'},
                {'name':'hooks','meaning':'Fishing effort (hooks)','type':'integer'},
                {'name':'catch_n','meaning':'Catch in number of fish','type':'integer'}]}


def cpue(records, vessel_effect=True, min_hooks=0):
    rows = [r for r in records if r['hooks'] >= min_hooks]
    if not rows or any(r['hooks'] <= 0 or r['catch_n'] < 0 for r in rows):
        raise ValueError('CPUE requires valid catch and positive effort.')
    years = sorted({r['year'] for r in rows})
    vessels = sorted({r['vessel'] for r in rows})
    effort = {(y, v): 0.0 for y in years for v in vessels}
    catch = dict(effort)
    for row in rows:
        key = row['year'], row['vessel']
        effort[key] += row['hooks'] / 1000
        catch[key] += row['catch_n']
    cy = {y: sum(catch[y, v] for v in vessels) for y in years}
    cv = {v: sum(catch[y, v] for y in years) for v in vessels}
    if any(value <= 0 for value in [*cy.values(), *cv.values()]):
        raise ValueError('The illustrative model requires positive group totals.')
    a = {y: cy[y] / sum(effort[y, v] for v in vessels) for y in years}
    b = {v: 1.0 for v in vessels}
    iterations = 0
    if vessel_effect:
        for iterations in range(1, 10001):
            previous = dict(a)
            a = {y: cy[y] / sum(effort[y, v] * b[v] for v in vessels) for y in years}
            b = {v: cv[v] / sum(effort[y, v] * a[y] for y in years) for v in vessels}
            scale = b[vessels[0]]
            a = {y: value * scale for y, value in a.items()}
            b = {v: value / scale for v, value in b.items()}
            if max(abs(math.log(a[y] / previous[y])) for y in years) < 1e-12:
                break
        else:
            raise ValueError('The CPUE fit did not converge.')
    residual = max(abs(sum(effort[y, v] * a[y] * b[v] for v in vessels) / cy[y] - 1)
                   for y in years)
    if residual > 1e-9:
        raise ValueError('The CPUE score check failed.')
    return {'series': [{'year': y, 'index': a[y] / a[years[0]]} for y in years],
            'sets_used': len(rows), 'sets_excluded': len(records) - len(rows),
            'method': 'Year + vessel' if vessel_effect else 'Year only',
            'iterations': iterations, 'score_residual': residual}


def assessment(inputs, mortality):
    result = fit([r['index'] for r in inputs], [r['catch_t'] for r in inputs], mortality)
    from .age_model import catch_fraction
    series = []
    errors = []
    for source, row in zip(inputs, result['rows']):
        predicted = result['q'] * row['vulnerable_biomass']
        model_catch = row['vulnerable_biomass'] * catch_fraction(row['F'], mortality)
        errors.append(abs(model_catch - source['catch_t']) / max(1, source['catch_t']))
        series.append({'year': source['year'], 'observed_index': source['index'],
                       'fitted_index': predicted, 'log_residual': math.log(source['index'] / predicted),
                       'SB_over_SB0': row['SB_over_SB0'], 'F': row['F'],
                       'biomass_t': row['biomass'], 'catch_t': source['catch_t']})
    if max(errors) > 1e-8:
        raise ValueError('The fitted trajectory does not reproduce annual catches.')
    return {'series': series, 'catch_check': 'Pass',
            'M': mortality, 'boundary_fit': result['boundary_fit'],
            'B0': result['B0'], 'q': result['q'], 'recruitment': result['R0']}
