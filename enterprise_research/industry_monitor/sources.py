"""Register acquisition artifacts with the existing source library."""
import json
from pathlib import Path
from source_data import SourceRepository
from .ingestion import subject_id


def register_report(directory, record):
    repo=SourceRepository(directory);sid=subject_id(record['code']);did='hkex-'+record['id']
    try:return repo.document(sid,did)
    except ValueError:pass
    meta=dict(title=record['title'],url=record['url'],published_on=record['published_on'],
              kind=record['kind'],origin='港交所公开披露',notes='公告原件；公开时点见港交所目录')
    reps={}
    for kind,key in [('original','pdf_path'),('text','text_path')]:
        path=Path(record[key]);reps[kind]=repo.add_source(sid,meta,path.read_bytes(),path.name)
    return repo.save_document(sid,dict(id=did,title=record['title'],nature='company_disclosure',
          issuer=record['code'],published_on=record['published_on'],published_at=record['published_at'],
          representations=reps,rows=[],periods={},extraction_status='full_text',
          acquisition=dict(provider='HKEX',url=record['url'],index_url=record['source_url'],
                           kind=record['kind'],amended=record['amended'])))


def register_structured(directory, sid, path, provider):
    repo=SourceRepository(directory);path=Path(path);payload=json.loads(path.read_text())
    # Acquisition files have a stable identity within an immutable input batch.
    did='input-'+path.parent.parent.name+'-'+path.parent.name+'-'+path.stem.replace('.','-')
    try:return repo.document(sid,did)
    except ValueError:pass
    url=(payload.get('urls') or [payload.get('source_url','')])[0]
    meta=dict(title=provider+' '+path.stem,url=url,kind='结构化原始响应',origin=provider,
              notes='当前供应商历史值，取得时间不代表首次公开时间')
    source=repo.add_source(sid,meta,path.read_bytes(),path.name)
    return repo.save_document(sid,dict(id=did,title=meta['title'],nature='industry_reference',
          representations=dict(original=source,text=source),rows=[],periods={},
          extraction_status='structured_response',retrieved_at=payload.get('retrieved_at'),
          acquisition=dict(provider=provider,url=url)))
