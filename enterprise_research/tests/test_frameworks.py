import json
import sys
import tempfile
import threading
import unittest
from pathlib import Path
from http.server import ThreadingHTTPServer
from urllib.request import Request, build_opener, ProxyHandler

BASE=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(BASE))
from app import Store,Handler
import frameworks
import topics


class FrameworkTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.store=Store(self.tmp.name)
        self.cid=self.store.add_company(dict(name='软件框架界面测试',industry='软件',currency='USD'))
        self.other=self.store.add_company(dict(name='设备框架界面测试',industry='设备'))
        self.frame=dict(title='软件：客户、产品、交付',rationale='按续约、产品需求和服务投入理解经营。',synthesis='用持续收入支付研发和服务。',factors=[
            dict(id='customers',name='客户',question='客户为何续约？',assessment='测试判断',watch='测试资料'),
            dict(id='product',name='产品',question='产品解决什么需求？'),
            dict(id='delivery',name='交付',question='每个客户的服务成本是多少？')])
        self.topic=dict(title='续约研究',category='客户关系',body='独立测试正文',factor_ids=['customers','product'],chapter_indices=[1])
    def tearDown(self):self.tmp.cleanup()

    def test_generic_framework_and_topic_history_remain_distinct(self):
        before=self.store.company(self.cid)
        frameworks.save(self.store,self.cid,self.frame)
        saved=topics.save(self.store,self.cid,self.topic)
        original=topics.read(self.store,self.cid,saved['id'])
        updated=json.loads(json.dumps(self.frame));updated['base_revision']=1;updated['factors'][0]['name']='客户留存'
        frameworks.save(self.store,self.cid,updated)
        # A new revision records the current names; the old snapshot keeps the original names.
        topics.save(self.store,self.cid,dict(self.topic,base_revision=1),saved['id'])
        reopened=Store(self.tmp.name)
        self.assertEqual(frameworks.read(reopened,self.cid,1)['factors'][0]['name'],'客户')
        self.assertEqual(frameworks.read(reopened,self.cid)['factors'][0]['name'],'客户留存')
        self.assertEqual(topics.read(reopened,self.cid,saved['id'],1)['factor_labels'],['客户','产品'])
        self.assertEqual(topics.read(reopened,self.cid,saved['id'])['factor_labels'],['客户留存','产品'])
        self.assertEqual(original['body'],self.topic['body'])
        after=reopened.company(self.cid)
        for key in ['original','records','sources','dossier','cash','value']:
            self.assertEqual(before[key],after[key])
        self.assertIsNone(reopened.company(self.other)['research_framework'])
        with self.assertRaises(ValueError):frameworks.save(reopened,self.cid,self.frame)

    def test_three_distinct_factors_and_company_association(self):
        for invalid in [dict(self.frame,factors=self.frame['factors'][:2]),dict(self.frame,rationale=''),dict(self.frame,factors=[self.frame['factors'][0]]*3)]:
            with self.assertRaises(ValueError):frameworks.save(self.store,self.cid,invalid)
        frameworks.save(self.store,self.cid,self.frame)
        with self.assertRaises(ValueError):topics.save(self.store,self.cid,dict(self.topic,factor_ids=['brand']))
        with self.assertRaises(ValueError):topics.save(self.store,self.other,self.topic)
        # Legacy or not-yet-classified topics remain readable and editable.
        old=topics.save(self.store,self.cid,dict(self.topic,factor_ids=[]))
        self.assertEqual(topics.read(self.store,self.cid,old['id'])['factor_ids'],[])
        saved=topics.save(self.store,self.cid,self.topic)
        changes=dict(self.topic,base_revision=1);changes.pop('factor_ids')
        topics.save(self.store,self.cid,changes,saved['id'])
        self.assertEqual(topics.read(self.store,self.cid,saved['id'])['factor_ids'],self.topic['factor_ids'])

    def test_http_framework_versions_and_export(self):
        server=ThreadingHTTPServer(('127.0.0.1',0),Handler);server.store=self.store
        thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
        opener=build_opener(ProxyHandler({}));base=f'http://127.0.0.1:{server.server_port}/api/companies/{self.cid}'
        def request(path,data=None):
            req=Request(base+path,data=json.dumps(data).encode() if data else None,headers={'Content-Type':'application/json'})
            with opener.open(req,timeout=4) as r:return json.load(r)
        try:
            request('/framework',self.frame)
            request('/framework',dict(self.frame,base_revision=1,title='更新框架说明'))
            self.assertEqual(request('/framework?revision=1')['title'],self.frame['title'])
            self.assertEqual(request('')['research_framework']['revision'],2)
            self.assertEqual(len(request('/export')['company']['framework_versions']),2)
        finally:server.shutdown();server.server_close();thread.join()


if __name__=='__main__':unittest.main()
