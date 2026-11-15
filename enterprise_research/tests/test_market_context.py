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
from market_context import MarketService, build_context, fit_model, prior_window_analysis
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


if __name__ == '__main__':
    unittest.main()
