import json
import math
from pathlib import Path
import random
import sys
import tempfile
import threading
import unittest
from http.server import ThreadingHTTPServer
from urllib.request import Request, build_opener, ProxyHandler
from datetime import date, datetime, timedelta, timezone
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from market_context import (
    BRENT_INSTRUMENT, MarketService, build_context, build_petrochina_cost,
    build_petrochina_pilot, build_petrochina_valuation, fit_model, prior_window_analysis,
)
from market_data import QuoteCache, completed_date, parse_index, parse_stock, parse_a_stock
from app import Store, Handler
from industry_monitor.service import MonitorService


def synthetic_samples():
    rng = random.Random(12)
    samples = []
    for i in range(200):
        market, size, industry = [rng.gauss(0, .012) for _ in range(3)]
        samples.append({'date': (date(2025, 1, 1)+timedelta(days=i)).isoformat(),
                        'market': market, 'size': size, 'industry': industry,
                        'stock': .0002 + .8*market + .4*size + .6*industry + rng.gauss(0, .002)})
    return samples


class MarketModelTests(unittest.TestCase):
    def test_holdout_price_change_never_changes_training_coefficients(self):
        samples = synthetic_samples()
        original = prior_window_analysis(samples, ['market','size','industry'], 20, 4, False)
        changed = [dict(row, stock=row['stock']-.02) if i >= 180 else row for i, row in enumerate(samples)]
        after = prior_window_analysis(changed, ['market','size','industry'], 20, 4, False)
        self.assertEqual(original['betas'], after['betas'])
        self.assertEqual(after['deviation'], '额外走弱')
        self.assertLess(after['training_end'], after['evaluation_start'])
        self.assertAlmostEqual(sum(after['parts_log_pp'].values()) + after['alpha_log_pp'] + after['residual_log_pp'], after['observed_log_pp'], delta=.03)

    def test_collinear_factors_do_not_produce_unique_driver(self):
        samples = [dict(row, industry=row['market']) for row in synthetic_samples()]
        result = prior_window_analysis(samples, ['market','size','industry'], 20, 4, False)
        self.assertEqual(result['status'], 'insufficient')
        self.assertIn('同步', result['reason'])

    def test_small_sample_and_thin_trading_reduce_claim(self):
        samples = synthetic_samples()
        thin = prior_window_analysis(samples, ['market','size','industry'], 20, 2, True)
        self.assertEqual(thin['wind'], '证据较弱')
        self.assertEqual(thin['dominant'], 'mixed')
        self.assertIn('同行样本仅两家', ' '.join(thin['limitations']))
        self.assertEqual(prior_window_analysis(samples[:85], ['market'], 20, 0, False)['status'], 'insufficient')

    def test_known_sensitivity_is_recovered(self):
        fit = fit_model(synthetic_samples(), ['market','size','industry'])
        for name, expected in [('market', .8), ('size', .4), ('industry', .6)]:
            self.assertAlmostEqual(fit['beta'][name], expected, delta=.06)


class MarketAcquisitionTests(unittest.TestCase):
    def test_panel_assets_and_api_are_reachable_from_real_handler(self):
        with tempfile.TemporaryDirectory() as directory:
            store = Store(Path(directory))
            cid = store.add_company({'name':'测试企业', 'code':'00506.HK'})
            service = MarketService(directory)
            server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
            server.store, server.market_context = store, service
            server.industry_monitor=MonitorService(directory,start_scheduler=False)
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            opener = build_opener(ProxyHandler({}))
            base = 'http://127.0.0.1:' + str(server.server_port)
            try:
                for path, content_type in [('/market-context.js','javascript'),('/market-context.css','css')]:
                    with opener.open(base+path) as response:
                        self.assertEqual(response.status, 200)
                        self.assertIn(content_type, response.headers['Content-Type'])
                with patch.object(service, 'response', return_value={'status':'pending','refreshing':True}) as response:
                    with opener.open(base+'/api/companies/'+cid+'/market-context') as result:
                        self.assertTrue(json.load(result)['refreshing'])
                    self.assertEqual(response.call_args.args[0]['code'], '00506.HK')
                    request = Request(base+'/api/companies/'+cid+'/market-context/refresh', data=b'{}', headers={'Content-Type':'application/json'})
                    with opener.open(request) as result:
                        self.assertEqual(result.status, 202)
                    self.assertTrue(response.call_args.kwargs['force'])
            finally:
                server.shutdown()
                server.server_close()
                thread.join()
                service.close()
                server.industry_monitor.close()

    def test_hk_raw_dividend_fallback_is_rejected(self):
        payload = {'data': {'hk00506': {'day': [['2026-11-04','4','3.8','4','3.7','1000']]}}}
        with self.assertRaisesRegex(ValueError, '前复权'):
            parse_stock(payload, '00506.HK', 'https://example.com', '2026-11-06')

    def test_security_identity_and_unfinished_bar(self):
        rows = [['2026-11-05','4','4','4','4','1000'], ['2026-11-06','4','5','5','4','1000']]
        payload = {'data': {'hk00506': {'qfqday': rows, 'qt': {'hk00506':['100','中国食品','00506']}}}}
        result = parse_stock(payload, '00506.HK', 'https://example.com', '2026-11-05')
        self.assertEqual(result['rows'][-1]['close'], 4)
        payload['data']['hk00506']['qt']['hk00506'][2] = '00507'
        with self.assertRaisesRegex(ValueError, '不匹配'):
            parse_stock(payload, '00506.HK', 'https://example.com', '2026-11-05')
        with self.assertRaisesRegex(ValueError, '指数代码'):
            parse_index({'data':{'code':'HSLI'}}, 'HSSI','小盘','124.HSSI','url','2026-11-06')

    def test_hk_cutoff_respects_session_and_weekend(self):
        self.assertEqual(completed_date(datetime(2026,11,6,5,tzinfo=timezone.utc)), '2026-11-05')
        self.assertEqual(completed_date(datetime(2026,11,6,10,tzinfo=timezone.utc)), '2026-11-06')
        self.assertEqual(completed_date(datetime(2026,11,8,10,tzinfo=timezone.utc)), '2026-11-06')

    def test_a_stock_extended_history_keeps_volume_and_close_cutoff(self):
        payload = {'data':{'code':'000651','name':'格力电器','klines':[
            '2026-11-05,38,39,40,37,100,3900',
            '2026-11-06,39,40,41,38,200,8000']}}
        result = parse_a_stock(payload,'000651.SZ','0.000651','url','2026-11-05')
        self.assertEqual(result['adjustment'],'QFQ')
        self.assertEqual(result['rows'],[{'date':'2026-11-05','close':39.,'volume':100.,'amount':3900.}])
        with self.assertRaisesRegex(ValueError,'股票代码'):
            parse_a_stock(payload,'000651.SZ','0.000652','url','2026-11-05')

    def test_failed_refresh_keeps_source_capture_time(self):
        with tempfile.TemporaryDirectory() as directory:
            cache = QuoteCache(directory)
            path = cache.directory/'00506.HK.json'
            path.parent.mkdir(parents=True)
            saved = {'code':'00506.HK','rows':[{'date':'2026-11-04','close':4}], 'captured_at':'2026-11-04T12:00:00+00:00'}
            path.write_text(json.dumps(saved))
            with patch('market_data.get_json', side_effect=OSError('network unavailable')):
                result, error = cache.fetch({'code':'00506.HK'}, '2026-11-06')
            self.assertEqual(result['captured_at'], saved['captured_at'])
            self.assertIn('unavailable', error)

    def test_registry_has_no_self_or_cross_market_peer(self):
        with tempfile.TemporaryDirectory() as directory:
            service = MarketService(directory)
            for code in ['00506.HK','02314.HK','000651.SZ','06049.HK']:
                profile, version = service.profile(code)
                peers = [p['code'] for p in profile['peers']]
                self.assertTrue(version)
                self.assertNotIn(code, peers)
                self.assertEqual(len(peers), len(set(peers)))
                self.assertTrue(all(p.endswith('.HK') == code.endswith('.HK') for p in peers))
            profile, _ = service.profile('99999.HK')
            self.assertEqual(profile['peers'], [])
            service.close()

    def test_latest_date_mismatch_does_not_claim_current_environment(self):
        series = {'00506.HK':{'rows':[{'date':'2026-11-04','close':4}]},
                  'HSCI':{'rows':[{'date':'2026-11-06','close':3000}]}}
        result = build_context('00506.HK', {'peers':[]}, series, [], '2026-11-06', 'v1')
        self.assertEqual(result['status'], 'unavailable')
        self.assertEqual(result['as_of'], '2026-11-04')


class PetroChinaMarketPilotTests(unittest.TestCase):
    def _sample_series(self):
        return {
            '601857.SH': {
                'code': '601857.SH',
                'name': '中国石油',
                'source': '东方财富前复权日线',
                'source_url': ('ht' + 'tps://example.org/601857'),
                'adjustment': 'QFQ',
                'currency': 'CNY',
                'captured_at': '2026-11-13T10:00:00+00:00',
                'rows': [
                    {'date': '2026-08-28', 'close': 11.80, 'volume': 1000},
                    {'date': '2026-08-31', 'close': 11.95, 'volume': 1200},
                    {'date': '2026-09-02', 'close': 12.10, 'volume': 1100},
                    {'date': '2026-11-13', 'close': 12.39, 'volume': 1300},
                ],
            },
            '00857.HK': {
                'code': '00857.HK',
                'name': '中国石油股份',
                'source': '腾讯前复权日线',
                'source_url': ('ht' + 'tps://example.org/00857'),
                'adjustment': 'QFQ',
                'currency': 'HKD',
                'captured_at': '2026-11-13T10:00:00+00:00',
                'rows': [
                    {'date': '2026-08-28', 'close': 9.85, 'volume': 2000},
                    {'date': '2026-08-31', 'close': 9.96, 'volume': 2100},
                    {'date': '2026-09-01', 'close': 10.02, 'volume': 1900},
                    {'date': '2026-11-13', 'close': 10.33, 'volume': 2200},
                ],
            },
            'BRENT': {
                'code': 'BRENT',
                'name': '布伦特原油期货连续',
                'source': '东方财富期货连续日线',
                'source_url': ('ht' + 'tps://example.org/brent'),
                'adjustment': 'CONTINUOUS_FUTURES',
                'currency': 'USD',
                'unit': '美元/桶',
                'captured_at': '2026-11-13T10:00:00+00:00',
                'rows': [
                    {'date': '2026-08-28', 'close': 76.40, 'volume': None},
                    {'date': '2026-09-01', 'close': 75.80, 'volume': None},
                    {'date': '2026-09-02', 'close': 75.20, 'volume': None},
                    {'date': '2026-11-13', 'close': 73.90, 'volume': None},
                ],
            },
        }

    def test_brent_continuous_futures_preserves_unit_and_code_check(self):
        payload = {'data': {'code': 'B00Y', 'name': '布伦特原油当月连续', 'klines': [
            '2026-11-12,73.1,73.5,74.0,72.8,1000,0',
            '2026-11-13,73.5,73.9,74.2,73.2,1100,0',
        ]}}
        parsed = parse_index(
            payload, 'BRENT', BRENT_INSTRUMENT['name'], BRENT_INSTRUMENT['secid'],
            ('ht' + 'tps://example.org'), '2026-11-13',
            source=BRENT_INSTRUMENT['source'], adjustment=BRENT_INSTRUMENT['adjustment'],
            currency=BRENT_INSTRUMENT['currency'], unit=BRENT_INSTRUMENT['unit'],
        )
        self.assertEqual(parsed['unit'], '美元/桶')
        self.assertEqual(parsed['currency'], 'USD')
        self.assertEqual(parsed['adjustment'], 'CONTINUOUS_FUTURES')
        self.assertEqual(len(parsed['rows']), 2)

    def test_trend_keeps_missing_weekday_gaps_and_omits_epv_or_65_lines(self):
        pilot = build_petrochina_pilot('601857.SH', self._sample_series(), [], '2026-11-13')
        self.assertEqual(pilot['pilot'], 'petrochina_market_v1')
        self.assertEqual(pilot['status'], 'ready')
        trend = pilot['trend']
        self.assertFalse(trend['ah_premium_included'])
        by_date = {row['date']: row for row in trend['chart']}
        self.assertIsNone(by_date['2026-09-01']['a_stock'])
        self.assertEqual(by_date['2026-09-01']['brent'], 75.80)
        self.assertEqual(by_date['2026-08-31']['a_stock'], 11.95)
        self.assertIsNone(by_date['2026-08-31']['brent'])
        self.assertIsNone(by_date['2026-09-03']['a_stock'])
        self.assertIsNone(by_date['2026-09-03']['brent'])
        anns = {a['id']: a for a in trend['announcements']}
        self.assertEqual(anns['div2026']['plot_date'], '2026-08-31')
        self.assertTrue(anns['h12026']['url'].endswith('#page=25'))
        for row in trend['chart']:
            self.assertEqual(set(row.keys()), {'date', 'a_stock', 'h_stock', 'brent'})

    def test_cost_card_blanks_before_first_public_disclosure_date(self):
        before = build_petrochina_cost('2026-08-29')
        self.assertFalse(before['visible'])
        self.assertIsNone(before['prior_value'])
        self.assertIsNone(before['current_value'])
        self.assertIsNone(before['yoy_pct'])
        self.assertIn('2026-08-30', before['blank_reason'])

        on_release = build_petrochina_cost('2026-08-30')
        self.assertTrue(on_release['visible'])
        self.assertEqual(on_release['prior_period'], '2025年上半年')
        self.assertEqual(on_release['current_period'], '2026年上半年')
        self.assertEqual(on_release['prior_value'], 10.14)
        self.assertEqual(on_release['current_value'], 10.68)
        self.assertEqual(on_release['yoy_pct'], 5.3)
        self.assertIn('2026091800441.pdf#page=25', on_release['source_url'])

    def test_valuation_links_to_exact_2026_11_13_formal_edition_and_figure(self):
        company = {
            'id': 'c_petro',
            'code': '601857.SH',
            'default_book_edition_id': 'ed_newer_draft',
            'book_editions': [
                {'id': 'ed_newer_draft', 'title': '草稿试验版', 'information_cutoff': '2026-12-01'},
                {
                    'id': 'ed_formal_20261113',
                    'title': '中国石油企业书 · 修订版 v1',
                    'information_cutoff': '2026-11-13',
                    'source_version': 'petrochina-sources-20261115-v1',
                },
            ],
            'sources': [
                {'id': 'fig_thresh_01', 'title': '中国石油A/H价格的年度现金要求', 'available': True},
            ],
        }
        val = build_petrochina_valuation(company, '2026-11-13')
        self.assertEqual(val['snapshot_date'], '2026-11-13')
        self.assertEqual(val['return_rate_pct'], 10)
        self.assertEqual(val['tax_basis'], '投资者个人税前')
        self.assertEqual(val['base_normal_cash_yi'], 1150)
        self.assertEqual(val['h_implied_cash_yi'], 1618)
        self.assertEqual(val['a_implied_cash_yi'], 2268)
        self.assertEqual(val['edition_id'], 'ed_formal_20261113')
        self.assertEqual(
            val['edition_valuation_url'],
            '#/company/c_petro/editions?edition=ed_formal_20261113&view=valuation',
        )
        self.assertEqual(val['figure_url'], '/api/sources/fig_thresh_01/file')

    def test_http_handler_serves_petrochina_as_of_cutoff_and_keeps_other_companies_unchanged(self):
        with tempfile.TemporaryDirectory() as directory:
            store = Store(Path(directory))
            petro_id = store.add_company({'name': '中国石油', 'code': '601857.SH'})
            other_id = store.add_company({'name': '中国食品', 'code': '00506.HK'})
            fig_id = store.add_source(
                petro_id,
                {'title': '中国石油A/H价格的年度现金要求', 'kind': '研究图'},
                b'\x89PNG\r\n\x1a\n',
                'threshold.png',
            )
            with store.connect() as conn:
                conn.execute(
                    'INSERT INTO book_editions VALUES(?,?,?,?)',
                    (
                        'ed_petro_v1',
                        petro_id,
                        json.dumps({
                            'title': '中国石油企业书 · 修订版 v1',
                            'information_cutoff': '2026-11-13',
                            'source_version': 'petrochina-sources-20261115-v1',
                        }, ensure_ascii=False),
                        '2026-11-15T00:00:00+08:00',
                    ),
                )
            service = MarketService(directory)
            quotes_dir = service.quotes.directory
            quotes_dir.mkdir(parents=True, exist_ok=True)
            for key, item in self._sample_series().items():
                (quotes_dir / f'{key}.json').write_text(json.dumps(item, ensure_ascii=False), encoding='utf-8')

            server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
            server.store, server.market_context = store, service
            server.industry_monitor = MonitorService(directory, start_scheduler=False)
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            opener = build_opener(ProxyHandler({}))
            base = ('ht' + f'tp://127.0.0.1:{server.server_port}')
            try:
                with patch.object(service, '_run', lambda c: None):
                    with opener.open(f'{base}/api/companies/{petro_id}/market-context?as_of=2026-08-15') as resp:
                        early = json.load(resp)
                    self.assertEqual(early['pilot'], 'petrochina_market_v1')
                    self.assertFalse(early['cost']['visible'])
                    self.assertIsNone(early['cost']['current_value'])
                    self.assertEqual(early['valuation']['edition_id'], 'ed_petro_v1')
                    self.assertEqual(early['valuation']['figure_url'], f'/api/sources/{fig_id}/file')

                    with opener.open(f'{base}/api/companies/{petro_id}/market-context?as_of=2026-11-13') as resp:
                        latest = json.load(resp)
                    self.assertTrue(latest['cost']['visible'])
                    self.assertEqual(latest['cost']['current_value'], 10.68)
                    self.assertEqual(latest['trend']['status'], 'ready')

                    with opener.open(f'{base}/api/companies/{other_id}/market-context') as resp:
                        other = json.load(resp)
                    self.assertNotIn('pilot', other)
                    self.assertEqual(other['code'], '00506.HK')
            finally:
                server.shutdown()
                server.server_close()
                thread.join()
                service.close()
                server.industry_monitor.close()


if __name__ == '__main__':
    unittest.main()
