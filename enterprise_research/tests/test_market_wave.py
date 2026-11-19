from pathlib import Path
import tempfile
import unittest

from market_wave import detect, publish, response


class MarketWaveTests(unittest.TestCase):
    def test_ongoing_and_closed_swings_retain_the_same_signal(self):
        opening = [('2026-11-02', 100), ('2026-11-03', 96), ('2026-11-04', 103)]
        first = detect(opening)
        self.assertEqual(len(first), 1)
        self.assertEqual((first[0]['start'], first[0]['signal_on']), ('2026-11-03', '2026-11-04'))
        self.assertFalse(first[0]['closed'])
        later = detect(opening + [('2026-11-05', 107), ('2026-11-06', 99)])
        self.assertEqual(later[0]['id'], first[0]['id'])
        self.assertEqual(later[0]['end'], '2026-11-05')
        self.assertTrue(later[0]['closed'])
        self.assertLess(later[-1]['change'], 0)

    def test_reviewed_case_replaces_pending_and_hides_future_evidence(self):
        code = '000999.SZ'
        chart = [dict(date='2026-11-02', values={code: 100}), dict(date='2026-11-03', values={code: 110}),
                 dict(date='2026-11-04', values={code: 120})]
        case = {
            'start': '2026-11-02', 'end': '2026-11-04', 'model': 'Gemini', 'reviewed_by': 'Codex',
            'notes': [
                dict(date=day, kind='公告', title=day, text='已核资料，资金归属暂未查清。',
                     sources=[dict(label='公告原件', url='https://example.org/filing')])
                for day in ('2026-11-03', '2026-11-04')
            ],
        }
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.assertEqual(len(response(root, code, chart, '2026-11-04')['pending']), 1)
            with self.assertRaises(ValueError):
                publish(root, code, case, '2026-11-03')
            publish(root, code, case, '2026-11-04')
            full = response(root, code, chart, '2026-11-04')
            self.assertEqual(full['pending'], [])
            slight_move = chart + [dict(date='2026-11-05', values={code: 122})]
            self.assertEqual(response(root, code, slight_move, '2026-11-05')['pending'], [])
            material_move = chart + [dict(date='2026-11-05', values={code: 125})]
            self.assertEqual(len(response(root, code, material_move, '2026-11-05')['pending']), 1)
            self.assertEqual(len(full['reviewed'][0]['notes']), 2)
            prior = response(root, code, chart, '2026-11-03')['reviewed'][0]
            self.assertEqual(prior['end'], '2026-11-03')
            self.assertEqual([note['date'] for note in prior['notes']], ['2026-11-03'])

    def test_existing_studies_cover_their_original_dates(self):
        with tempfile.TemporaryDirectory() as directory:
            for code in ('000651.SZ', '06049.HK'):
                self.assertEqual(response(Path(directory), code, [], '2026-10-20')['reviewed'], [])
                waves = response(Path(directory), code, [], '2026-11-12')['reviewed']
                self.assertTrue(waves and len(waves[0]['notes']) > 0)
                self.assertTrue(all(n['date'] <= '2026-11-12' for n in waves[0]['notes']))
