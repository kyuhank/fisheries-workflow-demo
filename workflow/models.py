"""Small deterministic calculations used by the browser and command-line demo."""
import math

from .age_model import fit


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
    return {'series': [{'year': source['year'], 'SB_over_SB0': row['SB_over_SB0'],
                       'F': row['F']} for source, row in zip(inputs, result['rows'])],
            'M': mortality, 'boundary_fit': result['boundary_fit'],
            'B0': result['B0'], 'q': result['q']}
