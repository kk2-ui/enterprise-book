import importlib.util
from pathlib import Path
import tempfile
import unittest

spec = importlib.util.spec_from_file_location('source_acquisition', Path(__file__).resolve().parents[1] / 'scripts/acquire_book_sources.py')
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class ReadingNoteAcquisitionTests(unittest.TestCase):
    def test_browser_note_preserves_authored_text_and_separate_dates(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            note = root / 'reading.md'
            content = '# 阅读记录\n作者估算 <5%，不是公司披露。\n'
            note.write_text(content)
            entry = dict(id='reading', file='reading.md', url='https://example.com/article',
                         capture_method='browser_notes', published_on='2026-04-20',
                         fact_period='FY2025', author='研究作者')
            result = module.acquire(entry, root, '2026-10-29')
            self.assertEqual(Path(result['text_path']).read_text(), content)
            self.assertEqual(result['acquired_on'], '2026-10-29')
            self.assertEqual(result['published_on'], '2026-04-20')
            self.assertEqual(result['author'], '研究作者')

    def test_missing_browser_note_is_not_silently_replaced_by_html(self):
        with tempfile.TemporaryDirectory() as temp:
            with self.assertRaisesRegex(ValueError, 'must be saved after reading'):
                module.acquire(dict(id='reading', file='missing.md', url='https://example.com',
                                    capture_method='browser_notes'), Path(temp), '2026-10-29')

if __name__ == '__main__':
    unittest.main()
