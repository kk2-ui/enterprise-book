from datetime import datetime
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from zoneinfo import ZoneInfo

from market_factors import series


class MarketFactorTests(unittest.TestCase):
    def test_new_cutoff_updates_cached_benchmark_and_excludes_ny_intraday_quote(self):
        ny = ZoneInfo('America/New_York')
        benchmark = [
            ['2025-10-14', 100, 101],
            ['2026-11-17', 110, 111],
        ]
        ny_bars = [(datetime(2025, 10, 13, tzinfo=ny), 95),
                   (datetime(2026, 11, 16, tzinfo=ny), 103.55)]

        def provider(url, referer):
            if 'gtimg.cn' in url:
                return {'code': 0, 'data': {'sh000300': {'day': benchmark[:]}}}
            return {'chart': {'result': [{
                'meta': {'symbol': 'DX-Y.NYB', 'fullExchangeName': 'ICE Futures',
                         'instrumentType': 'INDEX', 'exchangeTimezoneName': 'America/New_York'},
                'timestamp': [int(day.timestamp()) for day, _ in ny_bars],
                'indicators': {'quote': [{'close': [close for _, close in ny_bars]}]},
            }]}}

        class TestClock(datetime):
            @classmethod
            def now(cls, tz=None):
                return datetime(2026, 11, 18, 15, tzinfo=ny).astimezone(tz)

        with (tempfile.TemporaryDirectory() as directory,
              patch('market_factors.datetime', TestClock),
              patch('market_factors.fetch', side_effect=provider)):
            first = series(Path(directory), 'sh000300', '2026-11-17')
            self.assertEqual(first['benchmark']['points'][-1]['close'], 111)
            self.assertEqual(first['dxy']['points'][-1]['close'], 103.55)
            benchmark.append(['2026-11-18', 112, 115])
            ny_bars.extend([(datetime(2026, 11, 17, tzinfo=ny), 103.49),
                           (datetime(2026, 11, 18, 14, tzinfo=ny), 106.88)])
            second = series(Path(directory), 'sh000300', '2026-11-18')
            self.assertEqual(second['benchmark']['points'][-1], {'date': '2026-11-18', 'close': 115})
            self.assertEqual(second['dxy']['points'][-1],
                             {'date': '2026-11-18', 'session': '2026-11-17', 'close': 103.49})
            earlier = series(Path(directory), 'sh000300', '2026-11-17')
            self.assertEqual(earlier['benchmark']['points'][-1]['date'], '2026-11-17')
            self.assertEqual(earlier['dxy']['points'][-1]['session'], '2026-11-16')
