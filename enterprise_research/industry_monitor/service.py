"""Bounded local jobs; readers only see immutable published snapshots."""
import json
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime,timezone
from pathlib import Path
from threading import Event,Lock,Thread

from market_data import completed_date,read_json,write_json,HONG_KONG,QuoteCache
from .repository import Repository
from .ingestion import register_universe,subject_id
from .acquisition import acquire_financials,raw_prices
from .disclosures import discover,download
from .pipeline import ingest
from .snapshot import build,financial_signature
from . import fx,events
from .returns import dividends
from .indices import total_return,TR_CODES,acquire_factsheet
from .market import from_inputs


def research_covers_change(repo,row,signature,new_events,today):
    """Only a newly adopted research basis can clear a changed-input hold."""
    adopted=[r for r in repo.observations(row['subject_id'],'research_basis') if r['as_of']<=today]
    if not adopted:return False
    latest=adopted[-1];previous=((row.get('research') or {}).get('adoption') or {}).get('id')
    return (latest['id']!=previous and latest.get('financial_signature')==signature
            and {e['document_id'] for e in new_events}<=set(latest.get('event_ids',[])))


def catchup_records(index,kind,previous_cutoff=None):
    records=sorted([r for r in index['records'] if r['kind']==kind],
                   key=lambda r:r.get('published_at',r['published_on']),reverse=True)
    return [r for i,r in enumerate(records) if i==0 or not previous_cutoff
            or r['published_on']>=previous_cutoff]


class MonitorService:
    def __init__(self,directory,start_scheduler=True):
        self.repo=Repository(directory);self.universe=register_universe(self.repo)
        self.lock=Lock();self.stopped=Event();self.future=None;self.job_id=None
        self.executor=ThreadPoolExecutor(max_workers=1,thread_name_prefix='industry-monitor')
        with self.repo.connect() as c:
            interrupted=[r['id'] for r in c.execute("SELECT id FROM monitor_jobs WHERE status IN ('queued','running')")]
        for jid in interrupted:self.repo.update_job(jid,'interrupted',reason='上次服务中断；已发布快照保留，可重试未完成输入')
        if start_scheduler:
            self.scheduler=Thread(target=self._schedule,name='industry-monitor-daily',daemon=True);self.scheduler.start()

    def _schedule(self):
        while not self.stopped.is_set():
            day=datetime.now(HONG_KONG).date().isoformat();cutoff=completed_date()
            with self.repo.connect() as c:
                attempted=any(json.loads(r['data']).get('schedule_key')==[day,cutoff]
                              for r in c.execute('SELECT data FROM monitor_jobs ORDER BY rowid DESC LIMIT 12'))
            if not attempted:self.refresh()
            self.stopped.wait(60)

    def refresh(self,retry=None):
        with self.lock:
            if self.future and not self.future.done():return self.repo.job(self.job_id)
            previous=self.repo.job(retry) if retry else None
            if previous and previous['scope']!='property':raise ValueError('重试任务范围不符')
            jid=self.repo.new_job('property',retry_of=retry,completed=0,failures=[],
                                  schedule_key=[datetime.now(HONG_KONG).date().isoformat(),completed_date()])
            self.job_id=jid
            self.future=self.executor.submit(self._run,jid,previous)
            return self.repo.job(jid)

    def _run(self,jid,previous):
        root=Path(previous['input_directory']) if previous and previous.get('input_directory') else self.repo.directory/'monitor_inputs'/jid
        cutoff=(previous or {}).get('price_date') or completed_date()
        today=(previous or {}).get('information_cutoff') or datetime.now(HONG_KONG).date().isoformat();failures=[]
        self.repo.update_job(jid,'running',input_directory=str(root),price_date=cutoff,information_cutoff=today,phase='financials')
        def progress(result):
            if result['status']=='failed':failures.append(result)
            job=self.repo.job(jid);self.repo.update_job(jid,'running',completed=job.get('completed',0)+1,failures=failures)
        try:
            current=self.repo.current('property')
            archive=Path(current['input_directory']) if current and current.get('input_directory') else None
            acquire_financials(self.universe['members'],root/'eastmoney',progress=progress)
            self.repo.update_job(jid,'running',phase='disclosures')
            discover(self.universe['members'],root/'hkex_index',today,progress=progress)
            for m in self.universe['members']:
                if self.stopped.is_set():raise InterruptedError('服务停止，保留已取得输入供重试')
                path=root/'prices'/(m['code']+'.json')
                if not path.exists():
                    try:write_json(path,raw_prices(m['code'],cutoff))
                    except Exception as e:failures.append(dict(code=m['code'],kind='prices',error=str(e)))
                divpath=root/'dividends'/(m['code']+'.json')
                if not divpath.exists():
                    try:write_json(divpath,dividends(m['code']))
                    except Exception as e:failures.append(dict(code=m['code'],kind='dividends',error=str(e)))
                index=read_json(root/'hkex_index'/(m['code']+'.json'))
                if index:
                    for kind in ('annual_report','interim_report','monthly_return'):
                        # Catch up every disclosure since the published input,
                        # even after a long shutdown; keep the latest annual and
                        # interim available for the current TTM bridge.
                        records=catchup_records(index,kind,(current or {}).get('information_cutoff'))
                        for record in records:
                            try:download(record,root/'reports',archive/'reports' if archive else None)
                            except Exception as e:failures.append(dict(code=m['code'],kind=kind,error=str(e)))
            (root/'fx').mkdir(parents=True,exist_ok=True)
            if not (root/'fx/ecb.csv').exists():(root/'fx/ecb.csv').write_text(fx.acquire())
            acquire_factsheet(root/'indices')
            for code in TR_CODES:
                p=root/'indices'/(code+'-total-return.json')
                if not p.exists():write_json(p,total_return(code))
            # Next-day disclosures update issued/treasury shares between monthly returns.
            for m in self.universe['members']:
                index=read_json(root/'hkex_index'/(m['code']+'.json')) or {}
                for record in index.get('records',[]):
                    if record['published_on']>=((current or {}).get('price_date','2019-01-01')[:7]+'-01') and '翌日' in record['title']:
                        try:download(record,root/'capital_events',archive/'capital_events' if archive else None)
                        except Exception as e:failures.append(dict(code=m['code'],kind='capital_event',error=str(e)))
            # Keep the separately labelled long price history; do not splice it
            # into the shorter total-return series used by the factor model.
            self.repo.update_job(jid,'running',phase='company_events')
            failures.extend(events.acquire(root,self.universe['members'],today))
            price_index,index_error=QuoteCache(root).fetch(dict(code='HSCI',name='恒生综合指数',secid='124.HSCI'),cutoff)
            if not price_index or price_index['rows'][-1]['date']!=cutoff:
                raise ValueError('长期价格指数未更新到对应交易日：'+str(index_error or '行情日期不足'))
            write_json(root/'indices/HSCI-price.json',price_index)
            self.repo.update_job(jid,'running',phase='ingestion',failures=failures)
            coverage=ingest(self.repo,root,self.universe['members'],cutoff,information_cutoff=today)
            active_codes={m['code'] for m in self.universe['members'] if m['status']!='delisted'}
            material_failures=[f for f in failures if f.get('code') in active_codes]
            if current and material_failures:
                self.repo.update_job(jid,'failed',failures=failures,coverage=coverage,reason='部分在市样本采集失败；继续显示上一已发布快照')
                return
            if current:
                # Compare with the published input, including on retries after
                # an earlier failed ingestion. The mutable database is not the
                # baseline for deciding whether old research still applies.
                before={r['code']:r.get('financial_signature') for r in current['companies']}
                after={m['code']:financial_signature(self.repo.facts(subject_id(m['code'])),today) for m in self.universe['members']}
                changed=[]
                for row in current['companies']:
                    fresh=events.newly_disclosed(row.get('company_events',[]),self.repo.observations(row['subject_id'],'company_event'),
                                                current['information_cutoff'],today)
                    different=before.get(row['code'])!=after[row['code']]
                    if (different or fresh) and not research_covers_change(self.repo,row,after[row['code']],fresh,today):
                        changed.append(dict(code=row['code'],reason='新财务输入或公司事件尚未由新的研究采用覆盖',financial_changed=different,events=fresh))
                if changed:
                    self.repo.update_job(jid,'needs_research',changed_disclosures=changed,coverage=coverage,failures=failures,
                                         reason='新财报或公司事件已取得；须完成研究采用后才替换完整判断。当前快照保留。')
                    return
            market,series=from_inputs(root,self.universe,cutoff)
            if any(series[code]['rows'][-1]['date']!=cutoff for code in ('06049.HK',*TR_CODES)):
                raise ValueError('个股与指数的完整交易日尚未对齐；保留上一快照，等待取得对应日数据')
            data=build(self.repo,self.universe,cutoff,today,market)
            data['input_job_id']=jid;data['input_directory']=str(root);data['acquisition_coverage']=coverage
            rid=self.repo.publish('property',cutoff,data,(current or {}).get('status','partial'))
            self.repo.update_job(jid,'completed',run_id=rid,coverage=coverage,failures=failures)
        except Exception as e:
            self.repo.update_job(jid,'interrupted' if isinstance(e,InterruptedError) else 'failed',failures=failures,reason=str(e))

    def sector(self,run_id=None):
        result=self.repo.current('property',run_id)
        if not result:return dict(status='pending',reason='首批数据与研究尚未发布',job=self.repo.job(self.job_id) if self.job_id else None)
        with self.repo.connect() as c:
            versions=[dict(r) for r in c.execute("SELECT id,as_of,status,created_at FROM monitor_runs WHERE scope='property' ORDER BY rowid DESC")]
            last=c.execute("SELECT id FROM monitor_jobs WHERE scope='property' ORDER BY rowid DESC LIMIT 1").fetchone()
        return dict(result,versions=versions,latest_job=self.repo.job(last['id']) if last else None)

    def subject(self,sid,run_id=None):
        result=self.sector(run_id)
        if result['status']=='pending':return result
        row=next((r for r in result['companies'] if r['subject_id']==sid),None)
        if not row:raise ValueError('该快照中没有此研究主体')
        ids=set(row.get('source_fact_ids',[]))
        for h in row.get('history',[]):ids.update(h.get('source_fact_ids',[]))
        return dict(row,run_id=result['run_id'],as_of=result['as_of'],snapshot_status=result['status'],
                    facts=row.get('evidence_facts',row.get('source_facts',[])))

    def overview(self,company,run_id=None):
        result=self.sector(run_id)
        if result['status']=='pending':return None
        row=next((r for r in result['companies'] if r['code']==company['code']),None)
        if not row:return None
        market=result['market'] if row['code']=='06049.HK' else dict(status='insufficient',reason='本批统计驱动仅为保利建模；同行估值可读，该公司驱动须独立计算',windows={})
        return dict(market,valuation_monitor=dict(company=row,groups=result['groups'],
                    peer_position=result['poly_peer_position'] if row['code']=='06049.HK' else {},
                    run_id=result['run_id'],as_of=result['as_of'],status=result['status'],
                    index_valuations=result.get('index_valuations',[]),versions=result.get('versions',[]),
                    latest_job=result.get('latest_job'),coverage=result['coverage'],boundary=result['boundary']),
                    refreshing=(result.get('latest_job') or {}).get('status') in ('queued','running'))

    def close(self):
        self.stopped.set();self.executor.shutdown(wait=False,cancel_futures=True)
