#!/usr/bin/env python3
"""Append a reviewed dossier, reuse source IDs; never overwrite forecasts or notes."""
import argparse,json,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from app import Store,encode,uid,now
import research_workspace

def import_dossier(store,path):
    data=json.loads(Path(path).read_text());cid=data['company_id'];version=data['version']
    store.company(cid)
    if data.get('research_basis'):
        research_workspace.validate_publication(store,cid,data['research_basis'])
    with store.connect() as c:
        if c.execute('SELECT 1 FROM dossiers WHERE company_id=? AND version=?',(cid,version)).fetchone():return 'already imported'
        existing=[(r['id'],json.loads(r['data'])) for r in c.execute('SELECT * FROM sources WHERE company_id=?',(cid,))]
        for ref,doc in data['documents'].items():
            for typ in ('pdf','text','url','image'):
                target=doc.get(typ)
                if not target:continue
                if typ!='url' and not Path(target).is_file():raise ValueError(f'missing source: {target}')
                if typ=='image' and Path(target).suffix.lower() not in ('.png','.jpg','.jpeg','.webp'):
                    raise ValueError('book figures must use PNG, JPEG or WebP')
                field='url' if typ=='url' else 'path'
                found=next((sid for sid,s in existing if s.get(field)==target),None)
                if not found:
                    found=uid();src=dict(title=doc['title']+(' · 正文' if typ=='text' else ''),kind=doc['type'],chapter='',
                        path=target if typ!='url' else '',url=target if typ=='url' else doc.get('url',''),
                        fact_period=doc['period'],published_on=doc.get('published_on',''),notes=doc.get('notes',''),origin='企业书来源补充')
                    c.execute('INSERT INTO sources VALUES(?,?,?,?)',(found,cid,encode(src),now()));existing.append((found,src))
                doc[typ+'_source_id']=found
        sections=[s for chapter in data['chapters'] for s in chapter.get('sections',[])]
        sections+=data.get('cash_analysis',{}).get('sections',[])
        for section in sections:
            for figure in section.get('figures',[]):
                if not data['documents'].get(figure['document'],{}).get('image_source_id'):
                    raise ValueError('figure requires an image document: '+figure['document'])
                position=figure.get('after_paragraph',len(section.get('paragraphs',[]))-1)
                if not isinstance(position,int) or not 0<=position<len(section.get('paragraphs',[])):
                    raise ValueError('figure position must refer to a paragraph in its section')
        c.execute('INSERT INTO dossiers VALUES(?,?,?,?)',(cid,version,encode(data),now()))
    return 'imported '+version

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--data-dir',required=True,type=Path);p.add_argument('dossier',type=Path);a=p.parse_args()
    print(import_dossier(Store(a.data_dir),a.dossier))
