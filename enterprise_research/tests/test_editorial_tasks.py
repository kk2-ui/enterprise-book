import copy
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import editorial_tasks


class EditorialTaskTests(unittest.TestCase):
    def setUp(self):
        self.spec = dict(role='first_read', company='测试公司', question='客户如何付款？',
                         scope='专题r2全文和实际图片', output='本批/首读意见.md',
                         end_condition='复述理解、信息增量与图文取舍，标明未审范围',
                         inputs=dict(manuscript=['本批/稿件r2.md'], figures=['本批/付款关系.png']))

    def test_writer_and_reader_receive_current_full_writing_standard(self):
        expected = (editorial_tasks.ROOT/'WRITING_STANDARD.md').read_text()
        for role in ['writer', 'first_read', 'recheck']:
            docs = editorial_tasks.instructions(role)['documents']
            self.assertEqual(next(d['body'] for d in docs if d['path']=='WRITING_STANDARD.md'), expected)
        rendered = editorial_tasks.prepare(self.spec)
        self.assertIn(expected, rendered)
        self.assertIn('本批/稿件r2.md', rendered)
        self.assertIn('本批/付款关系.png', rendered)
        self.assertIn('信息推进', rendered)

    def test_first_read_rejects_author_context_and_previous_acceptance(self):
        for category in ['evidence', 'reviews', 'work_map']:
            spec = copy.deepcopy(self.spec)
            spec['inputs'][category] = ['旧稿已经通过，请沿用作者结论.md']
            with self.assertRaisesRegex(ValueError, '首读只交'):
                editorial_tasks.prepare(spec)

    def test_recheck_cannot_receive_only_author_reply_without_revised_manuscript(self):
        spec = copy.deepcopy(self.spec)
        spec.update(role='recheck', inputs=dict(reviews=['原意见.md', '作者回复.md']))
        with self.assertRaisesRegex(ValueError, '实际修订稿'):
            editorial_tasks.prepare(spec)
        spec['inputs']['manuscript'] = ['修订r3完整稿.md']
        self.assertIn('修订r3完整稿.md', editorial_tasks.prepare(spec))

    def test_new_dispatch_reads_updated_canonical_file_without_changing_old_dispatch(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            for name in editorial_tasks.ROLES['first_read'][1]:
                target = root/name
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_text('本次标准原文A')
            with patch.object(editorial_tasks, 'ROOT', root):
                first = editorial_tasks.prepare(self.spec)
                (root/'WRITING_STANDARD.md').write_text('后续标准原文B')
                second = editorial_tasks.prepare(self.spec)
            self.assertIn('后续标准原文B', second)
            self.assertNotIn('后续标准原文B', first)

    def test_unbounded_assignment_is_not_dispatched(self):
        spec = copy.deepcopy(self.spec)
        spec.pop('scope')
        with self.assertRaisesRegex(ValueError, 'scope'):
            editorial_tasks.prepare(spec)


if __name__ == '__main__':
    unittest.main()
