"""External-agent tasks and immutable whole-book editions within a company."""
import json,re
from pathlib import Path
from source_data.repository import identifier,uid,now,encode
from source_data import access
import topics,frameworks,research_workspace,editorial_tasks

SCHEMA='''
CREATE TABLE IF NOT EXISTS book_tasks(id TEXT PRIMARY KEY,company_id TEXT NOT NULL,data TEXT NOT NULL,created_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS book_editions(id TEXT PRIMARY KEY,company_id TEXT NOT NULL,data TEXT NOT NULL,created_at TEXT NOT NULL);
'''
REQUIRED={'overview':'公司全貌',**{f'chapter-{i}':t for i,t in enumerate(['沿革与业务边界','商业模式与价值链','行业与竞争','历史经营与当前阶段','财务质量与现金归属','资本配置','投资判断与估值','跟踪与反证'],1)},'life':'生命周期与变化路径','history':'长期财务与口径','track':'后续核验安排','judgment':'综合判断','valuation':'正常现金与三步估值','assumptions':'假设及依据','calculations':'可复算计算','references':'事实与来源','gaps':'缺口与结论边界'}
CITATION=re.compile(r'\[\[doc:([\w-]+)@(\d+)\|([^\]\n]+)\]\]')

def unpack(row):
    if not row:raise ValueError('任务或企业书版本不存在')
    return dict(json.loads(row['data']),id=row['id'],company_id=row['company_id'],created_at=row['created_at'])

def editions(conn,cid):
    return [{k:v for k,v in unpack(r).items() if k not in {'snapshot','parts','research','calculations','topics'}} for r in conn.execute('SELECT * FROM book_editions WHERE company_id=? ORDER BY rowid DESC',(cid,))]

def read_edition(store,cid,eid):
    with store.connect() as c:return unpack(c.execute('SELECT * FROM book_editions WHERE company_id=? AND id=?',(cid,eid)).fetchone())

def tasks(store,cid):
    with store.connect() as c:
        return [{k:v for k,v in unpack(r).items() if k!='parts'}|{'saved_parts':list(json.loads(r['data']).get('parts',{}))} for r in c.execute('SELECT * FROM book_tasks WHERE company_id=? ORDER BY rowid DESC',(cid,))]

def task(store,cid,tid):
    with store.connect() as c:return unpack(c.execute('SELECT * FROM book_tasks WHERE company_id=? AND id=?',(cid,tid)).fetchone())

def create_task(store,cid,data):
    store.company(cid);version=data.get('source_version')
    m=access.manifest(store.source_data,cid,version)
    model={k:str(data.get('model',{}).get(k,'')).strip() for k in ['name','version']}
    if not model['name']:raise ValueError('请注明外部模型名称，精确版本未知可留空')
    d=dict(title=str(data.get('title') or model['name']+'企业书'),model=model,source_version=version,information_cutoff=m['information_cutoff'],valuation_date=m.get('valuation_date'),status='waiting',parts={},additional_sources=[],review_status='not_reviewed',updated_at=now())
    tid=uid()
    with store.connect() as c:c.execute('INSERT INTO book_tasks VALUES(?,?,?,?)',(tid,cid,encode(d),now()))
    return task(store,cid,tid)

def instructions(store,cid,tid):
    t=task(store,cid,tid);base=f'/api/companies/{cid}/book-tasks/{tid}';src=f'/api/companies/{cid}/data/versions/{t["source_version"]}'
    return dict(task=t,required_parts=REQUIRED,source_url=src,facts_url=src+'/facts',search_url=src+'/search?q=关键词',part_url=base+'/parts/{part_id}',complete_url=base+'/complete',status_url=base+'/status',
        workflow=editorial_tasks.instructions('coordinator'),
        role_instructions={role:f'/api/editorial-instructions/{role}' for role in editorial_tasks.ROLES if role!='coordinator'},
        prepare_url='/api/editorial-instructions/prepare',
        overview_display_contract='overview使用与全部企业一致的企业全景。POST overview 时在title、body之外提交display，含intro、subtitle、identity、metrics、series、overview。沿用共同的主体与范围、财务实绩及多年趋势、判断、八章入口、未解问题，参见 MODEL_BOOKS.md。',
        prepare_example={'role':'first_read','company':'本公司名称','question':'本篇的完整经营问题','scope':'实际稿件版本及完整阅读范围','output':'本批首读意见保存位置','end_condition':'复述理解与信息增量；单列图示取舍与遗漏，按实际页面判断现有图及未画出的重要关系；说明未覆盖范围','inputs':{'manuscript':['实际正文入口及版本'],'figures':['实际图像入口'],'preceding_text':[]}},
        execution='先完整读取workflow，再在每个具体任务开始时读取对应role_instructions全文，按prepare_example填写实际范围和输入并POST到prepare_url生成指令，保存返回的body到本批记录。按一个完整问题、一种主要产出接续；不要仅凭下面的接口摘要执行。独立正文首读只交实际正文、图片与可见前文，不把本接口的整项task、作者message、底稿或旧意见转交首读者。审阅必须留下对实际版本的具体理解、图文判断和未覆盖范围，不能用一句通过代替。无独立审阅条件就保留未审状态。完成接口只保存模型成稿，不评定内容质量。标准内历史示例不属于本公司的事实输入。',
        instructions='接口约定：目录、分页、检索和任务恢复使用GET；part_url、status_url和complete_url使用POST，Content-Type为application/json。先向status_url提交running及message；按part_url替换part_id逐部分保存。完成时向complete_url提交实际model身份与additional_sources。你是本任务的独立研究与主笔。只从本任务固定资料版本开始，不先读其他模型企业书。先读资料目录及缺口，再按完整问题分批研究和写作。目录给出全文分页接口、原PDF和披露数据；披露值不是正常化假设。每次可保存一个完整章节/专题并从GET任务恢复，不必一次生成整书。life单独保存企业经历的阶段、当前顺逆风及改善和恶化路径；history保存长期年度与同季财务及口径；track保存观察基点、下一披露、反证和判断影响，未发生的结果不能写成经营复盘。三个页面与八章一同属于本模型整书，不读取当前协作稿来补空缺。公司介绍与投资判断分别展开；资产再生产、EPV和增长分别研究，不能相加或平均，不强凑增长估值。假设、资本成本、维护和权益归属自行论证，缺失不补零。引用格式为 [[doc:ar2025@88|利润表]]，PDF页序从1开始；自行补充资料在完成请求additional_sources列明。可保存topic-自定义ID专题。每个部分为{title,body}，body为完整Markdown；支持本系统[[figure:来源ID|图注]]，图片用既有资料上传接口保存。先形成完整研究、统一写作，再独立审阅；提交完成只标为模型成稿，系统不会自动称已审定。不要复制旧判断、缩写成摘要或用默认数字填缺口。',
        example_part={'title':'章节标题','body':'完整Markdown正文，关键事实 [[doc:ar2025@88|原表]]。'},
        complete_example={'model':{'name':t['model']['name'],'version':t['model']['version']},'additional_sources':[]})

def save_part(store,cid,tid,slot,data):
    if slot not in REQUIRED and not re.fullmatch(r'topic-[\w-]+',slot):raise ValueError('未知正文位置')
    title=str(data.get('title','')).strip();body=str(data.get('body','')).strip()
    if not title or not body:raise ValueError('正文部分须有标题和完整内容')
    with store.connect() as c:
        c.execute('BEGIN IMMEDIATE');t=unpack(c.execute('SELECT * FROM book_tasks WHERE company_id=? AND id=?',(cid,tid)).fetchone())
        if t['status']=='completed':raise ValueError('已完成版本不可覆盖，请新建研究任务')
        docs={d['id']:d for d in access.manifest(store.source_data,cid,t['source_version'])['documents']}
        for did,page,label in CITATION.findall(body):
            if did not in docs or not 1<=int(page)<=docs[did]['page_count']:raise ValueError('引用不在所选资料版本或页码无效：'+did+'@'+page)
        part=dict(title=title,body=body,updated_at=now())
        if slot=='overview' and 'display' in data:
            part['display']=overview_display(data['display'],docs)
        t['parts'][slot]=part;t.update(status='running',updated_at=now())
        _save_task(c,t)
    return dict(id=tid,status=t['status'],saved_parts=list(t['parts']),missing_parts=[k for k in REQUIRED if k not in t['parts']])

def overview_display(display,docs):
    if not isinstance(display,dict) or not all(display.get(k) for k in ('intro','identity','metrics','series','overview')):
        raise ValueError('企业全景须提供介绍、主体经营信息、指标定义、年度序列和图表选项')
    def check_ref(x):
        doc=docs.get(x.get('document'))
        if not doc or not isinstance(x.get('page'),int) or not 1<=x['page']<=doc['page_count']:
            raise ValueError('企业全景所引用的财务或主体依据须属于本版资料及有效原件页')
    for r in display['overview'].get('identity_refs',[]):
        check_ref(r)
    for row in display['series']:
        for key,value in row['values'].items():
            if key not in display['metrics'] or not isinstance(value.get('value'),(float,int)):
                raise ValueError('企业全景数据须有对应的指标定义和披露数值')
            check_ref(value)
    return display

def _save_task(conn,t):
    conn.execute('UPDATE book_tasks SET data=? WHERE id=?',(encode({k:v for k,v in t.items() if k not in {'id','company_id','created_at'}}),t['id']))

def set_status(store,cid,tid,data):
    if data.get('status') not in {'running','failed','waiting'}:raise ValueError('状态须为running、failed或waiting')
    with store.connect() as c:
        c.execute('BEGIN IMMEDIATE');t=unpack(c.execute('SELECT * FROM book_tasks WHERE company_id=? AND id=?',(cid,tid)).fetchone())
        if t['status']=='completed':raise ValueError('完成任务不能改回进行中')
        t.update(status=data['status'],message=str(data.get('message','')),updated_at=now());_save_task(c,t)
    return t

def complete(store,cid,tid,data):
    with store.connect() as c:
        c.execute('BEGIN IMMEDIATE');t=unpack(c.execute('SELECT * FROM book_tasks WHERE company_id=? AND id=?',(cid,tid)).fetchone())
        if t['status']=='completed':return unpack(c.execute('SELECT * FROM book_editions WHERE id=?',(t['edition_id'],)).fetchone())
        missing=[k for k in REQUIRED if k not in t['parts']]
        if missing:raise ValueError('整书尚缺：'+'、'.join(REQUIRED[k] for k in missing))
        actual=data.get('model',t['model'])
        if actual.get('name')!=t['model']['name']:raise ValueError('实际模型与任务不符，请新建对应模型任务')
        if t['model']['version'] and actual.get('version') and actual['version']!=t['model']['version']:raise ValueError('实际模型版本与任务不符，请新建对应版本任务')
        model=dict(name=t['model']['name'],version=str(actual.get('version') or t['model']['version']))
        extra=data.get('additional_sources',[])
        if not isinstance(extra,list) or any(not isinstance(s,dict) or not s.get('title') or not (s.get('url') or s.get('source_id')) for s in extra):raise ValueError('补充来源逐项声明title及url或source_id')
        eid=uid();d=dict(title=t['title'],model=model,format='agent_book_v1',source_version=t['source_version'],information_cutoff=t['information_cutoff'],valuation_date=t['valuation_date'],parts=t['parts'],additional_sources=extra,review_status='not_reviewed',status='complete',task_id=tid,provenance='外部Agent提交；模型身份为执行方声明',completed_at=now())
        c.execute('INSERT INTO book_editions VALUES(?,?,?,?)',(eid,cid,encode(d),now()))
        t.update(status='completed',edition_id=eid,model=model,additional_sources=extra,updated_at=now());_save_task(c,t)
    return read_edition(store,cid,eid)

def capture_legacy(store,cid,eid,label='Codex协作版'):
    identifier(eid)
    with store.connect() as conn:
        existing=conn.execute('SELECT * FROM book_editions WHERE id=?',(eid,)).fetchone()
        if existing:
            if existing['company_id']!=cid:raise ValueError('版本编号已属于另一企业')
            return unpack(existing)
    company=store.company(cid);dossier=company.get('dossier')
    if not dossier:raise ValueError('本企业尚无可登记的现有正文')
    company.pop('book_editions',None)
    basis=dossier.get('research_basis',{});selected=basis.get('topic_versions',[])
    if not selected:selected=[dict(id=t['id'],revision=t['revision']) for t in company.get('topics',[])]
    bodies=[topics.read(store,cid,t['id'],t['revision']) for t in selected]
    project=research_workspace.read(store,cid,basis['project_id'],basis['research_revision']) if basis.get('project_id') else None
    calc_ids=research_workspace.calculation_ids(basis)
    calculations=[research_workspace.calculation(store,cid,basis['project_id'],rid) for rid in calc_ids] if project else []
    # Freeze the framework actually associated with this company edition where available.
    if basis.get('framework_revision'):company['research_framework']=frameworks.read(store,cid,basis['framework_revision'])
    data=dict(title=label+' · '+dossier.get('version','现有稿'),model=dict(name='Codex',version=''),format='legacy_snapshot',snapshot=company,topics=bodies,research=project,calculations=calculations,source_version=None,information_cutoff=None,book_date=dossier.get('as_of'),status='complete',review_status='historical_review',provenance='现有协作稿快照；历史主笔精确模型版本未统一登记，含独立审阅与多批次修订；不声称仅用后建资料版本重生成',completed_at=now())
    with store.connect() as c:c.execute('INSERT INTO book_editions VALUES(?,?,?,?)',(eid,cid,encode(data),now()))
    return read_edition(store,cid,eid)
