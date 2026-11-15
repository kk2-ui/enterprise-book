"""Workspace organization, independent from economic judgments and forecast records."""
import json
from datetime import date

RESEARCH_STATUSES=['待初筛','研究中','持续跟踪','暂缓','归档']

def org_defaults(company):
    return dict(research_status='持续跟踪' if company['id'] in ('00506','02314') else '待初筛',
                sector=(company.get('industry') or '未分类').split(' · ')[0],
                market='香港' if company.get('code','').endswith('.HK') else '未分类',
                tags=[],pinned=False)


def summaries(store):
    """No original JSON, chapters, source contents or record bodies in the catalog."""
    with store.connect() as conn:
        companies=conn.execute('SELECT id,data FROM companies ORDER BY id').fetchall()
        source_rows={r['company_id']:r for r in conn.execute('SELECT company_id,count(*) n,max(created_at) updated FROM sources GROUP BY company_id')}
        source_counts={cid:r['n'] for cid,r in source_rows.items()}
        framework_rows={r['company_id']:r['updated'] for r in conn.execute('SELECT company_id,max(created_at) updated FROM company_frameworks GROUP BY company_id')}
        topic_rows={r['company_id']:r for r in conn.execute('SELECT company_id,count(DISTINCT id) n,max(created_at) updated FROM research_topics GROUP BY company_id')}
        research_updates={r['company_id']:r['updated'] for r in conn.execute('''
            SELECT company_id,MAX(created_at) updated FROM (
            SELECT company_id,created_at FROM research_projects UNION ALL
            SELECT company_id,created_at FROM research_calculations UNION ALL
            SELECT company_id,created_at FROM research_handoffs) GROUP BY company_id''')}
        rows=conn.execute('SELECT company_id,kind,data,created_at FROM records ORDER BY rowid DESC').fetchall()
        groups=conn.execute('SELECT company_id,collection_id FROM collection_members').fetchall()
    by={}
    for row in rows: by.setdefault(row['company_id'],[]).append(row)
    memberships={}
    for row in groups: memberships.setdefault(row['company_id'],[]).append(row['collection_id'])
    result=[]
    for row in companies:
        c=json.loads(row['data']); recs=by.get(c['id'],[]); org={**org_defaults(c),**c.get('organization',{})}
        counts={}; pending=[]; latest_j=None; latest_v=None; updated=source_rows[c['id']]['updated'] if c['id'] in source_rows else ''
        topic=topic_rows.get(c['id'])
        if topic: updated=max(updated,topic['updated'])
        updated=max(updated,framework_rows.get(c['id'],''),research_updates.get(c['id'],''))
        for r in recs:
            counts[r['kind']]=counts.get(r['kind'],0)+1
            updated=max(updated,r['created_at'])
            # Only inspect data required by the catalog, not full forecast snapshots.
            if r['kind']=='task':
                data=json.loads(r['data'])
                if data.get('status')!='已完成': pending.append(data)
            elif r['kind']=='judgment' and latest_j is None:latest_j=json.loads(r['data'])
            elif r['kind']=='valuation' and latest_v is None:latest_v=json.loads(r['data'])
        def task_order(t):return (0 if t.get('due_date') else 1,t.get('due_date',''),t.get('title',''))
        next_task=min(pending,key=task_order) if pending else None
        item={k:c.get(k,'') for k in ('id','name','code','industry','currency','stage','color','summary','cash','cash_label','value','value_label')}
        item.update(organization=org,collections=memberships.get(c['id'],[]),source_count=source_counts.get(c['id'],0),topic_count=topic['n'] if topic else 0,
                    open_tasks=len(pending),overdue_tasks=sum(bool(t.get('due_date')) and t['due_date']<date.today().isoformat() for t in pending),
                    updated_at=max(updated,c.get('organization_updated_at',''),c.get('created_at','')),judgment_date=(latest_j or {}).get('effective_on',''),
                    research_updated_at=updated,has_judgment=bool(latest_j),has_valuation=bool(latest_v) or c.get('value','—')!='—',
                    next_task={k:next_task.get(k,'') for k in ('title','due_date','timing')} if next_task else None)
        if latest_j and latest_j.get('stage'):item['stage']=latest_j['stage']
        if latest_v:
            for key in ('cash','value','cash_label','value_label'):item[key]=latest_v[key]
        result.append(item)
    return result


def collection_list(store):
    with store.connect() as c:
        return [dict(r) for r in c.execute('SELECT c.id,c.name,count(m.company_id) member_count FROM collections c LEFT JOIN collection_members m ON m.collection_id=c.id GROUP BY c.id ORDER BY c.created_at,c.id')]


def overview(store):
    companies=summaries(store); active=[c for c in companies if c['organization']['research_status']!='归档']
    with store.connect() as c:
        views=[dict(id=r['id'],name=r['name'],filters=json.loads(r['filters'])) for r in c.execute('SELECT * FROM saved_views ORDER BY rowid')]
    return dict(companies=companies,collections=collection_list(store),saved_views=views,research_statuses=RESEARCH_STATUSES,
                stats=dict(total=len(companies),active=len(active),archived=len(companies)-len(active),
                           source_count=sum(c['source_count'] for c in companies),open_tasks=sum(c['open_tasks'] for c in active),
                           overdue=sum(c['overdue_tasks'] for c in active),unreviewed=sum(not c['has_judgment'] for c in active)))


def items(store,kind,params):
    """Bounded cross-company feeds. Filtering precedes pagination."""
    page=max(1,int(params.get('page',1)));size=min(50,max(1,int(params.get('size',20))))
    catalog={c['id']:c for c in summaries(store)}
    company_id=params.get('company','');query=params.get('q','').casefold();collection=params.get('collection','')
    ids={cid for cid,c in catalog.items() if (not company_id or cid==company_id)
         and (not collection or collection in c['collections'])
         and (params.get('archived')=='1' or c['organization']['research_status']!='归档')}
    table='sources' if kind=='sources' else 'records'
    with store.connect() as c:
        rows=list(c.execute(f'SELECT * FROM {table} ORDER BY rowid DESC').fetchall())
        if kind=='activity':
            for research_table,record_kind in [('research_projects','research'),('research_calculations','calculation'),('research_handoffs','handoff')]:
                for row in c.execute(f'SELECT * FROM {research_table} ORDER BY rowid DESC'):
                    r=dict(row);data=json.loads(r['data'])
                    summary=dict(title=data.get('title','写作交接'),body=data.get('change_note') or data.get('note',''),
                                 research_project_id=r.get('project_id',r['id']),research_revision=r.get('project_revision',r.get('revision')))
                    if record_kind=='calculation':summary['calculation_id']=r['id']
                    r.update(kind=record_kind,data=json.dumps(summary,ensure_ascii=False));rows.append(r)
            rows.sort(key=lambda r:r['created_at'],reverse=True)
    found=[]
    for r in rows:
        if r['company_id'] not in ids:continue
        if kind=='tasks' and r['kind']!='task':continue
        if kind=='reviews' and r['kind'] not in ('review','observation'):continue
        if kind=='activity' and r['kind'] not in ('judgment','valuation','review','observation','note','event','research','calculation','handoff'):continue
        data=json.loads(r['data']); co=catalog[r['company_id']]
        if query and query not in ' '.join(str(data.get(k,'')) for k in ('title','body','notes','chapter','kind')).casefold()+' '+(co['name']+' '+co['code']).casefold():continue
        if kind=='sources' and params.get('type') and data.get('kind')!=params['type']:continue
        status=data.get('status','待资料')
        if kind=='tasks':
            view=params.get('status','open')
            if view=='open' and status=='已完成':continue
            if view=='overdue' and (status=='已完成' or not data.get('due_date') or data['due_date']>=date.today().isoformat()):continue
            if view=='event' and (status=='已完成' or data.get('due_date')):continue
            if view not in ('open','all','overdue','event') and status!=view:continue
        result=dict(id=r['id'],company_id=r['company_id'],company_name=co['name'],company_code=co['code'],created_at=r['created_at'],**data)
        if table=='records':result['kind']=r['kind']
        # Metadata history belongs in the source inspector, not the library listing.
        result.pop('metadata_history',None)
        found.append(result)
    if kind=='tasks':found.sort(key=lambda r:(r.get('status')=='已完成',not bool(r.get('due_date')),r.get('due_date',''),r['company_name'],r['id']))
    page=min(page,max(1,(len(found)+size-1)//size))
    return dict(items=found[(page-1)*size:page*size],total=len(found),page=page,size=size)
