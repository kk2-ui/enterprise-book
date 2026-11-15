import json,sys,tempfile,threading,unittest
from pathlib import Path
from http.server import ThreadingHTTPServer
from urllib.request import Request,build_opener,ProxyHandler
from urllib.error import HTTPError
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from app import Store,Handler
import model_books
from source_data.packages import build_package
from source_data import access

class ModelBooksTests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.root=Path(self.tmp.name);self.store=Store(self.root)
  self.cid=self.store.add_company({'name':'接口测试公司','currency':'CNY'});r=self.store.source_data
  sid=r.add_source(self.cid,{'title':'原文','notes':'不应进入Agent输入的旧判断'},'第一页披露收入\f第二页现金流\f'.encode(),'annual.txt')
  d=r.save_document(self.cid,dict(id='annual',title='年报',nature='company_disclosure',issuer='测试公司',fact_period='2025',published_on='2026-04-01',representations={'original':sid,'text':sid},rows=[]))
  self.v=build_package(r,self.cid,dict(id='source-v1',company={'id':self.cid,'name':'测试公司'},information_cutoff='2026-10-30',documents=[{'id':'annual','revision':d['revision']}]),create_archive=False)
 def tearDown(self):self.tmp.cleanup()
 def task(self,name='测试模型A',version='1'):
  return model_books.create_task(self.store,self.cid,{'source_version':self.v['id'],'model':{'name':name,'version':version},'title':name+'整书'})
 def fill(self,t,label):
  for key,title in model_books.REQUIRED.items():model_books.save_part(self.store,self.cid,t['id'],key,{'title':title,'body':label+'完整正文 [[doc:annual@2|现金流原页]]'})
 def test_sources_are_online_frozen_page_addressable_without_zip_or_prior_judgment(self):
  self.assertIsNone(self.v['zip_path']);m=access.manifest(self.store.source_data,self.cid,self.v['id'])
  self.assertEqual(m['documents'][0]['page_count'],2)
  self.assertIn('第二页',access.document(self.store.source_data,self.cid,self.v['id'],'annual',2)['pages'][0]['text'])
  self.assertEqual(access.search(self.store.source_data,self.cid,self.v['id'],'现金流')['results'][0]['page'],2)
  self.assertNotIn('旧判断',json.dumps(m,ensure_ascii=False))
  with self.assertRaises(ValueError):access.document(self.store.source_data,self.cid,self.v['id'],'annual',3)
  with self.assertRaises(ValueError):access.document(self.store.source_data,self.cid,self.v['id'],'other')
 def test_parts_resume_and_completion_cannot_publish_incomplete_book(self):
  t=self.task();model_books.save_part(self.store,self.cid,t['id'],'overview',{'title':'全貌','body':'实际内容'})
  self.assertEqual(model_books.task(self.store,self.cid,t['id'])['parts']['overview']['body'],'实际内容')
  with self.assertRaisesRegex(ValueError,'尚缺'):model_books.complete(self.store,self.cid,t['id'],{})
  with self.store.connect() as c:self.assertEqual(model_books.editions(c,self.cid),[])
  with self.assertRaisesRegex(ValueError,'页码'):model_books.save_part(self.store,self.cid,t['id'],'judgment',{'title':'判断','body':'[[doc:annual@9|错页]]'})
  model_books.set_status(self.store,self.cid,t['id'],{'status':'failed','message':'工具中断'})
  model_books.save_part(self.store,self.cid,t['id'],'chapter-1',{'title':'沿革','body':'恢复后内容'})
  self.assertEqual(model_books.task(self.store,self.cid,t['id'])['status'],'running')
 def test_whole_books_are_independent_and_completed_editions_are_immutable(self):
  before=self.store.company(self.cid);a=self.task();b=self.task('测试模型B','2')
  self.fill(a,'A');self.fill(b,'B');ea=model_books.complete(self.store,self.cid,a['id'],{});eb=model_books.complete(self.store,self.cid,b['id'],{})
  self.assertTrue(all(p['body'].startswith('A') for p in ea['parts'].values()))
  self.assertTrue(all(p['body'].startswith('B') for p in eb['parts'].values()))
  self.assertNotEqual(ea['id'],eb['id']);self.assertEqual(ea['review_status'],'not_reviewed')
  self.assertEqual(model_books.complete(self.store,self.cid,a['id'],{})['id'],ea['id'])
  with self.assertRaisesRegex(ValueError,'不可覆盖'):model_books.save_part(self.store,self.cid,a['id'],'valuation',{'title':'改值','body':'不应写入'})
  after=self.store.company(self.cid);self.assertEqual(before['records'],after['records']);self.assertEqual(before['original'],after['original']);self.assertEqual(before['dossier'],after['dossier'])
  b2=self.task('测试模型B','2.1');self.fill(b2,'B2');e2=model_books.complete(self.store,self.cid,b2['id'],{})
  self.assertEqual(model_books.read_edition(self.store,self.cid,eb['id'])['model']['version'],'2');self.assertEqual(e2['model']['version'],'2.1')
 def test_complete_requires_the_lifecycle_financial_and_followup_pages(self):
  t=self.task();pages={'life','history','track'}
  for key,title in model_books.REQUIRED.items():
   if key not in pages:model_books.save_part(self.store,self.cid,t['id'],key,{'title':title,'body':'已完成正文'})
  with self.assertRaisesRegex(ValueError,'生命周期.*长期财务.*后续核验'):
   model_books.complete(self.store,self.cid,t['id'],{})
  for key in pages:model_books.save_part(self.store,self.cid,t['id'],key,{'title':model_books.REQUIRED[key],'body':'本模型独立内容 '+key})
  edition=model_books.complete(self.store,self.cid,t['id'],{})
  self.assertEqual(edition['parts']['life']['body'],'本模型独立内容 life')
  self.assertEqual(edition['review_status'],'not_reviewed')
 def test_overview_financial_points_are_frozen_with_the_edition(self):
  t=self.task()
  self.fill(t,'A')
  point={'value':10,'raw':10000,'raw_unit':'人民币千元','document':'annual','page':3}
  display={'intro':'做什么生意','identity':[{'label':'主体','value':'本公司'}],
           'metrics':{'cfo':{'label':'经营现金'}},
           'series':[{'period':'FY2025','year':2025,'kind':'annual','values':{'cfo':point}}],
           'overview':{'period':'FY2025'}}
  part={'title':'全景','body':'解释经营与现金','display':display}
  with self.assertRaisesRegex(ValueError,'原件页'):
   model_books.save_part(self.store,self.cid,t['id'],'overview',part)
  point['page']=2
  model_books.save_part(self.store,self.cid,t['id'],'overview',part)
  e=model_books.complete(self.store,self.cid,t['id'],{})
  read=model_books.read_edition(self.store,self.cid,e['id'])
  self.assertEqual(read['parts']['overview']['display'],display)
 def test_task_pins_sources_and_model_identity(self):
  t=self.task();info=model_books.instructions(self.store,self.cid,t['id']);self.assertNotIn('dossier',info);self.assertNotIn('不应进入Agent输入的旧判断',str(info))
  self.fill(t,'A')
  with self.assertRaisesRegex(ValueError,'模型'):model_books.complete(self.store,self.cid,t['id'],{'model':{'name':'另一个模型','version':'1'}})
  with self.assertRaisesRegex(ValueError,'版本'):model_books.complete(self.store,self.cid,t['id'],{'model':{'name':'测试模型A','version':'2'}})
  with self.assertRaises(ValueError):model_books.read_edition(self.store,'another','missing')
 def test_external_agent_http_roundtrip(self):
  server=ThreadingHTTPServer(('127.0.0.1',0),Handler);server.store=self.store;threading.Thread(target=server.serve_forever,daemon=True).start();base='http://127.0.0.1:'+str(server.server_port);op=build_opener(ProxyHandler({}))
  def get(path):return json.load(op.open(base+path))
  def post(path,data):return json.load(op.open(Request(base+path,data=json.dumps(data).encode(),headers={'Content-Type':'application/json'})))
  try:
   api='/api/companies/'+self.cid
   t=post(api+'/book-tasks',{'source_version':self.v['id'],'model':{'name':'HTTP测试Agent','version':'test'}})
   inst=get(api+'/book-tasks/'+t['id']+'/instructions');m=get(inst['source_url']);page=get(m['documents'][0]['read_url']+'?start_page=2');self.assertIn('现金流',page['pages'][0]['text'])
   self.assertIn('workflow',inst);self.assertEqual(inst['workflow']['role'],'coordinator')
   for role,url in inst['role_instructions'].items():
    policy=get(url);self.assertEqual(policy['role'],role);self.assertNotIn('task',policy)
    for doc in policy['documents']:self.assertEqual(doc['body'],(Path(__file__).resolve().parents[1]/doc['path']).read_text())
   self.assertIn('不能只报',str(get(inst['role_instructions']['first_read'])))
   dispatch=post(inst['prepare_url'],inst['prepare_example'])
   self.assertIn('WRITING_STANDARD.md',dispatch['body'])
   self.assertIn('实际正文入口及版本',dispatch['body'])
   spec=inst['prepare_example'];spec['inputs']['reviews']=['旧稿已通过.md']
   with self.assertRaises(HTTPError) as rejection:post(inst['prepare_url'],spec)
   self.assertEqual(rejection.exception.code,400)
   rejection.exception.close()
   self.assertEqual(get(api+'/book-tasks/'+t['id'])['parts'],{})
   self.assertEqual(len(get(inst['search_url'].replace('关键词','%E7%8E%B0%E9%87%91'))['results']),1)
   for key,title in inst['required_parts'].items():post(inst['part_url'].replace('{part_id}',key),{'title':title,'body':'HTTP Agent实际写入 '+key})
   e=post(inst['complete_url'],{});self.assertEqual(get(api+'/books/'+e['id'])['parts']['valuation']['body'],'HTTP Agent实际写入 valuation')
   self.assertEqual(e['review_status'],'not_reviewed')
   self.assertEqual(len(get(api+'/books')),1);self.assertEqual(get(api+'/book-tasks')[0]['status'],'completed')
   self.assertIn(b'editionURL',op.open(base+'/model-books.js').read())
  finally:server.shutdown();server.server_close()
if __name__=='__main__':unittest.main()
