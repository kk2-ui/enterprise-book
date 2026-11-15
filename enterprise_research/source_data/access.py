"""Online reading of frozen source editions, independent of company judgments."""
import json
from pathlib import Path

def manifest(repo,cid,vid):
    root=Path(repo.package(cid,vid)['path'])
    data=json.loads((root/'manifest.json').read_text())
    base=f'/api/companies/{cid}/data/versions/{vid}'
    for d in data['documents']:
        d['read_url']=base+'/documents/'+d['id']
        d['original_url']=d['read_url']+'/original'
    data['facts_url']=base+'/facts';data['search_url']=base+'/search'
    return data

def document(repo,cid,vid,did,start=1,end=None):
    m=manifest(repo,cid,vid);d=next((d for d in m['documents'] if d['id']==did),None)
    if not d:raise ValueError('该资料不属于所选版本')
    start=int(start);end=int(end or start)
    if start<1 or end<start or end-start>=50 or end>d['page_count']:raise ValueError('请选择有效页序，每次最多50页')
    root=Path(repo.package(cid,vid)['path']);pages=(root/d['text']).read_text().split('\f')
    return dict(document=d,pages=[dict(page=i+1,text=pages[i]) for i in range(start-1,end)],next_page=end+1 if end<d['page_count'] else None)

def original(repo,cid,vid,did):
    m=manifest(repo,cid,vid);d=next((d for d in m['documents'] if d['id']==did),None)
    if not d:raise ValueError('该资料不属于所选版本')
    return Path(repo.package(cid,vid)['path'])/d['original']

def facts(repo,cid,vid,did=None):
    root=Path(repo.package(cid,vid)['path'])
    values=json.loads((root/'data/disclosed.json').read_text())
    return dict(disclosed=[v for v in values if not did or v['document_id']==did],derived=json.loads((root/'data/derived.json').read_text()),dictionary=json.loads((root/'data/dictionary.json').read_text()))

def search(repo,cid,vid,query,did=None):
    q=str(query).strip()
    if not q:raise ValueError('请填写检索词')
    m=manifest(repo,cid,vid);root=Path(repo.package(cid,vid)['path']);results=[]
    for d in m['documents']:
        if did and d['id']!=did:continue
        for i,p in enumerate((root/d['text']).read_text().split('\f')):
            pos=p.casefold().find(q.casefold())
            if pos>=0:
                results.append(dict(document_id=d['id'],title=d['title'],page=i+1,excerpt=p[max(0,pos-160):pos+600],read_url=d['read_url']+f'?start_page={i+1}'))
                if len(results)==30:return dict(results=results,limited=True)
    return dict(results=results,limited=False)
