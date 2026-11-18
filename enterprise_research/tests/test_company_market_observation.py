import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from company_market_observation import DRIVERS, operating_series, disclosures, historical_limit, response, series_for, valuation


from market_nbs import release_point, series


class CompanyMarketObservationTests(unittest.TestCase):
    def setUp(self):
        self.company = {'id': 'test', 'code': '6049.HK', 'name': '保利物业'}
        self.edition = {
            'id': 'gemini', 'source_version': 'fixed', 'title': 'Gemini 企业书',
            'information_cutoff': '2026-11-17', 'completed_at': '2026-11-18T01:00:00+00:00',
            'parts': {'overview': {'display': {}}, 'valuation': {'body': '固定正文'}},
        }

    def test_valuation_belongs_to_selected_edition_and_checks_publication(self):
        self.assertNotIn('url', valuation(self.company, self.edition, '2026-11-17'))
        selected = valuation(self.company, self.edition, '2026-11-18')
        self.assertTrue(selected['url'].endswith('?edition=gemini&view=valuation'))
        self.assertIsNone(historical_limit(self.edition))
        old = dict(self.edition, title='三一重工 · 2015年8月26日历史企业书 v1')
        self.assertEqual(historical_limit(old), '2026-11-17')
        self.edition['parts']['overview']['display']['historical'] = True
        self.assertEqual(historical_limit(self.edition), '2026-11-17')

    def test_cards_check_publication_even_when_facts_are_earlier(self):
        doc = {'id': 'h12026', 'title': '中报', 'nature': 'company_disclosure',
               'published_on': '2026-09-16', 'original_url': '/report'}
        row = {'document_id': 'h12026', 'metric': 'revenue', 'value': '8829177',
               'unit': 'CNY_thousand', 'scope': 'consolidated', 'period': '2026H1',
               'column_definition': {'end': '2026-06-30'}, 'pdf_page': 13}
        store = SimpleNamespace(source_data=object())
        with patch('company_market_observation.manifest', return_value={'documents': [doc]}) as manifest, \
             patch('company_market_observation.facts', return_value={'disclosed': [row]}):
            self.assertEqual(disclosures(store, self.company, self.edition, '2026-09-15'), [])
            seen = disclosures(store, self.company, self.edition, '2026-09-16')
        self.assertEqual(seen[0]['metrics'], [('营业收入', '88.29 亿元')])
        self.assertEqual(seen[0]['sources'][0][1], '/report#page=13')
        manifest.assert_called_with(store.source_data, self.company['id'], 'fixed')

    def test_monthly_statistics_choose_cumulative_and_residential_columns_at_release(self):
        # A delayed test release makes the publication month an unreliable period label.
        header = ('<meta name="PubDate" content="2026/11/16 10:00">'
                  '<meta name="ArticleTitle" content="2026年1—9月份统计数据">')
        def table(*rows):
            return header + '<table>' + ''.join(
                '<tr>' + ''.join(f'<td>{cell}</td>' for cell in row) + '</tr>' for row in rows) + '</table>'
        retail = release_point(table(['家用电器和音像器材类', '100', '2.5', '900', '-4.2']), 'appliances', '/retail')
        housing = release_point(table(['房屋施工面积', '5000', '-8.0'], ['其中：住宅', '4000', '-9.0'],
                                      ['房屋竣工面积', '3000', '-26.6'], ['其中：住宅', '2100', '-27.9']),
                                'housing', '/housing')
        self.assertEqual((retail['period'], retail['value'], housing['value']), ('2026-09', -4.2, -27.9))
        archive = {'rows': {'/retail': retail, '/housing': housing}}
        with patch('market_nbs.archive', return_value=archive):
            self.assertEqual(series(None, 'housing', '2026-11-15')['points'], [])
            self.assertEqual(series(None, 'housing', '2026-11-16')['points'], [housing])

    def test_financial_series_uses_current_consolidated_balance_and_original_publication(self):
        doc = {'id': 'q3', 'title': '三季报', 'published_on': '2026-10-27', 'original_url': '/original'}
        base = dict(metric='bs_inventory', document_id='q3', scope='consolidated', unit='CNY_yuan', pdf_page=5)
        def balance(day, value, **extra):
            return dict(base, value=value, column_definition={'date': day, 'kind': 'stock'}, **extra)
        rows = [balance('2025-12-31', 900000000), balance('2026-09-30', 250000000),
                dict(balance('2026-09-30', 10000000), scope='parent'), balance('2026-12-31', 700000000)]
        profile = DRIVERS['000651.SZ']
        self.assertEqual(operating_series(profile, rows, {'q3': doc}, '2026-10-26')[0]['points'], [])
        series = operating_series(profile, rows, {'q3': doc}, '2026-10-27')
        self.assertEqual([(p['value'], p['period'], p['published'], p['url']) for p in series[0]['points']],
                         [(2.5, '2026-09-30', '2026-10-27', '/original#page=5')])
        self.assertEqual(series[1]['points'], [])

    def test_generic_price_cache_survives_source_error_and_respects_cutoff(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = SimpleNamespace(directory=Path(tmp))
            dataset = {'source': '行情源', 'url': 'https://example.org', 'rows': [
                {'date': '2026-11-16', 'close': 26.12},
                {'date': '2026-11-17', 'close': 26.62},
            ]}
            earlier_dataset = dict(dataset, rows=[{'date': '2025-10-14', 'close': 30.0}, dataset['rows'][0]])
            provider = Mock(side_effect=[dataset, earlier_dataset, OSError('offline')])
            with patch('company_market_observation.stock_series', provider), \
                 patch('company_market_observation.disclosures', return_value=[]):
                full = response(store, self.company, '2026-11-17', self.edition)
                early = response(store, self.company, '2026-11-16', self.edition)
                repeated = response(store, self.company, '2026-11-16', self.edition)
                cache, status = series_for(store.directory, '06049.HK', '2026-11-17', force=True)
            self.assertEqual(full['chart'][-1]['values'], {'06049.HK': 26.62})
            self.assertEqual(early['chart'][-1]['date'], '2026-11-16')
            self.assertEqual(early['chart'][0]['date'], '2025-10-14')
            self.assertEqual(repeated['chart'], early['chart'])
            self.assertEqual(cache['rows'], [*earlier_dataset['rows'], dataset['rows'][-1]])
            self.assertEqual([call.args[1] for call in provider.call_args_list],
                             ['2026-11-17', '2026-11-16', '2026-11-17'])
            self.assertEqual(status['errors'], {'06049.HK': 'offline'})

    def test_unknown_market_has_its_own_empty_sections(self):
        store = SimpleNamespace(directory=Path('/tmp'))
        with patch('company_market_observation.disclosures', return_value=[]):
            view = response(store, dict(self.company, code='unlisted'), '2026-11-17')
        self.assertEqual(view['chart'], [])
        self.assertEqual(view['coverage'], [])
        self.assertIn('reason', view['valuation'])


if __name__ == '__main__':
    unittest.main()
