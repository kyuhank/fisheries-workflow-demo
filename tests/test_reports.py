"""Reports describe their supplied results rather than repeating the summary view."""
import copy
from html.parser import HTMLParser
import json
from pathlib import Path
import unittest
from unittest.mock import patch

from workflow.reports import cpue_rates, output_page
from workflow.spec import SPEC


class ReportReader(HTMLParser):
    def __init__(self, page):
        super().__init__()
        self.in_report = False
        self.in_paragraph = False
        self.paragraphs = []
        self.content = []
        self.tags = []
        self.plots = 0
        self.tables = 0
        self.report = None
        self.feed(page)

    def handle_starttag(self, tag, attrs):
        self.tags.append(tag)
        attrs = dict(attrs)
        if tag == 'article' and attrs.get('class') == 'narrative-report':
            self.in_report = True
            self.report = attrs['data-report']
        if self.in_report:
            if tag == 'p':
                self.in_paragraph = True
                self.paragraphs.append('')
            self.plots += tag == 'svg'
            self.tables += tag == 'table'

    def handle_endtag(self, tag):
        if tag == 'article':
            self.in_report = False
        if tag == 'p':
            self.in_paragraph = False

    def handle_data(self, data):
        self.content.append(data)
        if self.in_report and self.in_paragraph:
            self.paragraphs[-1] += data

    @property
    def text(self):
        return '\n'.join(self.paragraphs)


class ReportTest(unittest.TestCase):
    def setUp(self):
        self.record = {'run_id': 'Run 009', 'settings': {}, 'software': {'python': '3.12'}}
        self.lineage = [{'job': 'Retained summary', 'run_id': 'Run 003', 'checksum': 'a' * 64}]
        self.cpue = {'series': {
            'CPUE analysis A': [{'year': 2000, 'index': 1.0}, {'year': 2001, 'index': 0.4}],
            'CPUE analysis B': [{'year': 2000, 'index': 1.0}, {'year': 2001, 'index': 0.7}],
        }}
        self.assessment = {'series': {}, 'diagnostics': []}
        for name, value, growth in [('A1', 0.4, 0.25), ('A2', 0.5, 0.35),
                                       ('B1', 0.6, 0.25), ('B2', 0.7, 0.35)]:
            case = 'Assessment ' + name
            self.assessment['series'][case] = [
                {'year': 2000, 'B_over_K': 1.0, 'harvest_rate': 0.02},
                {'year': 2001, 'B_over_K': value, 'harvest_rate': 0.1}]
            self.assessment['diagnostics'].append(
                {'case': case, 'r': growth, 'boundary_fit': False, 'catch_check': 'Pass'})

    def page(self, key, result):
        return output_page(SPEC[key], result, self.record, self.lineage)

    def test_reports_are_written_accounts_with_one_plot_and_retained_records(self):
        for prefix, result in [('cpue', self.cpue), ('assessment', self.assessment)]:
            with self.subTest(report=prefix):
                original = copy.deepcopy((result, self.record, self.lineage))
                summary = ReportReader(self.page(prefix + '_summary', result))
                page = self.page(prefix + '_report', result)
                report = ReportReader(page)
                self.assertIsNone(summary.report)
                self.assertEqual(report.report, prefix + '_report')
                self.assertEqual(report.plots, 1)
                self.assertEqual(report.tables, 0)
                self.assertIn('<h2>Methods</h2>', page)
                self.assertIn('<h2>Interpretation</h2>', page)
                self.assertIn('stock-management advice', report.text)
                self.assertIn('Run 009', page)
                self.assertIn('Retained summary', page)
                self.assertIn('Run 003', page)
                self.assertEqual((result, self.record, self.lineage), original)

    def test_cpue_account_uses_each_supplied_endpoint_without_assuming_a_decline(self):
        initial = ReportReader(self.page('cpue_report', self.cpue)).text
        self.assertIn('CPUE analysis A was 0.400 in 2001, relative to 1 in 2000.', initial)
        self.cpue['series']['CPUE analysis A'][-1] = {'year': 2024, 'index': 1.25}
        changed = ReportReader(self.page('cpue_report', self.cpue)).text
        self.assertIn('CPUE analysis A was 1.250 in 2024, relative to 1 in 2000.', changed)
        self.assertIn('CPUE analysis B was 0.700 in 2001', changed)
        self.assertNotIn('CPUE analysis A was 0.400', changed)
        self.assertNotIn('declin', changed)

    def test_assessment_account_uses_supplied_year_values_growth_and_checks(self):
        initial = ReportReader(self.page('assessment_report', self.assessment)).text
        self.assertIn('In 2001, biomass ranged from 0.400 to 0.700', initial)
        self.assertIn('intrinsic growth rates of 0.25 and 0.35 per year', initial)
        self.assertIn('The biomass recurrence and positive-stock feasibility checks passed', initial)
        for rows in self.assessment['series'].values():
            rows[-1]['year'] = 2024
            rows[-1]['B_over_K'] += 0.5
        self.assessment['diagnostics'][1].update(r=0.25, boundary_fit=True, catch_check='Fail')
        self.assessment['diagnostics'][3]['r'] = 0.25
        changed = ReportReader(self.page('assessment_report', self.assessment)).text
        self.assertIn('In 2024, biomass ranged from 0.900 to 1.200', changed)
        self.assertIn('intrinsic growth rates of 0.25 per year', changed)
        self.assertIn('Biomass balance or feasibility needs review for Assessment A2.', changed)
        self.assertIn('boundary was reached for Assessment A2', changed)
        self.assertNotIn('The biomass recurrence and positive-stock feasibility checks passed', changed)
        self.assertNotIn('0.35 per year', changed)
        self.assertIn('not an uncertainty interval', changed)
        self.assertIn('no stock-management advice', changed)

    def test_different_assessment_end_years_are_reported_separately(self):
        self.assessment['series']['Assessment A1'][-1]['year'] = 2024
        text = ReportReader(self.page('assessment_report', self.assessment)).text
        self.assertIn('Biomass in Assessment A1 was 0.400 of its carrying capacity in 2024.', text)
        self.assertIn('Biomass in Assessment B2 was 0.700 of its carrying capacity in 2001.', text)
        self.assertNotIn('ranged from', text)

    def test_report_names_and_records_remain_escaped_html(self):
        name = '<script>alert("case")</script>'
        for prefix, result in [('cpue', self.cpue), ('assessment', self.assessment)]:
            with self.subTest(report=prefix):
                first = next(iter(result['series']))
                result['series'][name] = result['series'].pop(first)
                if prefix == 'assessment':
                    result['diagnostics'][0].update(case=name, boundary_fit=True)
                self.record['run_id'] = '<img src=x onerror=alert(1)>'
                page = self.page(prefix + '_report', result)
                reader = ReportReader(page)
                self.assertNotIn('script', reader.tags)
                self.assertNotIn('img', reader.tags)
                self.assertIn('&lt;script&gt;', page)
                self.assertIn('&lt;img', page)

    def test_extraction_describes_actual_coverage_and_both_destinations(self):
        result = {
            'sets': [{'set_id': f'fish-{i}', 'year': 2000 + i // 4, 'vessel': 'A',
                      'hooks': 1000, 'catch_n': 2} for i in range(12)],
            'catch': [{'year': year, 'catch_t': 300} for year in range(2000, 2003)],
            'sql': 'SELECT set_id, year, vessel, hooks, catch_n FROM sets WHERE hooks > 0;',
        }
        page = self.page('extract', result)
        text = ''.join(ReportReader(page).content)
        self.assertIn('12 observations · 2000–2002 · 3 annual catch records', text)
        self.assertIn('Records → CPUE', text)
        self.assertIn('Annual catch → assessment inputs', text)
        self.assertIn('effort filter for analysis A is applied later', text)
        self.assertIn('annual total catches in tonnes', text.lower())
        self.assertIn('fish-5', text)
        self.assertNotIn('fish-6', text)
        self.assertIn('First six rows shown.', text)
        self.assertNotIn(result['sql'], text)
        result['sets'].append({'set_id': 'new', 'year': 2024, 'vessel': 'B',
                               'hooks': 1000, 'catch_n': 3})
        result['catch'].append({'year': 2024, 'catch_t': 350})
        updated = ''.join(ReportReader(self.page('extract', result)).content)
        self.assertIn('13 observations · 2000–2024 · 4 annual catch records', updated)

    def test_cpue_overlay_uses_saved_same_analysis_rates_before_values(self):
        result = {'series': [{'year': 2000, 'index': 1, 'standardised_cpue': 10, 'nominal_cpue': 12},
                             {'year': 2001, 'index': .8, 'standardised_cpue': 8, 'nominal_cpue': 11}],
                  'method': 'Quasipoisson GLM', 'sets_used': 8, 'sets_excluded': 4, 'min_hooks': 1000,
                  'standardisation': 'Fixed supported strata'}
        original = copy.deepcopy(result)
        for key in ('cpue_a', 'cpue_b'):
            with self.subTest(job=key), patch('workflow.reports.plot', return_value='<svg></svg>') as chart:
                page = self.page(key, result)
                chart.assert_called_once_with(cpue_rates(result['series']), 'cpue', 'Fish per 1,000 hooks')
                self.assertLess(page.index('<svg>'), page.index('<table>'))
                self.assertIn('same selected rows; 8 used, 4 excluded; effort filter: at least 1000 hooks', page)
                self.assertNotIn('<details', page)
        self.assertEqual(result, original)

    def test_summary_overlay_does_not_use_unfiltered_B_as_A_nominal(self):
        result = {'series': {'CPUE analysis A': [
                    {'year': 2000, 'index': 1, 'standardised_cpue': 10, 'nominal_cpue': 12},
                    {'year': 2001, 'index': .8, 'standardised_cpue': 8, 'nominal_cpue': 11}],
                'CPUE analysis B': [
                    {'year': 2000, 'index': 1, 'standardised_cpue': 900, 'nominal_cpue': 900},
                    {'year': 2001, 'index': .9, 'standardised_cpue': 810, 'nominal_cpue': 810}]},
                  'analyses': {'CPUE analysis A': {'sets_used': 8, 'sets_excluded': 4, 'min_hooks': 1000},
                               'CPUE analysis B': {'sets_used': 12, 'sets_excluded': 0, 'min_hooks': 0}}}
        with patch('workflow.reports.plot', return_value='<svg></svg>') as chart:
            page = self.page('cpue_summary', result)
        overlay = next(call for call in chart.call_args_list if call.args[1] == 'cpue')
        self.assertEqual(overlay.args[0], cpue_rates(result['series']['CPUE analysis A']))
        self.assertLess(page.index('Standardised and nominal'), page.index('Relative indices A and B'))
        self.assertIn('Any A effort filter applies to both; B uses its own eligible records.', page)
        self.assertNotIn('<details', page)

    def test_legacy_relative_cpue_has_explicit_overlay_absence(self):
        summary = self.page('cpue_summary', self.cpue)
        self.assertIn('A-row nominal overlay is unavailable', summary)
        self.assertEqual(ReportReader(summary).tags.count('svg'), 1)
        page = self.page('cpue_a', {'series': self.cpue['series']['CPUE analysis A']})
        self.assertIn('nominal and standardised rates were not recorded', page)
        self.assertEqual(ReportReader(page).tags.count('svg'), 1)

    def test_all_saved_nonreport_views_have_no_folds_or_raw_record_dumps(self):
        root = Path(__file__).resolve().parents[1]
        keys = [key for key in SPEC if not key.endswith('_report')]
        self.assertEqual(len(keys), 19)
        for key in keys:
            with self.subTest(job=key):
                result = json.loads((root / 'docs/example' / key / 'output.json').read_text())
                original = copy.deepcopy(result)
                page = self.page(key, result)
                tags = ReportReader(page).tags
                self.assertNotIn('details', tags)
                self.assertNotIn('summary', tags)
                self.assertNotIn('pre', tags)
                self.assertLessEqual(tags.count('svg'), 2)
                self.assertLessEqual(tags.count('table'), 1)
                self.assertEqual(tags.count('h1'), 1)
                self.assertIn('data-result="' + key + '"', page)
                self.assertIn('<h1>' + SPEC[key]['title'] + '</h1>', page)
                self.assertEqual(result, original)
                if key.startswith(('cpue_', 'assessment_', 'mse_')) and key != 'mse_prepare':
                    self.assertGreaterEqual(tags.count('svg'), 1)
                    if 'table' in tags:
                        self.assertLess(tags.index('svg'), tags.index('table'))

    def test_assessment_displays_observed_fitted_and_biomass_before_checks(self):
        root = Path(__file__).resolve().parents[1]
        result = json.loads((root / 'docs/example/assessment_a1/output.json').read_text())
        page = self.page('assessment_a1', result)
        self.assertIn('Observed CPUE', page)
        self.assertIn('Fitted CPUE', page)
        self.assertIn('Biomass trajectory', page)
        self.assertEqual(ReportReader(page).tags.count('svg'), 2)
        self.assertLess(page.rindex('</svg>'), page.index('<table>'))

    def test_mse_summary_tradeoff_contains_actual_metrics_before_table(self):
        root = Path(__file__).resolve().parents[1]
        result = json.loads((root / 'docs/example/mse_summary/output.json').read_text())
        page = self.page('mse_summary', result)
        self.assertIn('Management trade-off: mean annual catch', page)
        self.assertLess(page.rindex('</svg>'), page.index('<table>'))
        for row in result['metrics']:
            self.assertIn(f'{row["mean_catch_t"]:.4g} t/year; final B / K {row["final_B_over_K"]:.4g}', page)
        self.assertIn('does not rank the rules', page)


if __name__ == '__main__':
    unittest.main()
