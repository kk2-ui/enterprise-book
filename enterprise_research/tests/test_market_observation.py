import json
import tempfile
import threading
import unittest
from http.server import ThreadingHTTPServer
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
from urllib.request import Request, build_opener, ProxyHandler

from app import Store, Handler
from market_data import write_json
from market_observation import align_inputs, official_snapshot, response
from market_observation_update import ObservationUpdater


def prices(*bars):
    return {'rows': [
        {'date': day, 'close': price, 'volume': volume} for day, price, volume in bars
    ]}


class MarketObservationTests(unittest.TestCase):
    def test_observation_routes_serve_history_and_trigger_shared_updater(self):
        with tempfile.TemporaryDirectory() as directory:
            store = Store(Path(directory))
            cid = store.add_company({'name': '中国石油', 'code': '601857.SH'})
            updater = ObservationUpdater(directory)
            server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
            server.store, server.observation_updater = store, updater
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            base = f'http://127.0.0.1:{server.server_port}'
            client = build_opener(ProxyHandler({}))
            try:
                with client.open(base + '/market-observation.js') as result:
                    self.assertEqual(result.status, 200)
                endpoint = base + f'/api/companies/{cid}/market-context'
                with client.open(endpoint + '?observation=1&as_of=2026-08-29') as result:
                    data = json.load(result)
                self.assertEqual(data['cards'], [])
                self.assertFalse(data['refresh']['running'])
                with patch.object(updater, 'start') as start:
                    request = Request(endpoint + '/refresh', data=b'{"observation":1}',
                                      headers={'Content-Type': 'application/json'})
                    with client.open(request) as result:
                        self.assertEqual(result.status, 202)
                    start.assert_called_once_with()
            finally:
                server.shutdown()
                server.server_close()
                thread.join()
                updater.close()

    def test_pairs_use_only_their_own_trade_and_fx_legs(self):
        days = ('2026-10-05', '2026-10-06', '2026-10-08', '2026-10-09')
        inputs = {
            '690D.DE': prices((days[0], 1.8, 18741), (days[2], 2.0, 0), (days[3], 2.1, 1000)),
            '600690.SH': prices((days[2], 20, 1000), (days[3], 20, 1000)),
            '06690.HK': prices((days[2], 20, 1000), (days[3], 20, 1000)),
            'HKDCNY': prices((days[2], .85, None)),
            'EURCNY': prices((days[2], 7.5, None)),
        }
        rows = {row['date']: row['values'] for row in align_inputs(inputs, days[2])}
        self.assertEqual(rows[days[0]]['d_volume'], 18741)
        self.assertEqual(rows[days[0]]['690D.DE'], 1.8)
        self.assertIsNone(rows[days[0]]['d_discount'])
        self.assertIsNone(rows[days[1]]['690D.DE'])
        self.assertIsNone(rows[days[2]]['d_cny'])
        self.assertAlmostEqual(rows[days[2]]['h_discount'], -15)
        self.assertNotIn(days[3], rows)

    def test_disclosure_sources_and_edition_are_filtered_at_cutoff(self):
        with tempfile.TemporaryDirectory() as tmp:
            directory = Path(tmp)
            company = {'id': 'p', 'code': '601857.SH', 'name': '中国石油', 'sources': [],
                       'book_editions': [{'id': '84029c690b284d30', 'source_version': 'wrong',
                                          'information_cutoff': '2026-11-13'}]}
            store = SimpleNamespace(directory=directory)
            with patch('market_observation.completed_date', return_value='2026-11-17'):
                before = response(store, company, '2026-08-29')
                first = response(store, company, '2026-08-30')
                report = response(store, company, '2026-09-18')
                no_edition = response(store, company, '2026-11-17')
            self.assertEqual(before['cards'], [])
            self.assertEqual(before['events'], [])
            self.assertEqual(len(first['cards'][0]['sources']), 2)
            self.assertEqual(first['events'][0]['plot_on'], '2026-08-31')
            self.assertEqual(len(report['cards'][0]['sources']), 3)
            self.assertNotIn('url', no_edition['valuation'])

    def test_d_only_page_and_full_same_date_price_snapshot(self):
        with tempfile.TemporaryDirectory() as tmp:
            directory = Path(tmp)
            day = '2026-11-16'
            company = {'id': 'h', 'name': '海尔智家', 'code': '600690.SH', 'sources': [],
                       'book_editions': [{'id': 'new-haier-id', 'source_version': 'haier-sources-20261110-v4',
                                          'title': '海尔智家 · Codex 企业书 · haier-book-20261110-v2',
                                          'model': {'name': 'Codex'},
                                          'information_cutoff': '2026-11-10'}]}
            store = SimpleNamespace(directory=directory)
            def save(symbol, price, volume=None):
                write_json(directory / 'market_observation' / f'{symbol}.json', {
                    'label': symbol, 'source': 'test', 'url': 'https://example.org',
                    **prices((day, price, volume)),
                })
            with patch('market_observation.completed_date', return_value=day):
                save('690D.DE', 1.848, 75070)
                partial = response(store, company)
                self.assertIsNone(partial['price_snapshot'])
                self.assertEqual(partial['chart'][0]['values']['d_volume'], 75070)
                for symbol, price in (('600690.SH', 21.72), ('06690.HK', 21.14),
                                      ('EURCNY', 7.3810), ('HKDCNY', .85579)):
                    save(symbol, price)
                full = response(store, company)
            row = full['chart'][0]['values']
            self.assertAlmostEqual(row['d_cny'], 13.640088)
            self.assertAlmostEqual(row['h_cny'], 18.0914006)
            self.assertEqual(len(full['price_snapshot']['metrics']), 3)
            self.assertEqual(full['valuation']['url'], '#/company/h/editions?edition=new-haier-id&view=valuation')

    def test_petrochina_resolves_installed_edition_and_referenced_figure(self):
        edition = {'id': 'installed-edition', 'title': '中国石油企业书 · 修订版 v1',
                   'source_version': 'petrochina-sources-20261115-v1',
                   'information_cutoff': '2026-11-13', 'completed_at': '2026-11-15T12:00:00+08:00',
                   'model': {'name': 'Codex', 'version': 'gpt-6.1-sol'},
                   'parts': {'valuation': {'body': '[[figure:installed-picture|年度现金要求]]'}}}
        company = {'id': 'installed-company', 'book_editions': [edition],
                   'sources': [{'id': 'installed-picture', 'available': True}]}
        result = official_snapshot(None, company, 'petrochina', '2026-11-16')
        self.assertEqual(result['url'], '#/company/installed-company/editions?edition=installed-edition&view=valuation')
        self.assertEqual(result['figure_url'], '/api/sources/installed-picture/file')
        self.assertNotIn('url', official_snapshot(None, company, 'petrochina', '2026-11-14'))
