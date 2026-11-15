import json
import shutil
import sys
import tempfile
import threading
import unittest
from unittest.mock import patch
from pathlib import Path
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.request import Request, build_opener, ProxyHandler

BASE=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(BASE))
from app import Store, Handler
from source_data import SourceRepository
from source_data.acquisition import collect_document, ArticleText
from source_data.disclosures import extract_row
from source_data.packages import build_package,validate_package


class SourceDataTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.root=Path(self.temp.name)
        self.store=Store(self.root);self.cid=self.store.add_company(dict(name='资料模块测试企业',currency='CNY'))
        self.repo=self.store.source_data

    def tearDown(self):self.temp.cleanup()

    def document(self,did='annual',value='120.00',nature='company_disclosure',end='2025-12-31',unit='CNY_yuan'):
        content='披露原文\n营业收入  '+value+'\n\f'
        sid=self.repo.add_source(self.cid,dict(title=did,notes='内部研究结论不应导出',published_on='2026-04-01'),content.encode(),did+'.txt')
        spec=dict(id='revenue',pages=[1],pattern='^营业收入',columns=['current'])
        row=extract_row(content.split('\f'),spec);row.update(unit=unit,scope='consolidated')
        return self.repo.save_document(self.cid,dict(id=did,title=did,nature=nature,issuer='测试主体',published_on='2026-04-01',fact_period='2025',representations=dict(original=sid,text=sid),rows=[row],periods={'current':dict(kind='cumulative_flow',start='2025-01-01',end=end)}))

    def spec(self,docs,pid='package1'):
        return dict(id=pid,company=dict(id=self.cid,name='测试企业',judgment='DO_NOT_EXPORT',dossier={'value':999}),information_cutoff='2026-11-02',documents=[dict(id=d['id'],revision=d['revision']) for d in docs],gaps=['尚未披露的项目保持未知'])

    def test_source_management_preserves_existing_ids_metadata_and_research(self):
        before=self.store.company(self.cid);sid=self.store.add_source(self.cid,dict(title='旧来源',notes='原记录'))
        self.store.update_source(sid,dict(title='补正标题'))
        self.assertEqual(self.repo.source(sid)['metadata_history'][0]['title'],'旧来源')
        self.assertEqual(self.store.company(self.cid)['original'],before['original'])
        self.assertEqual(self.store.company(self.cid)['records'],before['records'])

    def test_portable_snapshot_freezes_files_metadata_and_excludes_report(self):
        d=self.document();result=build_package(self.repo,self.cid,self.spec([d]));root=Path(result['path']);archive=Path(result['zip_path']).read_bytes()
        manifest=json.loads((root/'manifest.json').read_text());self.assertNotIn('judgment',manifest['company'])
        self.assertNotIn('内部研究结论',(root/'documents/annual/read.md').read_text())
        self.repo.update_source(d['representations']['text'],dict(title='后来更名'))
        d['title']='第二版';new=self.repo.save_document(self.cid,d);self.assertEqual(new['revision'],2)
        self.assertEqual(json.loads((root/'manifest.json').read_text())['documents'][0]['revision'],1)
        self.assertEqual(Path(result['zip_path']).read_bytes(),archive)
        moved=self.root/'other-machine';shutil.copytree(root,moved)
        self.assertEqual(validate_package(moved)['status'],'passed')
        self.assertNotIn(str(self.root),(root/'manifest.json').read_text())
        with self.assertRaisesRegex(ValueError,'已存在'):build_package(self.repo,self.cid,self.spec([d]))

    def test_future_unknown_and_internal_sources_have_distinct_meanings(self):
        d=self.document(nature='research_output')
        with self.assertRaisesRegex(ValueError,'内部研究'):build_package(self.repo,self.cid,self.spec([d]))
        d=self.document('future');d['published_on']='2027-01-01';d=self.repo.save_document(self.cid,d)
        with self.assertRaisesRegex(ValueError,'截止日'):build_package(self.repo,self.cid,self.spec([d]))
        d['published_on']='';d=self.repo.save_document(self.cid,d)
        result=build_package(self.repo,self.cid,self.spec([d]));self.assertEqual(json.loads((Path(result['path'])/'manifest.json').read_text())['documents'][0]['published_on'],'')

    def test_wrong_extracted_number_is_not_promoted_to_disclosed_fact(self):
        d=self.document();d['rows'][0]['values']['current']='999.00'
        with self.assertRaisesRegex(ValueError,'实际原件'):self.repo.save_document(self.cid,d)
        d=self.repo.document(self.cid,'annual');result=build_package(self.repo,self.cid,self.spec([d]))
        path=Path(result['path'])/'data/disclosed.json';facts=json.loads(path.read_text());facts[0]['value']='999.00';path.write_text(json.dumps(facts))
        with self.assertRaisesRegex(ValueError,'披露值'):validate_package(result['path'])

    def test_hk_integer_parenthesized_amounts_and_note_column_roundtrip(self):
        content='經營現金流  8  (483,365)  1,827,098\n\f'
        spec=dict(id='operating_cash',pages=[1],pattern='^經營現金流',columns=['2026H1','2025'],number_format='financial',skip_amounts=1)
        row=extract_row(content.split('\f'),spec)
        self.assertEqual(row['values'],{'2026H1':'-483365','2025':'1827098'})
        row.update(unit='CNY_thousand',scope='consolidated')
        sid=self.repo.add_source(self.cid,dict(title='港股报表'),content.encode(),'hk.txt')
        d=self.repo.save_document(self.cid,dict(id='hk',title='港股报表',nature='company_disclosure',fact_period='2026H1',representations=dict(original=sid,text=sid),rows=[row]))
        result=build_package(self.repo,self.cid,self.spec([d]))
        self.assertEqual(validate_package(result['path'])['disclosed_cells'],2)
        with self.assertRaisesRegex(ValueError,'amounts'):
            extract_row(['經營現金流  8  –  1,827,098'],spec)

    def test_cumulative_derivation_requires_same_unit_scope_metric_and_window(self):
        a=self.document('q3',value='120.00',end='2025-09-30');b=self.document('h1',value='75.00',end='2025-06-30')
        spec=self.spec([a,b]);spec['derived']=[dict(id='third_quarter',operation='subtract',inputs=['q3/revenue/current','h1/revenue/current'],period='2025Q3')]
        result=build_package(self.repo,self.cid,spec);self.assertEqual(json.loads((Path(result['path'])/'data/derived.json').read_text())[0]['value'],'45.00')
        spec['id']='wrong_period';spec['derived'][0]['inputs'].reverse()
        with self.assertRaisesRegex(ValueError,'累计流量'):build_package(self.repo,self.cid,spec)
        b['rows'][0]['unit']='USD';b=self.repo.save_document(self.cid,b);spec=self.spec([a,b],'wrong_unit');spec['derived']=[dict(operation='subtract',inputs=['q3/revenue/current','h1/revenue/current'])]
        with self.assertRaisesRegex(ValueError,'单位'):build_package(self.repo,self.cid,spec)

    def test_missing_source_or_browser_notes_record_failure_without_fake_document(self):
        for extra in [dict(local_path=str(self.root/'missing.pdf')),dict(capture_method='browser_notes')]:
            r=collect_document(self.repo,self.cid,dict(id='missing',title='缺失',nature='company_disclosure',**extra),'2026-11-02')
            self.assertIsNone(r['document']);self.assertEqual(r['acquisition']['status'],'failed')
        self.assertEqual(self.repo.documents(self.cid),[])
        self.assertEqual(len(self.repo.acquisitions(self.cid)),2)

    def test_article_selector_keeps_full_body_and_excludes_site_ai_summary(self):
        parser=ArticleText('article-text');parser.feed('<p>AI摘要</p><div class="article-text"><p>首段</p><p>末段</p><script>private</script></div><p>推荐</p>')
        text=''.join(parser.out);self.assertIn('首段',text);self.assertIn('末段',text)
        self.assertNotIn('AI摘要',text);self.assertNotIn('private',text);self.assertNotIn('推荐',text)

    def test_http_collection_package_download_and_old_source_reference(self):
        class PublicFixture(BaseHTTPRequestHandler):
            def log_message(self,*args):pass
            def do_GET(self):
                self.send_response(200);self.end_headers();self.wfile.write('公司披露原文'.encode())
        fixture=ThreadingHTTPServer(('127.0.0.1',0),PublicFixture);ft=threading.Thread(target=fixture.serve_forever,daemon=True);ft.start()
        server=ThreadingHTTPServer(('127.0.0.1',0),Handler);server.store=self.store;threading.Thread(target=server.serve_forever,daemon=True).start()
        base='http://127.0.0.1:'+str(server.server_port);opener=build_opener(ProxyHandler({}))
        def post(path,data):return json.load(opener.open(Request(base+path,data=json.dumps(data).encode(),headers={'Content-Type':'application/json'})))
        try:
            self.assertIn(b'dataSourcesView',opener.open(base+'/source-data.js').read())
            # Keep the actual local HTTP fixture off the workstation's public-network proxy.
            with patch('source_data.acquisition.urllib.request.urlopen',opener.open):
                r=post(f'/api/companies/{self.cid}/data/acquire',dict(id='public',title='公开材料',url=f'http://127.0.0.1:{fixture.server_port}/original.txt',nature='company_disclosure'))
            doc=r['document'];self.assertEqual(doc['revision'],1)
            self.assertEqual(opener.open(base+'/api/sources/'+doc['representations']['original']+'/file').read(),'公司披露原文'.encode())
            p=post(f'/api/companies/{self.cid}/data/packages',self.spec([doc]))
            self.assertTrue(opener.open(base+f'/api/companies/{self.cid}/data/packages/{p["id"]}/download').read().startswith(b'PK'))
            overview=json.load(opener.open(base+f'/api/companies/{self.cid}/data'));self.assertEqual(len(overview['packages']),1)
        finally:server.shutdown();server.server_close();fixture.shutdown();fixture.server_close()


if __name__=='__main__':unittest.main()
