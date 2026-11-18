import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from tempfile import TemporaryDirectory
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import market_atlas
from market_observation import response


class MarketAtlasTests(unittest.TestCase):
    def atlas(self, code, cutoff, days=120):
        with TemporaryDirectory() as directory, patch('market_observation.completed_date', return_value='2026-11-17'):
            company = {'id': 'new-id', 'name': '公司', 'code': code, 'sources': [], 'book_editions': []}
            data = response(SimpleNamespace(directory=Path(directory)), company, cutoff)
            return market_atlas.build(data, days)

    def test_region_mix_uses_the_annual_report_disclosure_date(self):
        before = self.atlas('600690.SH', '2026-03-26')['operating']
        published = self.atlas('600690.SH', '2026-03-27')['operating']
        self.assertFalse(before['visualItems'])
        self.assertNotIn('source', before)
        self.assertAlmostEqual(sum(r['sharePct'] for r in published['visualItems']), 100)
        self.assertAlmostEqual(published['visualItems'][0]['sharePct'], 48.47, places=2)
        self.assertTrue(published['source'].endswith('#page=225'))

    def test_disclosed_weekend_event_visible_before_next_price(self):
        before = self.atlas('601857.SH', '2026-08-29')
        first = self.atlas('601857.SH', '2026-08-30')
        self.assertFalse(before['operating']['visualItems'])
        self.assertEqual([v['value'] for v in first['operating']['visualItems']], [10.14, 10.68])
        event, = first['mainChart']['events']
        self.assertEqual((event['firstDisclosed'], event['date'], event['onChart']),
                         ('2026-08-30', '2026-08-31', False))
        self.assertFalse(first['valuation']['available'])
        self.assertNotIn('url', first['valuation'])
