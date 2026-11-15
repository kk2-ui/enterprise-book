import json
import sys
import tempfile
import threading
import unittest
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, build_opener, ProxyHandler
from http.server import ThreadingHTTPServer

BASE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BASE))
from app import Store, Handler
import topics


class TopicTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.store = Store(self.tmp.name)
        self.cid = self.store.add_company(dict(name='专题测试软件企业', industry='软件', currency='USD'))
        self.other = self.store.add_company(dict(name='专题测试设备企业', industry='设备'))
        self.sid = self.store.add_source(self.cid, dict(title='客户留存资料', notes='仅用于隔离测试'))
        self.base = dict(title='订阅续约与研发投入', category='客户与产品', summary='测试主要判断',
                         body=f'## 经营过程\n\n测试正文。[[source:{self.sid}@3|客户资料第3页]]',
                         chapter_indices=[1, 2, 5], source_ids=[], record_ids=[], forecast_ids=[])

    def tearDown(self):
        self.tmp.cleanup()

    def test_company_without_dossier_can_edit_and_read_history_after_restart(self):
        before = self.store.company(self.cid)
        first = topics.save(self.store, self.cid, self.base)
        second = topics.save(self.store, self.cid, dict(self.base, body='修订后的经营判断', base_revision=1), first['id'])
        reopened = Store(self.tmp.name)
        old = topics.read(reopened, self.cid, first['id'], 1)
        self.assertEqual(old['body'], self.base['body'])
        self.assertEqual(old['source_ids'], [self.sid])
        current = topics.read(reopened, self.cid, first['id'])
        self.assertEqual(second['revision'], 2)
        self.assertEqual(current['body'], '修订后的经营判断')
        self.assertEqual([v['revision'] for v in current['history']], [2, 1])
        after = reopened.company(self.cid)
        self.assertNotIn('body', after['topics'][0])
        summary=next(c for c in reopened.workspace()['companies'] if c['id']==self.cid)
        self.assertEqual(summary['topic_count'],1)
        self.assertGreaterEqual(summary['research_updated_at'],current['updated_at'])
        self.assertEqual({k: v for k, v in after.items() if k != 'topics'}, {k: v for k, v in before.items() if k != 'topics'})
        with reopened.connect() as conn:
            self.assertEqual(len(topics.export(conn, self.cid)), 2)
        with self.assertRaises(ValueError):
            topics.save(reopened, self.cid, dict(self.base, base_revision=1), first['id'])

    def test_forecasts_and_tracking_are_links_not_copied_or_overwritten(self):
        self.store.add_record(self.cid, 'prediction', dict(title='测试预测', body='订阅收入变化', forecast_id='S1', definition='定义', deadline='FY2027报告', falsifier='测试反证'))
        original = self.store.company(self.cid)['original']
        topic = topics.save(self.store, self.cid, dict(self.base, forecast_ids=['S1']))
        rid = self.store.add_record(self.cid, 'task', dict(title='续约跟踪', body='取得经营事实', topic_id=topic['id'], forecast_id='S1'))
        topic = topics.save(self.store, self.cid, dict(self.base, base_revision=1, record_ids=[rid], forecast_ids=['S1']), topic['id'])
        self.assertEqual(topics.read(self.store, self.cid, topic['id'])['record_ids'], [rid])
        self.assertEqual(self.store.company(self.cid)['original'], original)
        self.store.task_status(rid, '已完成')
        self.assertFalse(any(r['kind'] == 'review' for r in self.store.company(self.cid)['records']))

    def test_associations_cannot_silently_mix_company_evidence(self):
        alien = self.store.add_source(self.other, dict(title='设备资料', notes='测试'))
        for changes in (dict(source_ids=[alien]), dict(body=f'[[source:{alien}|别家资料]]'), dict(forecast_ids=['missing']), dict(chapter_indices=[8])):
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                topics.save(self.store, self.cid, dict(self.base, **changes))
        topic = topics.save(self.store, self.other, dict(self.base, body='设备研发', source_ids=[]))
        with self.assertRaises(ValueError):
            self.store.add_record(self.cid, 'task', dict(title='测试', body='测试', topic_id=topic['id']))
        with self.assertRaises(ValueError):
            topics.read(self.store, self.cid, topic['id'])
        with self.assertRaises(ValueError):
            topics.save(self.store, self.cid, dict(self.base, body=''))

    def test_same_topic_id_in_two_companies_keeps_separate_current_editions(self):
        topics.save(self.store, self.cid, self.base, 'capital-return')
        topics.save(self.store, self.other, dict(self.base, body='设备资本开支'), 'capital-return')
        topics.save(self.store, self.cid, dict(self.base, base_revision=1), 'capital-return')
        self.assertEqual(self.store.company(self.cid)['topics'][0]['revision'], 2)
        self.assertEqual(self.store.company(self.other)['topics'][0]['revision'], 1)

    def test_figures_associate_uploaded_images_and_preserve_history(self):
        sid = self.store.add_source(self.cid, dict(title='经营流程图'), b'PNG test fixture', 'flow.PNG')
        first = topics.save(self.store, self.cid, self.base)
        body = self.base['body'] + f'\n\n[[figure:{sid}|图1 经营流程]]'
        topics.save(self.store, self.cid, dict(self.base, body=body, base_revision=1), first['id'])
        current = topics.read(self.store, self.cid, first['id'])
        self.assertEqual(current['source_ids'], [self.sid, sid])
        self.assertEqual(current['body'], body)
        self.assertEqual(topics.read(self.store, self.cid, first['id'], 1)['body'], self.base['body'])

    def test_figures_require_images_of_the_same_company(self):
        pdf = self.store.add_source(self.cid, dict(title='PDF'), b'PDF test fixture', 'source.pdf')
        alien = self.store.add_source(self.other, dict(title='别家图片'), b'PNG test fixture', 'flow.png')
        for sid in [self.sid, pdf, alien, 'missing']:
            with self.subTest(sid=sid), self.assertRaises(ValueError):
                topics.save(self.store, self.cid, dict(self.base, body=f'[[figure:{sid}|流程图]]'))

    def test_generic_import_reuses_sources_and_preserves_existing_research(self):
        sys.path.insert(0,str(BASE/'scripts'))
        from import_topics import import_topics
        pack=Path(self.tmp.name)/'topics.json'
        pack.write_text(json.dumps(dict(company_id=self.cid,topics=[dict(self.base,id='renewals')]),ensure_ascii=False))
        before=self.store.company(self.cid)
        import_topics(self.store,pack)
        self.assertEqual(import_topics(self.store,pack)[0]['status'],'already imported')
        after=self.store.company(self.cid)
        for key in ['sources','records','original','dossier','cash','value']:
            self.assertEqual(before[key],after[key])
        self.assertEqual(after['topics'][0]['revision'],1)

    def test_http_save_read_export_and_missing_routes(self):
        server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
        server.store = self.store
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        opener = build_opener(ProxyHandler({}))
        base = f'http://127.0.0.1:{server.server_port}'
        def request(path, data=None):
            req = Request(base + path, data=json.dumps(data).encode() if data is not None else None,
                          headers={'Content-Type': 'application/json'})
            with opener.open(req, timeout=4) as response:
                return json.load(response)
        try:
            root = f'/api/companies/{self.cid}'
            saved = request(root + '/topics', self.base)
            tid = saved['id']
            request(root + '/topics/' + tid, dict(self.base, title='新的标题', base_revision=1))
            self.assertEqual(request(root + '/topics/' + tid)['revision'], 2)
            self.assertEqual(request(root + '/topics/' + tid + '?revision=1')['title'], self.base['title'])
            self.assertEqual(len(request(root + '/export')['company']['topic_versions']), 2)
            self.assertEqual(request(root)['topics'][0]['title'], '新的标题')
            with self.assertRaises(HTTPError) as err:
                request(root + '/topics/' + tid, dict(self.base, base_revision=1))
            self.assertEqual(err.exception.code, 400)
            err.exception.close()
            with self.assertRaises(HTTPError) as err:
                request(root + '/topics/missing', self.base)
            self.assertEqual(err.exception.code, 400)
            err.exception.close()
            with opener.open(base + '/topics.js') as response:
                self.assertIn(b'topicsView', response.read())
        finally:
            server.shutdown()
            server.server_close()
            thread.join()


if __name__ == '__main__':
    unittest.main()
