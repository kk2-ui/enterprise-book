import tempfile
import unittest
from datetime import datetime, timedelta
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
from urllib.parse import parse_qs, urlparse

import market_observation
from market_data import read_json, write_json
from market_observation_update import B00Y_ID, HONG_KONG, ObservationUpdater, b00y_series, cutoffs, fx_series, parse_b00y


class MarketObservationUpdateTests(unittest.TestCase):
    def test_cfets_cold_start_respects_endpoint_year_limit_and_currency_order(self):
        cutoff = cutoffs()['fx']
        payload = {'head': {'rep_code': '200'},
                   'data': {'searchlist': ['HKD/CNY', 'EUR/CNY'], 'pageTotal': 1},
                   'records': [{'date': cutoff, 'values': ['0.85562', '7.3599']}]}
        with patch('market_observation_update.fetch', return_value=payload) as request:
            result = fx_series(cutoff, {})
        query = parse_qs(urlparse(request.call_args.args[0]).query)
        earliest = (datetime.now(HONG_KONG).date() - timedelta(days=364)).isoformat()
        self.assertEqual(query['startDate'], [earliest])
        self.assertEqual(result['EURCNY']['rows'], [{'date': cutoff, 'close': 7.3599}])
        self.assertEqual(result['HKDCNY']['rows'], [{'date': cutoff, 'close': 0.85562}])

    def test_cutoffs_follow_local_sessions_and_daylight_saving(self):
        for day, china, europe in [('2026-11-17', '2026-11-17', '2026-11-16'),
                                    ('2026-07-21', '2026-07-21', '2026-07-20')]:
            state = cutoffs(datetime.fromisoformat(day + 'T12:50:00+00:00'))
            self.assertEqual(state, {'stocks': china, 'fx': china, 'xetra': europe, 'B00Y': europe})
        self.assertEqual(cutoffs(datetime.fromisoformat('2026-07-21T22:16:00+00:00'))['B00Y'],
                         '2026-07-21')
        self.assertEqual(cutoffs(datetime.fromisoformat('2026-11-17T22:16:00+00:00'))['B00Y'],
                         '2026-11-16')

    def test_b00y_checks_identity_and_excludes_future_close(self):
        bars = ['2026-11-16,1,93,2,1', '2026-11-17,2,97,3,2']
        for code, exchange in [('BZ=F', 112), ('B00Y', 102)]:
            with self.assertRaises(ValueError):
                parse_b00y({'data': {'code': code, 'market': exchange, 'klines': bars}}, '2026-11-16', 'test')
        series = parse_b00y({'data': {'code': 'B00Y', 'market': 112, 'klines': bars}}, '2026-11-16', 'test')
        self.assertEqual(series['series_id'], B00Y_ID)
        self.assertEqual(series['rows'], [{'date': '2026-11-16', 'close': 93}])

    def test_b00y_uses_resolved_eastmoney_host_on_physical_route_after_timeout(self):
        routes = SimpleNamespace(stdout='default 198.18.0.1 UGSc utun4\ndefault 192.168.1.1 UGSc en7\n')
        addresses = {'Answer': [{'type': 1, 'data': '198.18.0.19'}, {'type': 1, 'data': '140.207.67.156'}]}
        response = SimpleNamespace(returncode=0, stdout='{"data":{"code":"B00Y","market":112,'
                                                        '"klines":["2026-11-16,95.84,91.75,96.77,91.74"]}}')
        with patch('market_data.sys.platform', 'darwin'), \
             patch('market_data.get_json', side_effect=[OSError('TLS timeout'), addresses]), \
             patch('market_data.run', side_effect=[routes, response]) as commands:
            output = b00y_series('2026-11-16')
        self.assertEqual(output['network_route'], 'macos-physical-interface')
        self.assertEqual(output['rows'], [{'date': '2026-11-16', 'close': 91.75}])
        arguments = commands.call_args.args[0]
        self.assertIn('if!en7', arguments)
        self.assertIn('push2his.eastmoney.com:443:140.207.67.156', arguments)
        self.assertIn('secid=112.B00Y', arguments[-1])

    def test_b00y_reader_ignores_legacy_and_unidentified_oil(self):
        with tempfile.TemporaryDirectory() as root:
            store = SimpleNamespace(directory=Path(root))
            company = {'id': 'p', 'code': '601857.SH', 'name': '中国石油', 'book_editions': []}
            base = {'label': 'test', 'source': 'Yahoo', 'url': 'test',
                    'rows': [{'date': '2026-11-16', 'close': 92.44}]}
            path = store.directory / 'market_observation'
            write_json(path / 'BRENT.json', base)
            write_json(path / 'B00Y.json', base)
            with patch('market_observation.completed_date', return_value='2026-11-17'):
                self.assertEqual(market_observation.response(store, company)['chart'], [])
                write_json(path / 'B00Y.json', base | {'source': 'Eastmoney', 'series_id': B00Y_ID})
                chart = market_observation.response(store, company)['chart']
            self.assertEqual(chart, [{'date': '2026-11-16', 'values': {'B00Y': 92.44}}])

    def test_failed_source_preserves_previous_data_and_records_attempt(self):
        with tempfile.TemporaryDirectory() as root:
            updater = ObservationUpdater(root)
            old = {'series_id': B00Y_ID, 'rows': [{'date': '2026-11-16', 'close': 93}]}
            path = updater.directory / 'B00Y.json'
            write_json(path, old)
            try:
                with patch('market_observation_update.stock_series', side_effect=OSError('offline')), \
                     patch('market_observation_update.xetra_series', side_effect=OSError('offline')), \
                     patch('market_observation_update.fx_series', side_effect=OSError('offline')), \
                     patch('market_observation_update.b00y_series', side_effect=OSError('offline')):
                    state = updater.start().result()
                self.assertEqual(state['errors']['B00Y'], 'offline')
                self.assertEqual(read_json(path), old)
                self.assertFalse(updater.status()['running'])
            finally:
                updater.close()
