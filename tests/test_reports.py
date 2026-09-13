"""Reports describe their supplied results rather than repeating the summary view."""
import copy
from html.parser import HTMLParser
import unittest

from workflow.reports import output_page
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
        for name, value, mortality in [('A1', 0.4, 0.2), ('A2', 0.5, 0.35),
                                       ('B1', 0.6, 0.2), ('B2', 0.7, 0.35)]:
            case = 'Assessment ' + name
            self.assessment['series'][case] = [
                {'year': 2000, 'SB_over_SB0': 1.0, 'F': 0.02},
                {'year': 2001, 'SB_over_SB0': value, 'F': 0.1}]
            self.assessment['diagnostics'].append(
                {'case': case, 'M': mortality, 'boundary_fit': False, 'catch_check': 'Pass'})

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
                self.assertIn('synthetic', report.text)
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

    def test_assessment_account_uses_supplied_year_values_mortality_and_checks(self):
        initial = ReportReader(self.page('assessment_report', self.assessment)).text
        self.assertIn('In 2001, spawning biomass ranged from 0.400 to 0.700', initial)
        self.assertIn('natural mortality of 0.20 and 0.35 per year', initial)
        self.assertIn('Annual catches were reproduced', initial)
        for rows in self.assessment['series'].values():
            rows[-1]['year'] = 2024
            rows[-1]['SB_over_SB0'] += 0.5
        self.assessment['diagnostics'][1].update(M=0.25, boundary_fit=True, catch_check='Fail')
        self.assessment['diagnostics'][3]['M'] = 0.25
        changed = ReportReader(self.page('assessment_report', self.assessment)).text
        self.assertIn('In 2024, spawning biomass ranged from 0.900 to 1.200', changed)
        self.assertIn('natural mortality of 0.20 and 0.25 per year', changed)
        self.assertIn('Catch matching needs review for Assessment A2.', changed)
        self.assertIn('boundary was reached for Assessment A2', changed)
        self.assertNotIn('Annual catches were reproduced', changed)
        self.assertNotIn('0.35 per year', changed)
        self.assertIn('not an uncertainty interval', changed)
        self.assertIn('no stock-management advice', changed)

    def test_different_assessment_end_years_are_reported_separately(self):
        self.assessment['series']['Assessment A1'][-1]['year'] = 2024
        text = ReportReader(self.page('assessment_report', self.assessment)).text
        self.assertIn('Spawning biomass in Assessment A1 was 0.400 of its unfished level in 2024.', text)
        self.assertIn('Spawning biomass in Assessment B2 was 0.700 of its unfished level in 2001.', text)
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
        self.assertIn('Observations → CPUE', text)
        self.assertIn('Annual catch → assessment inputs', text)
        self.assertIn('effort filter for analysis A is applied later', text)
        self.assertIn('annual total catches in tonnes', text.lower())
        self.assertIn('fish-9', text)
        self.assertNotIn('fish-10', text)
        self.assertIn(result['sql'], text)
        result['sets'].append({'set_id': 'new', 'year': 2024, 'vessel': 'B',
                               'hooks': 1000, 'catch_n': 3})
        result['catch'].append({'year': 2024, 'catch_t': 350})
        updated = ''.join(ReportReader(self.page('extract', result)).content)
        self.assertIn('13 observations · 2000–2024 · 4 annual catch records', updated)


if __name__ == '__main__':
    unittest.main()
