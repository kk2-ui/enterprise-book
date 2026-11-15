import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from extract_disclosure_rows import extract_row


class DisclosureRowsTest(unittest.TestCase):
    def test_negative_finance_and_note_number(self):
        row = extract_row(['财务费用 五、60 -4,086,088,396.47 -3,300,417,558.96'],
                          dict(id='finance', pages=[1], pattern='^财务费用', columns=['2025', '2024']))
        self.assertEqual(row['values'], {'2025': '-4086088396.47', '2024': '-3300417558.96'})

    def test_wrapped_original_row(self):
        row = extract_row(['固定资产折旧、投资性房地产折旧\n 2,153,738,979.49 2,423,470,288.05\n及使用权资产摊销'],
                          dict(id='depreciation', pages=[1], pattern='^固定资产折旧', following_lines=2, columns=['2026H1', '2025H1']))
        self.assertEqual(row['values']['2026H1'], '2153738979.49')
        self.assertIn('使用权资产', row['source_excerpt'])

    def test_missing_column_does_not_shift_or_fill_zero(self):
        with self.assertRaises(ValueError):
            extract_row(['手续费及佣金收入 83.29'], dict(id='commission', pages=[1], pattern='^手续费', columns=['2025', '2024']))

    def test_ambiguous_row_requires_explicit_selection(self):
        with self.assertRaises(ValueError):
            extract_row(['利息收入 1.00 2.00\n利息收入 3.00 4.00'], dict(id='interest', pages=[1], pattern='^利息收入', columns=['current', 'prior']))
