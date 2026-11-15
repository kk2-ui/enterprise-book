"""Acquisition and append-only ingestion shared by CLI and background jobs."""
import json
from pathlib import Path
from .ingestion import subject_id,import_eastmoney
from .capital import monthly_shares,nextday_shares
from .sources import register_report,register_structured
from . import fx
from .statements import extract
from .returns import cash_events
from . import events,reviewed_statements
from .disclosures import available_close_day


def ingest(repo,root,members,cutoff,register_originals=True,information_cutoff=None):
    root=Path(root);errors=[];originals=0;shares=0;documents={};statement_coverage=[];parsed_capital=set()
    if register_originals:
        for m in members:
            for path in (root/'eastmoney').glob(m['code']+'-*.json'):
                documents[path.name]=register_structured(repo.directory,subject_id(m['code']),path,'东方财富')
    summary=import_eastmoney(repo,root/'eastmoney',members,documents)
    for m in members:
        sid=subject_id(m['code'])
        price=root/'prices'/(m['code']+'.json')
        if price.exists():
            d=json.loads(price.read_text());repo.observe(sid,'raw_price_series',cutoff,'raw-prices:'+m['code'],d)
        dividend=root/'dividends'/(m['code']+'.json')
        if dividend.exists():
            d=json.loads(dividend.read_text());distributions,unresolved=cash_events(d)
            source=register_structured(repo.directory,sid,dividend,'现金分派原始数据') if register_originals else None
            repo.observe(sid,'cash_distributions',cutoff,'cash-distributions:'+m['code'],
                         dict(events=distributions,unresolved=unresolved,source_url=d['source_url'],
                              source_id=(source or {}).get('representations',{}).get('original'),retrieved_at=d['retrieved_at']))
    f=root/'fx/ecb.csv'
    if f.exists():
        repo.register('FX','reference','人民币港元参考汇率')
        repo.observe('FX','daily_rates',cutoff,'ecb-reference',dict(rows=fx.parse(f.read_text()),source_url=fx.URL))
    price_index=root/'indices/HSCI-price.json'
    if price_index.exists():
        index=json.loads(price_index.read_text())
        repo.observe('HSCI','trading_calendar',cutoff,'hsci-trading-calendar',
                     dict(dates=[r['date'] for r in index['rows'] if r['date']<=cutoff],source_url=index.get('source_url')))
    official=root/'indices/official-valuations.json'
    if official.exists():
        d=json.loads(official.read_text())
        from source_data import SourceRepository
        library=SourceRepository(repo.directory)
        for quote in d['values']:
            sid=quote['index'];did='hsi-factsheet-'+quote['as_of']+'-'+root.name
            try:doc=library.document(sid,did)
            except ValueError:
                metadata=dict(title='恒生官方指数概览 '+quote['as_of'],url=d['source_url'],kind='官方指数估值',fact_period=quote['as_of'],origin='恒生指数公司',notes=quote['limitation'])
                source=library.add_source(sid,metadata,Path(d['pdf_path']).read_bytes(),Path(d['pdf_path']).name)
                text_path=Path(d['text_path'])
                text=library.add_source(sid,metadata,text_path.read_bytes(),text_path.name)
                doc=library.save_document(sid,dict(id=did,title=metadata['title'],nature='industry_reference',representations=dict(original=source,text=text),rows=[],periods={},extraction_status='original_with_selected_rows'))
            quote['source_id']=doc['representations']['original'];quote['document_id']=did
            repo.observe(sid,'official_valuation',quote['as_of'],'hsi-factsheet',quote)
    for path in (root/'reports').glob('*.HK-*.json'):
        d=json.loads(path.read_text())
        if not Path(d['text_path']).exists():continue
        if d['kind']=='monthly_return':
            try:
                v=monthly_shares(Path(d['text_path']).read_text(),d)
                if register_originals:
                    doc=register_report(repo.directory,d);v['source_id']=doc['representations']['original']
                repo.observe(subject_id(d['code']),'shares',v['as_of'],'hkex-'+d['id'],v);shares+=1
                parsed_capital.add(d['id'])
            except ValueError as e:errors.append(dict(code=d['code'],document_id=d['id'],kind='share_parse',reason=str(e),available_on=available_close_day(d),source_url=d['url']))
        elif register_originals:
            doc=register_report(repo.directory,d);originals+=1
            result=extract(d)
            with repo.connect() as conn:
                current_keys={f['source_key'] for f in result['facts']}
                seen=set()
                for previous in conn.execute('SELECT id,revision,data FROM monitor_facts WHERE source_key LIKE ? ORDER BY revision DESC',('hkex-'+d['id']+':%',)).fetchall():
                    old=json.loads(previous['data']);key=old['source_key']
                    if key in seen:continue
                    seen.add(key)
                    if (':statement:' in key or ':derived-parent-equity:' in key or ':derived-capex:' in key) and key not in current_keys and old.get('quality')!='conflict':
                        repo.add_fact(dict(old,quality='conflict',withdrawal_reason='原件解析修正：本行不再作为该指标；旧快照保留'),conn)
                for fact in result['facts']:
                    fact['source'].update(document_revision=doc['revision'],source_id=doc['representations']['original'])
                    repo.add_fact(fact,conn)
            statement_coverage.append(dict(code=d['code'],document_id=doc['id'],period=result.get('period_end'),
                                           facts=len(result['facts']),issues=result['issues']))
    reviewed=reviewed_statements.ingest(repo,root)
    capital_events=0
    records=[]
    for path in (root/'capital_events').glob('*.HK-*.json'):
        d=json.loads(path.read_text());records.append(d)
    for d in sorted(records,key=lambda x:x['published_at']):
        sid=subject_id(d['code'])
        try:
            prior=[x for x in repo.observations(sid,'shares') if x['as_of']<=d['published_on'] and x.get('available_on','')<=d['published_on']]
            previous=max(prior,key=lambda x:(x['as_of'],x.get('available_on',''))) if prior else None
            v=nextday_shares(Path(d['text_path']).read_text(),d,previous)
            if register_originals:
                doc=register_report(repo.directory,d);v['source_id']=doc['representations']['original']
            repo.observe(sid,'shares',v['as_of'],'hkex-'+d['id'],v);capital_events+=1
            parsed_capital.add(d['id'])
        except ValueError as error:errors.append(dict(code=d['code'],document_id=d['id'],kind='capital_event_parse',reason=str(error),available_on=available_close_day(d),source_url=d['url']))
    for member in members:
        sid=subject_id(member['code'])
        previous=repo.observations(sid,'capital_coverage')
        gaps={e['document_id']:e for e in previous[-1]['unresolved'] if e['document_id'] not in parsed_capital} if previous else {}
        gaps.update({e['document_id']:e for e in errors if e['code']==member['code']})
        repo.observe(sid,'capital_coverage',cutoff,'capital-coverage',dict(unresolved=list(gaps.values())))
    company_events=events.ingest(repo,root,members,information_cutoff or cutoff)
    return dict(company_events=company_events,capital_events=capital_events,financials=summary,reports=originals,share_returns=shares,statement_coverage=statement_coverage,reviewed_statements=reviewed,errors=errors)
