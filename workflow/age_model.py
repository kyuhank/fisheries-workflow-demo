"""Small annual age-structured model with fixed biology and constant recruitment."""
import math

AGES = list(range(11))  # Age 10 contains ages 10 and older.
WEIGHT = [0.1 * (1 - math.exp(-0.25 * (age + 1))) ** 3 for age in AGES]  # tonnes
SELECTIVITY = [float(age >= 2) for age in AGES]
MATURITY = [float(age >= 3) for age in AGES]


def equilibrium(recruitment, mortality):
    numbers = [recruitment * math.exp(-mortality * age) for age in AGES]
    numbers[-1] /= -math.expm1(-mortality)
    return numbers


def catch_fraction(fishing, mortality):
    total = fishing + mortality
    return fishing / total * -math.expm1(-total)


def fishing_mortality(catch, vulnerable, mortality):
    if catch < 0 or vulnerable <= 0 or catch >= vulnerable:
        return None
    if catch == 0:
        return 0.0
    target = catch / vulnerable
    lo, hi = 0.0, 1.0
    while catch_fraction(hi, mortality) < target:
        hi *= 2
        if hi > 1024:
            return None
    for _ in range(40):
        mid = (lo + hi) / 2
        if catch_fraction(mid, mortality) < target:
            lo = mid
        else:
            hi = mid
    return (lo + hi) / 2


def trajectory(unfished_biomass, mortality, catches):
    per_recruit = equilibrium(1.0, mortality)
    recruitment = unfished_biomass / sum(n * w for n, w in zip(per_recruit, WEIGHT))
    numbers = [n * recruitment for n in per_recruit]
    spawning0 = sum(n * w * m for n, w, m in zip(numbers, WEIGHT, MATURITY))
    rows = []
    for catch in catches:
        vulnerable = sum(n * w * s for n, w, s in zip(numbers, WEIGHT, SELECTIVITY))
        fishing = fishing_mortality(catch, vulnerable, mortality)
        if fishing is None:
            return None
        biomass = sum(n * w for n, w in zip(numbers, WEIGHT))
        spawning = sum(n * w * m for n, w, m in zip(numbers, WEIGHT, MATURITY))
        rows.append({'biomass': biomass, 'spawning_biomass': spawning,
                     'SB_over_SB0': spawning / spawning0, 'vulnerable_biomass': vulnerable,
                     'F': fishing, 'numbers': numbers[:]})
        natural_survival, fished_survival = math.exp(-mortality), math.exp(-mortality - fishing)
        survivors = [n * (fished_survival if s else natural_survival)
                     for n, s in zip(numbers, SELECTIVITY)]
        numbers = [recruitment, *survivors[:-1]]
        numbers[-1] += survivors[-1]
    return {'R0': recruitment, 'B0': unfished_biomass, 'SB0': spawning0, 'rows': rows}


def fit(indices, catches, mortality):
    logs = [math.log(value) for value in indices]
    lower, upper = max(1.0, max(catches) * 1.1), max(100000.0, max(catches) * 500)
    def objective(log_biomass):
        result = trajectory(math.exp(log_biomass), mortality, catches)
        if result is None:
            return 1e30
        predicted = [math.log(row['vulnerable_biomass']) for row in result['rows']]
        logq = sum(i - p for i, p in zip(logs, predicted)) / len(logs)
        return sum((i - logq - p) ** 2 for i, p in zip(logs, predicted))
    grid = [math.log(lower) + i / 48 * math.log(upper / lower) for i in range(49)]
    best = min(range(len(grid)), key=lambda i: objective(grid[i]))
    lo, hi = grid[max(0, best - 1)], grid[min(len(grid) - 1, best + 1)]
    ratio = (math.sqrt(5) - 1) / 2
    a, b = hi - ratio * (hi - lo), lo + ratio * (hi - lo)
    fa, fb = objective(a), objective(b)
    for _ in range(75):
        if hi - lo < 1e-9:
            break
        if fa < fb:
            hi, b, fb = b, a, fa
            a = hi - ratio * (hi - lo); fa = objective(a)
        else:
            lo, a, fa = a, b, fb
            b = lo + ratio * (hi - lo); fb = objective(b)
    estimate = (lo + hi) / 2
    result = trajectory(math.exp(estimate), mortality, catches)
    if result is None or objective(estimate) >= 1e29:
        raise ValueError('No feasible age-structured fit')
    result['q'] = math.exp(sum(i - math.log(row['vulnerable_biomass'])
                              for i, row in zip(logs, result['rows'])) / len(logs))
    result['log_index_SSE'] = objective(estimate)
    result['boundary_fit'] = result['B0'] <= lower * 1.001 or result['B0'] >= upper / 1.001
    return result
