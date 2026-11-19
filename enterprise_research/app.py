#!/usr/bin/env python3
"""Independent, localhost enterprise research book. Python standard library only."""
import argparse, json, mimetypes, sqlite3, uuid, re
from contextlib import contextmanager
from datetime import datetime, date
from email.parser import BytesParser
from email.policy import default
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse, parse_qs, quote
from seed import CHAPTERS
import catalog
import topics
import frameworks
import research_workspace
import model_books
import editorial_tasks
from market_context import MarketService
import market_observation
import company_market_observation
import market_nbs
import market_wave
import market_factors
import market_atlas
from market_observation_update import ObservationUpdater
from industry_monitor.service import MonitorService
from source_data import access as source_access
from source_data import SourceRepository
from source_data.acquisition import collect_document
from source_data.packages import build_package

BASE=Path(__file__).resolve().parent
KINDS={'judgment','event','task','observation','review','note','prediction','metric','valuation'}

def now(): return datetime.now().astimezone().isoformat(timespec='seconds')
def uid(): return uuid.uuid4().hex[:16]
def encode(x): return json.dumps(x,ensure_ascii=False)

class Store:
    def __init__(self, directory):
        self.directory=Path(directory).resolve(); self.directory.mkdir(parents=True,exist_ok=True)
        self.source_data=SourceRepository(self.directory)
        self.db=self.directory/'research.db'; (self.directory/'uploads').mkdir(exist_ok=True)
        with self.connect() as c:
            c.executescript('''CREATE TABLE IF NOT EXISTS companies(id TEXT PRIMARY KEY,data TEXT NOT NULL,original TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS records(id TEXT PRIMARY KEY,company_id TEXT NOT NULL,kind TEXT NOT NULL,data TEXT NOT NULL,created_at TEXT NOT NULL);
            CREATE INDEX IF NOT EXISTS records_company ON records(company_id,kind);
            CREATE TABLE IF NOT EXISTS meta(key TEXT PRIMARY KEY,value TEXT);
            CREATE TABLE IF NOT EXISTS collections(id TEXT PRIMARY KEY,name TEXT NOT NULL UNIQUE,created_at TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS collection_members(collection_id TEXT NOT NULL,company_id TEXT NOT NULL,PRIMARY KEY(collection_id,company_id));
            CREATE TABLE IF NOT EXISTS saved_views(id TEXT PRIMARY KEY,name TEXT NOT NULL,filters TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS dossiers(company_id TEXT NOT NULL,version TEXT NOT NULL,data TEXT NOT NULL,created_at TEXT NOT NULL,PRIMARY KEY(company_id,version));''')
            c.executescript(topics.SCHEMA + frameworks.SCHEMA + research_workspace.SCHEMA + model_books.SCHEMA)
    @contextmanager
    def connect(self):
        c=sqlite3.connect(self.db); c.row_factory=sqlite3.Row
        try:
            with c: yield c
        finally: c.close()
    def _record(self,c,cid,kind,data):
        rid=uid(); c.execute('INSERT INTO records VALUES(?,?,?,?,?)',(rid,cid,kind,encode(data),now())); return rid
    def company(self,cid):
        with self.connect() as c:
            row=c.execute('SELECT * FROM companies WHERE id=?',(cid,)).fetchone()
            if not row: raise ValueError('企业不存在')
            d=json.loads(row['data']); d['original']=json.loads(row['original'])
            d['sources']=[dict(id=r['id'],company_id=cid,created_at=r['created_at'],**json.loads(r['data'])) for r in c.execute('SELECT * FROM sources WHERE company_id=? ORDER BY rowid',(cid,))]
            for s in d['sources']: s['available']=not s['path'] or Path(s['path']).is_file()
            d['records']=[dict(id=r['id'],kind=r['kind'],created_at=r['created_at'],**json.loads(r['data'])) for r in c.execute('SELECT * FROM records WHERE company_id=? ORDER BY rowid DESC',(cid,))]
            latest=next((r for r in d['records'] if r['kind']=='judgment'),{})
            if latest.get('stage'): d['stage']=latest['stage']
            valuation=next((r for r in d['records'] if r['kind']=='valuation'),{})
            if valuation:
                d['cash']=valuation['cash']; d['value']=valuation['value']; d['cash_label']=valuation['cash_label']; d['value_label']=valuation['value_label']
                d['valuation_updated_on']=valuation['created_at'][:10]
            d['organization']={**catalog.org_defaults(d),**d.get('organization',{})}
            d['collections']=[r[0] for r in c.execute('SELECT collection_id FROM collection_members WHERE company_id=?',(cid,))]
            dossier=c.execute('SELECT data FROM dossiers WHERE company_id=? ORDER BY rowid DESC LIMIT 1',(cid,)).fetchone()
            d['dossier']=json.loads(dossier[0]) if dossier else None
            d['dossier_versions']=[dict(r) for r in c.execute('SELECT version,created_at FROM dossiers WHERE company_id=? ORDER BY rowid DESC',(cid,))]
            d['topics']=topics.listing(c,cid)
            if basis := (d['dossier'] or {}).get('research_basis'):
                d['dossier_topics'] = [topics.unpack(c.execute(
                    'SELECT * FROM research_topics WHERE company_id=? AND id=? AND revision=?',
                    (cid, t['id'], t['revision'])).fetchone(), summary=True)
                    for t in basis.get('topic_versions', [])]
            d['research_framework']=frameworks.current(c,cid)
            d['book_editions']=model_books.editions(c,cid)
            return d
    def all(self):
        with self.connect() as c: ids=[r[0] for r in c.execute('SELECT id FROM companies ORDER BY id')]
        return [self.company(i) for i in ids]
    def source(self,sid):
        return self.source_data.source(sid)
    def add_source(self,cid,data,content=None,filename=None):
        self.company(cid)
        return self.source_data.add_source(cid,data,content,filename)
    def update_source(self,sid,data):
        return self.source_data.update_source(sid,data)
    def add_record(self,cid,kind,data):
        company=self.company(cid)
        if kind not in KINDS: raise ValueError('未知记录类型')
        if not str(data.get('title','')).strip(): raise ValueError('请填写标题')
        if not str(data.get('body','')).strip(): raise ValueError('请填写内容')
        sid=data.get('source_id','')
        if sid and not any(s['id']==sid for s in company['sources']): raise ValueError('引用资料不属于该企业')
        if data.get('topic_id') and not any(t['id']==data['topic_id'] for t in company['topics']): raise ValueError('关联专题不属于该企业')
        forecasts=[f['id'] for f in company['original'].get('forecasts',[])]+[r['forecast_id'] for r in company['records'] if r['kind']=='prediction']
        if kind!='prediction' and data.get('forecast_id') and data['forecast_id'] not in forecasts: raise ValueError('预测不存在')
        if kind in ('observation','review','metric','valuation') and not sid: raise ValueError('观察和复盘须关联资料；可先录入原始公告或研究笔记')
        if kind=='observation':
            if not data.get('fact_period'): raise ValueError('请填写事实期间')
            if not data.get('published_on'): raise ValueError('请填写资料公开日')
            if data['published_on']>date.today().isoformat(): raise ValueError('公开日不能晚于今天；未来内容应记为条件或预测')
        if kind=='valuation':
            if not all(data.get(k,'').strip() for k in ['cash','value','cash_label','value_label']): raise ValueError('现金与价值须同时注明数值、单位及条件')
        if kind=='prediction':
            if not data.get('forecast_id') or data['forecast_id'] in forecasts: raise ValueError('新预测编号不能为空或与既有预测重复')
            if not all(data.get(k,'').strip() for k in ['definition','deadline','falsifier']): raise ValueError('新预测须包含指标定义、期限和反证')
        if kind=='metric':
            import math
            try: val=float(data.get('value',''))
            except (ValueError,TypeError): raise ValueError('指标数值必须是数字')
            if not math.isfinite(val): raise ValueError('指标数值必须有限')
            if data.get('metric') not in ('B','A'): raise ValueError('目前支持已定义的B、A指标；其他指标请附计算底稿')
            if not re.fullmatch(r'(FY20\d{2}|20\d{2}H1)',data.get('period','')): raise ValueError('期间请使用FY2026或2027H1格式')
            if not data.get('published_on') or data['published_on']>date.today().isoformat(): raise ValueError('请填写已发生的公开日')
            period=data['period']; year=period[2:] if period.startswith('FY') else period[:4]
            end=year+('-12-31' if period.startswith('FY') else '-06-30')
            if data['published_on']<end: raise ValueError('完整期间现金不能早于该期间结束日披露；过程信息请记为观察')
            if data.get('currency')!=company['currency']: raise ValueError('指标币种须与公司报告币种一致')
            data['value']=val
        if kind=='judgment':
            previous=next((r for r in company['records'] if r['kind']=='judgment'),None)
            data['supersedes_id']=previous['id'] if previous else None
        if kind=='task': data['status']='待资料'
        with self.connect() as c: return self._record(c,cid,kind,data)
    def task_status(self,rid,status):
        if status not in ('待资料','待披露','进行中','已完成'): raise ValueError('未知任务状态')
        with self.connect() as c:
            row=c.execute("SELECT * FROM records WHERE id=? AND kind='task'",(rid,)).fetchone()
            if not row: raise ValueError('任务不存在')
            data=json.loads(row['data']); data['status']=status; data['updated_at']=now()
            c.execute('UPDATE records SET data=? WHERE id=?',(encode(data),rid))
    def workspace(self):
        return dict(catalog.overview(self),chapters=CHAPTERS,as_of='2026-10-27',version='0.12',mode='本地研究工作区')
    def organize(self,ids,changes):
        if not isinstance(ids,list) or not ids:raise ValueError('请先选择企业')
        ids=list(dict.fromkeys(ids))
        status=changes.get('research_status')
        if status is not None and status not in catalog.RESEARCH_STATUSES:raise ValueError('研究状态不正确')
        if 'tags' in changes and not isinstance(changes['tags'],list):raise ValueError('标签须为列表')
        if 'pinned' in changes and not isinstance(changes['pinned'],bool):raise ValueError('收藏状态不正确')
        with self.connect() as c:
            collection=changes.get('add_collection')
            if collection and not c.execute('SELECT 1 FROM collections WHERE id=?',(collection,)).fetchone():raise ValueError('专题不存在')
            values=[]
            for cid in ids:
                row=c.execute('SELECT data FROM companies WHERE id=?',(cid,)).fetchone()
                if not row:raise ValueError('企业不存在，未更新任何企业')
                d=json.loads(row[0]); org={**catalog.org_defaults(d),**d.get('organization',{})}
                for key in ('research_status','sector','market','tags','pinned'):
                    if key in changes:org[key]=changes[key]
                org['tags']=list(dict.fromkeys(str(t).strip() for t in org['tags'] if str(t).strip()))
                d['organization']=org;d['organization_updated_at']=now();values.append((encode(d),cid))
            c.executemany('UPDATE companies SET data=? WHERE id=?',values)
            if collection:c.executemany('INSERT OR IGNORE INTO collection_members VALUES(?,?)',[(collection,cid) for cid in ids])
            if changes.get('remove_collection'):c.executemany('DELETE FROM collection_members WHERE collection_id=? AND company_id=?',[(changes['remove_collection'],cid) for cid in ids])
        return len(ids)
    def create_collection(self,name):
        name=str(name).strip()
        if not name:raise ValueError('专题名称不能为空')
        with self.connect() as c:
            existing=c.execute('SELECT id FROM collections WHERE name=?',(name,)).fetchone()
            if existing:return existing[0]
            cid=uid();c.execute('INSERT INTO collections VALUES(?,?,?)',(cid,name,now()));return cid
    def save_view(self,name,filters):
        if not str(name).strip():raise ValueError('视图名称不能为空')
        allowed=('q','status','sector','market','tag','collection','pinned','needs','sort')
        clean={k:str(filters[k]) for k in allowed if filters.get(k)}
        with self.connect() as c:
            vid=uid();c.execute('INSERT INTO saved_views VALUES(?,?,?)',(vid,name.strip(),encode(clean)));return vid
    def delete_view(self,vid):
        with self.connect() as c:c.execute('DELETE FROM saved_views WHERE id=?',(vid,))
    def add_company(self,data):
        if not data.get('name','').strip(): raise ValueError('请填写企业名称')
        cid=uid()
        clean=dict(created_at=now(),id=cid,name=data['name'].strip(),code=data.get('code',''),industry=data.get('industry','待研究'),currency=data.get('currency','CNY'),stage='尚未形成判断',color='teal',summary='从原始资料开始建立企业书。',thesis='',rival='',triggers='',cash='—',cash_label='正常现金尚未估计',value='—',value_label='尚未估值',next='添加第一份资料与研究判断。',chapters=['尚未整理；请添加资料及章节笔记。']*len(CHAPTERS))
        with self.connect() as c: c.execute('INSERT INTO companies VALUES(?,?,?)',(cid,encode(clean),encode({'forecasts':[], 'observation_log':[], 'weights':{'quality':.4,'value':.45,'market':.15}})))
        return cid

class Handler(BaseHTTPRequestHandler):
    server_version='EnterpriseBook/0.1'
    def log_message(self,fmt,*args): print(f'{now()} {fmt % args}',flush=True)
    def send(self,status,body,ctype='application/json; charset=utf-8',headers=None):
        if not isinstance(body,bytes): body=body.encode('utf-8')
        self.send_response(status); self.send_header('Content-Type',ctype); self.send_header('Content-Length',str(len(body))); self.send_header('X-Content-Type-Options','nosniff'); self.send_header('Cache-Control','no-store')
        for k,v in (headers or {}).items(): self.send_header(k,v)
        self.end_headers(); self.wfile.write(body)
    def do_GET(self):
        try:
            u=urlparse(self.path); p=u.path
            if p=='/api/state': return self.send(200,encode(self.server.store.workspace()))
            if p=='/api/market-observation/refresh-status':
                return self.send(200,encode(self.server.observation_updater.status()))
            q={k:v[0] for k,v in parse_qs(u.query).items()}
            if p=='/api/industries/property/monitor':
                return self.send(200,encode(self.server.industry_monitor.sector(q.get('run'))))
            if p=='/api/industries/property/monitor/export':
                from industry_monitor.presentation import offline
                return self.send(200,offline(self.server.industry_monitor.sector(q.get('run'))),'text/html; charset=utf-8')
            m=re.fullmatch(r'/api/monitor-jobs/([\w-]+)',p)
            if m:return self.send(200,encode(self.server.industry_monitor.repo.job(m[1])))
            m=re.fullmatch(r'/api/research-subjects/([\w-]+)/monitor',p)
            if m:return self.send(200,encode(self.server.industry_monitor.subject(m[1],q.get('run'))))
            m=re.fullmatch(r'/api/companies/([\w-]+)/market-context/macro',p)
            if m:
                company=self.server.store.company(m[1])
                code=company_market_observation.stock_code(company)
                profile=company_market_observation.DRIVERS.get(code)
                if not profile:
                    return self.send(404,encode({'error':'该公司尚未配置行业统计指标'}))
                selected=company_market_observation.selected_edition(self.server.store,company,q.get('edition'))
                cutoff=market_observation.observation_cutoff(q.get('as_of'))
                limit=company_market_observation.historical_limit(selected)
                cutoff=min(cutoff,limit) if limit else cutoff
                directory=self.server.store.directory
                result=market_nbs.series(directory,profile['macro'],cutoff)
                benchmark=profile.get('benchmark')
                if benchmark:
                    result['market']=market_factors.series(directory,benchmark,cutoff)
                return self.send(200,encode(result))
            m=re.fullmatch(r'/api/companies/([\w-]+)/market-context',p)
            if m:
                company=self.server.store.company(m[1])
                if q.get('observation') == '1':
                    edition=company_market_observation.selected_edition(self.server.store,company,q.get('edition'))
                    cutoff=market_observation.observation_cutoff(q.get('as_of'))
                    limit=(company_market_observation.historical_limit(edition)
                           if q.get('edition') or company.get('default_book_edition_id') else None)
                    if limit:
                        cutoff=min(cutoff,limit)
                    key=market_observation.observation_key(company)
                    if key:
                        result=market_observation.response(self.server.store,company,cutoff)
                        result['historical_limit']=limit
                        if edition:
                            result['cards'].extend(company_market_observation.disclosures(
                                self.server.store,company,edition,cutoff))
                        if edition and edition['id'] != result['valuation'].get('edition_id'):
                            result['valuation']=company_market_observation.valuation(company,edition,cutoff)
                            result['price_snapshot']=None
                        if q.get('layout') == 'atlas':
                            result['atlas']=market_atlas.build(result,int(q.get('days','120')))
                        result['refresh']=self.server.observation_updater.status()
                    else:
                        result=company_market_observation.response(self.server.store,company,cutoff,edition,limit)
                    result['attribution']=market_wave.response(self.server.store.directory,
                        company_market_observation.stock_code(company),result['chart'],cutoff)
                    return self.send(200,encode(result))
                extra={'as_of':q['as_of']} if q.get('as_of') else {}
                return self.send(200,encode(self.server.industry_monitor.overview(company,q.get('run')) or self.server.market_context.response(company,**extra)))
            m=re.fullmatch(r'/api/companies/([\w-]+)/data/versions(?:/([\w-]+))?(?:/(facts|search|documents)(?:/([\w-]+))?(?:/(original))?)?',p)
            if m:
                repo=self.server.store.source_data;q={k:v[0] for k,v in parse_qs(u.query).items()}
                if not m[2]:result=repo.packages(m[1])
                elif m[5]:
                    path=source_access.original(repo,m[1],m[2],m[4])
                    return self.send(200,path.read_bytes(),mimetypes.guess_type(path)[0] or 'application/octet-stream')
                elif m[3]=='documents':result=source_access.document(repo,m[1],m[2],m[4],q.get('start_page',1),q.get('end_page'))
                elif m[3]=='facts':result=source_access.facts(repo,m[1],m[2],q.get('document'))
                elif m[3]=='search':result=source_access.search(repo,m[1],m[2],q.get('q',''),q.get('document'))
                else:result=source_access.manifest(repo,m[1],m[2])
                return self.send(200,encode(result))
            m=re.fullmatch(r'/api/editorial-instructions/([\w-]+)',p)
            if m:return self.send(200,encode(editorial_tasks.instructions(m[1])))
            m=re.fullmatch(r'/api/companies/([\w-]+)/(books|book-tasks)(?:/([\w-]+))?(?:/(instructions))?',p)
            if m:
                if m[2]=='books':
                    if m[3]:result=model_books.read_edition(self.server.store,m[1],m[3])
                    else:
                        with self.server.store.connect() as conn:result=model_books.editions(conn,m[1])
                else:result=model_books.instructions(self.server.store,m[1],m[3]) if m[4] else model_books.task(self.server.store,m[1],m[3]) if m[3] else model_books.tasks(self.server.store,m[1])
                return self.send(200,encode(result))
            m=re.fullmatch(r'/api/companies/([\w-]+)/data(?:/packages/([\w-]+)/(download|manifest))?',p)
            if m:
                self.server.store.company(m[1])
                repo=self.server.store.source_data
                if not m[2]:return self.send(200,encode(repo.overview(m[1])))
                package=repo.package(m[1],m[2])
                if m[3]=='manifest':return self.send(200,(Path(package['path'])/'manifest.json').read_bytes())
                if not package.get('zip_path'):raise ValueError('该资料版本在线读取，不含离线归档')
                return self.send(200,Path(package['zip_path']).read_bytes(),'application/zip',{'Content-Disposition':'attachment; filename="'+package['id']+'.zip"'})
            m=re.fullmatch(r'/api/companies/([\w-]+)',p)
            if m:return self.send(200,encode(self.server.store.company(m[1])))
            m=re.fullmatch(r'/api/companies/([\w-]+)/topics/([\w-]+)',p)
            if m:
                revision=parse_qs(u.query).get('revision',[None])[0]
                return self.send(200,encode(topics.read(self.server.store,m[1],m[2],int(revision) if revision else None)))
            m=re.fullmatch(r'/api/companies/([\w-]+)/research(?:/([\w-]+))?(?:/calculations/([\w-]+))?',p)
            if m:
                if m[3]: result=research_workspace.calculation(self.server.store,m[1],m[2],m[3])
                elif m[2]:
                    revision=parse_qs(u.query).get('revision',[None])[0]
                    result=research_workspace.read(self.server.store,m[1],m[2],int(revision) if revision else None)
                else: result=research_workspace.listing(self.server.store,m[1])
                return self.send(200,encode(result))
            m=re.fullmatch(r'/api/companies/([\w-]+)/framework',p)
            if m:
                revision=parse_qs(u.query).get('revision',[None])[0]
                return self.send(200,encode(frameworks.read(self.server.store,m[1],int(revision) if revision else None)))
            m=re.fullmatch(r'/api/workspace/(sources|tasks|reviews|activity)',p)
            if m:return self.send(200,encode(catalog.items(self.server.store,m[1],{k:v[0] for k,v in parse_qs(u.query).items()})))
            m=re.fullmatch(r'/api/companies/([\w-]+)/export',p)
            if m:
                company=self.server.store.company(m[1])
                with self.server.store.connect() as conn:
                    company['topic_versions']=topics.export(conn,m[1])
                    company['framework_versions']=frameworks.versions(conn,m[1])
                    company.update(research_workspace.export(conn,m[1]))
                return self.send(200,encode(dict(exported_at=now(),research_only=True,company=company)),headers={'Content-Disposition':f'attachment; filename="enterprise-{m[1]}.json"'})
            m=re.fullmatch(r'/api/sources/([\w-]+)/(content|file)',p)
            if m:
                s=self.server.store.source(m[1])
                if m[2]=='content':
                    txt=''
                    if s['path'] and Path(s['path']).is_file() and Path(s['path']).suffix.lower() in ('.md','.txt','.json','.csv'):
                        txt=Path(s['path']).read_text(errors='replace')
                    return self.send(200,encode(dict(source=s,text=txt)))
                if not s['path'] or not Path(s['path']).is_file(): return self.send(404,encode({'error':'本地文件不可用；可查看来源链接或重新上传。'}))
                path=Path(s['path']); ctype=mimetypes.guess_type(str(path))[0] or 'application/octet-stream'
                disp='attachment' if 'download' in parse_qs(u.query) or path.suffix.lower() not in ('.pdf','.png','.jpg','.jpeg','.webp') else 'inline'
                return self.send(200,path.read_bytes(),ctype,{'Content-Disposition':disp+"; filename*=UTF-8''"+quote(s.get('original_filename') or path.name)})
            if p in ('/','/index.html','/app.js','/workspace.js','/dossier.js','/dossier.css','/style.css','/business.js','/business.css','/china-map.js','/book.js','/book.css','/topics.js','/topics.css','/framework.js','/layered-research.js','/research.js','/three-step.js','/source-data.js','/model-books.js','/model-books.css','/research.css','/market-context.js','/market-observation.js','/market-atlas.js','/market-driver-chart.js','/market-atlas.css','/market-context.css','/industry-monitor.js','/industry-monitor.css'):
                f=BASE/'static'/('index.html' if p=='/' else p[1:]); return self.send(200,f.read_bytes(),mimetypes.guess_type(str(f))[0]+'; charset=utf-8')
            self.send(404,encode({'error':'页面不存在'}))
        except ValueError as e: self.send(404,encode({'error':str(e)}))
        except Exception as e:
            self.log_message('ERROR %r',e); self.send(500,encode({'error':'读取失败，请检查服务日志'}))
    def do_POST(self):
        try:
            n=int(self.headers.get('Content-Length','0'))
            if n>50*1024*1024: return self.send(413,encode({'error':'单次上传不超过50MB'}))
            raw=self.rfile.read(n); p=urlparse(self.path).path
            if self.headers.get('Content-Type','').startswith('multipart/form-data'):
                msg=BytesParser(policy=default).parsebytes(('Content-Type: '+self.headers['Content-Type']+'\r\nMIME-Version: 1.0\r\n\r\n').encode()+raw)
                data={}; content=None; filename=None
                for part in msg.iter_parts():
                    name=part.get_param('name',header='content-disposition'); fn=part.get_filename()
                    if fn: content=part.get_payload(decode=True); filename=fn
                    elif name: data[name]=part.get_payload(decode=True).decode('utf-8')
            else: data=json.loads(raw or b'{}'); content=None; filename=None
            if p=='/api/industries/property/monitor/refresh':
                return self.send(202,encode(self.server.industry_monitor.refresh()))
            m=re.fullmatch(r'/api/monitor-jobs/([\w-]+)/retry',p)
            if m:return self.send(202,encode(self.server.industry_monitor.refresh(retry=m[1])))
            m=re.fullmatch(r'/api/companies/([\w-]+)/market-attribution',p)
            if m:
                company=self.server.store.company(m[1])
                result=market_wave.publish(self.server.store.directory,company_market_observation.stock_code(company),
                                           data,market_observation.observation_cutoff(None))
                return self.send(201,encode(result))
            m=re.fullmatch(r'/api/companies/([\w-]+)/market-context/refresh',p)
            if m:
                company=self.server.store.company(m[1])
                if data.get('observation') == 1 and market_observation.observation_key(company):
                    self.server.observation_updater.start()
                    return self.send(202,encode(self.server.observation_updater.status()))
                if data.get('observation') == 1:
                    code=company_market_observation.stock_code(company)
                    cutoff=market_observation.observation_cutoff(data.get('as_of'))
                    selected=company_market_observation.selected_edition(self.server.store,company,data.get('edition'))
                    limit=company_market_observation.historical_limit(selected)
                    if limit:
                        cutoff=min(cutoff,limit)
                    _, refresh=company_market_observation.series_for(self.server.store.directory,code,cutoff,force=True)
                    return self.send(200,encode(refresh))
                if self.server.industry_monitor.overview(company):
                    job=self.server.industry_monitor.refresh()
                    return self.send(202,encode(dict(self.server.industry_monitor.overview(company),refresh_job_id=job['id'],refreshing=True)))
                extra={'as_of':data['as_of']} if isinstance(data,dict) and data.get('as_of') else {}
                return self.send(202,encode(self.server.market_context.response(company,force=True,**extra)))
            if p=='/api/editorial-instructions/prepare':return self.send(200,encode({'body':editorial_tasks.prepare(data)}))
            if p=='/api/organize':return self.send(200,encode({'updated':self.server.store.organize(data.get('ids'),data.get('changes',{}))}))
            if p=='/api/collections':return self.send(201,encode({'id':self.server.store.create_collection(data.get('name',''))}))
            if p=='/api/views':return self.send(201,encode({'id':self.server.store.save_view(data.get('name',''),data.get('filters',{}))}))
            m=re.fullmatch(r'/api/views/([\w-]+)/remove',p)
            if m:self.server.store.delete_view(m[1]);return self.send(200,encode({'ok':True}))
            m=re.fullmatch(r'/api/companies/([\w-]+)/book-tasks(?:/([\w-]+)/(status|complete|parts)(?:/([\w-]+))?)?',p)
            if m:
                if not m[2]:result=model_books.create_task(self.server.store,m[1],data)
                elif m[3]=='parts':result=model_books.save_part(self.server.store,m[1],m[2],m[4],data)
                elif m[3]=='complete':result=model_books.complete(self.server.store,m[1],m[2],data)
                else:result=model_books.set_status(self.server.store,m[1],m[2],data)
                return self.send(201,encode(result))
            m=re.fullmatch(r'/api/companies/([\w-]+)/data/(acquire|packages|versions)',p)
            if m:
                self.server.store.company(m[1])
                repo=self.server.store.source_data
                if m[2]=='acquire':
                    # Local-file imports belong to the CLI; web collection uses the declared URL.
                    spec={k:v for k,v in data.items() if k in ['id','title','url','issuer','fact_period','published_on','nature','description','group']}
                    spec.setdefault('id',uid())
                    result=collect_document(repo,m[1],spec)
                    return self.send(201 if result['document'] else 400,encode(result if result['document'] else dict(result,error=result['acquisition']['error'])))
                return self.send(201,encode(build_package(repo,m[1],data,create_archive=m[2]=='packages')))
            m=re.fullmatch(r'/api/companies/([\w-]+)/research(?:/([\w-]+))?(?:/(preview|calculations|handoffs))?',p)
            if m:
                if m[3] and not m[2]: raise ValueError('请选择研究')
                if m[3]=='handoffs': result=research_workspace.handoff(self.server.store,m[1],m[2],data)
                elif m[3] in ('preview','calculations'): result=research_workspace.compute(self.server.store,m[1],m[2],data,m[3]=='calculations')
                else:
                    if m[2]: research_workspace.read(self.server.store,m[1],m[2])
                    result=research_workspace.save(self.server.store,m[1],data,m[2])
                return self.send(200 if m[3]=='preview' else 201,encode(result))
            m=re.fullmatch(r'/api/companies/([\w-]+)/framework',p)
            if m:return self.send(201,encode(frameworks.save(self.server.store,m[1],data)))
            m=re.fullmatch(r'/api/companies/([\w-]+)/topics(?:/([\w-]+))?',p)
            if m:
                if m[2]: topics.read(self.server.store,m[1],m[2])
                return self.send(201,encode(topics.save(self.server.store,m[1],data,m[2])))
            m=re.fullmatch(r'/api/companies/([\w-]+)/(sources|records)',p)
            if m:
                rid=self.server.store.add_source(m[1],data,content,filename) if m[2]=='sources' else self.server.store.add_record(m[1],data.pop('kind',''),data)
                return self.send(201,encode({'id':rid}))
            source_match=re.fullmatch(r'/api/sources/([\w-]+)',p)
            if source_match:
                self.server.store.update_source(source_match[1],data);return self.send(200,encode({'ok':True}))
            m=re.fullmatch(r'/api/tasks/([\w-]+)',p)
            if m:
                self.server.store.task_status(m[1],data.get('status')); return self.send(200,encode({'ok':True}))
            if p=='/api/companies': return self.send(201,encode({'id':self.server.store.add_company(data)}))
            self.send(404,encode({'error':'操作不存在'}))
        except (ValueError,KeyError) as e: self.send(400,encode({'error':str(e)}))
        except Exception as e:
            self.log_message('ERROR %r',e); self.send(500,encode({'error':'保存失败，请检查服务日志'}))

def serve(port=8778, directory=BASE/'data', schedule_monitor=False):
    store=Store(directory)
    server=ThreadingHTTPServer(('127.0.0.1',port),Handler); server.store=store
    server.market_context=MarketService(store.directory)
    server.industry_monitor=MonitorService(store.directory, start_scheduler=schedule_monitor)
    server.observation_updater=ObservationUpdater(store.directory,schedule=True)
    print(f'企业书 http://127.0.0.1:{server.server_port}  data={store.directory}',flush=True)
    try: server.serve_forever()
    except KeyboardInterrupt: pass
    finally:
        server.market_context.close()
        server.industry_monitor.close()
        server.observation_updater.close()
        server.server_close()

if __name__=='__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('--port',type=int,default=8778)
    parser.add_argument('--data-dir',type=Path,default=BASE/'data')
    parser.add_argument('--schedule-monitor',action='store_true',help='启用行业监测的定时联网采集')
    args=parser.parse_args()
    serve(args.port,args.data_dir,args.schedule_monitor)
