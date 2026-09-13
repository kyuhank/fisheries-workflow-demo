"""Jobs, dependencies and responsibilities shared by all interfaces."""

JOBS = [
    ('submission', 'Data submission', 'data', 'Data provider', [],
     'Submit catch and effort records for checking.'),
    ('qc', 'Quality check', 'data', 'Data curator', ['submission'],
     'Check records and return invalid effort for correction.'),
    ('database', 'Prepare and load', 'data', 'Data curator', ['qc'],
     'Store the accepted records in a fixed database snapshot.'),
    ('extract', 'Extract data', 'data', 'Data analyst', ['database'],
     'Use saved SQL to select observations and annual catches.'),
    ('cpue_a', 'CPUE analysis A', 'cpue', 'CPUE analyst', ['extract'],
     'Fit a CPUE index with year and vessel effects.'),
    ('cpue_b', 'CPUE analysis B', 'cpue', 'CPUE analyst', ['extract'],
     'Fit an alternative index with year effects only.'),
    ('cpue_summary', 'Compare CPUE results', 'cpue', 'CPUE analyst', ['cpue_a', 'cpue_b'],
     'Compare both indices in a plot and table.'),
    ('cpue_report', 'CPUE report', 'cpue', 'CPUE analyst', ['cpue_summary'],
     'Write a short account of the CPUE methods and results.'),
    ('prepare_a', 'Prepare inputs A', 'assessment', 'Assessment analyst', ['extract', 'cpue_a'],
     'Join index A to annual catches and check the model inputs.'),
    ('prepare_b', 'Prepare inputs B', 'assessment', 'Assessment analyst', ['extract', 'cpue_b'],
     'Join index B to annual catches and check the model inputs.'),
    ('assessment_a1', 'Assessment A1', 'assessment', 'Assessment analyst', ['prepare_a'],
     'Fit the illustrative model to index A with mortality setting 1.'),
    ('assessment_a2', 'Assessment A2', 'assessment', 'Assessment analyst', ['prepare_a'],
     'Fit the illustrative model to index A with mortality setting 2.'),
    ('assessment_b1', 'Assessment B1', 'assessment', 'Assessment analyst', ['prepare_b'],
     'Fit the illustrative model to index B with mortality setting 1.'),
    ('assessment_b2', 'Assessment B2', 'assessment', 'Assessment analyst', ['prepare_b'],
     'Fit the illustrative model to index B with mortality setting 2.'),
    ('assessment_summary', 'Compare assessments', 'assessment', 'Assessment analyst',
     ['assessment_a1', 'assessment_a2', 'assessment_b1', 'assessment_b2'],
     'Compare the four fitted cases in plots and tables.'),
    ('assessment_report', 'Assessment report', 'assessment', 'Assessment analyst', ['assessment_summary'],
     'Write a short report and preserve its analytical record.'),
]
SPEC = {key: dict(key=key, title=title, module=module, owner=owner, parents=parents,
                  description=description)
        for key, title, module, owner, parents, description in JOBS}
DEFAULTS = {'last_year': 2023, 'min_hooks_a': 0, 'mortality_2': 0.30}

# Complete each peer group before its dependent groups; independent paths continue.
# These barriers coordinate execution without adding scientific input dependencies.
STAGES = [
    ['submission'], ['qc'], ['database'], ['extract'],
    ['cpue_a', 'cpue_b'],
    ['prepare_a', 'prepare_b'], ['cpue_summary'], ['cpue_report'],
    ['assessment_a1', 'assessment_a2', 'assessment_b1', 'assessment_b2'],
    ['assessment_summary'], ['assessment_report'],
]

# These are file-transfer boundaries, separate from calculation dependencies.
HANDOVERS = {
    'data': {'cpue_a': ['extract'], 'cpue_b': ['extract']},
    'cpue': {'prepare_a': ['extract', 'cpue_a'], 'prepare_b': ['extract', 'cpue_b']},
}


def handover_groups(stage, active):
    """Only selected recipients whose incoming files were updated need a transfer."""
    for boundary, recipients in HANDOVERS.items():
        group = [key for key in stage if key in recipients
                 and any(parent in active for parent in recipients[key])]
        if group:
            yield {'boundary': boundary, 'group': group}


def downstream(roots):
    selected = set(roots)
    for key, job in SPEC.items():
        if selected.intersection(job['parents']):
            selected.add(key)
    return [key for key in SPEC if key in selected]
