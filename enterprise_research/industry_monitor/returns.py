"""Cash-dividend total return, with explicit exclusions for unresolved rights."""
import re
from urllib.parse import urlencode
from datetime import datetime,timezone
from .acquisition import fetch_json


def dividends(code):
    p=dict(reportName='RPT_HKF10_MAIN_DIVBASIC',columns='ALL',filter=f'(SECUCODE="{code}")',
           pageSize=500,pageNumber=1,source='F10',client='PC')
    url='https://datacenter.eastmoney.com/securities/api/data/v1/get?'+urlencode(p)
    data=fetch_json(url)
    if not data.get('success') or not data.get('result'):raise ValueError('分红历史未取得，不能假设从未分红')
    if data['result'].get('pages',1)>1:raise ValueError('分红历史分页未完整取得')
    return dict(code=code,source_url=url,retrieved_at=datetime.now(timezone.utc).isoformat(),rows=data['result']['data'])


def cash_events(payload):
    events=[];unresolved=[]
    for row in payload['rows']:
        plan=row.get('PLAN_EXPLAIN') or '';day=row.get('EX_DIVIDEND_DATE')
        if row.get('IS_BFP')=='1' or plan in ('未派发或宣派股息','不分配'):continue
        if not day:
            unresolved.append(dict(reason='已提及分配但除净日未取得',raw=row));continue
        day=day.replace('/','-')[:10]
        unit=re.search(r'每(\d*(?:\.\d+)?)股',plan)
        per=float(unit.group(1) or 1) if unit else None
        match=re.search(r'相当于港币([\d.]+)(?:元|\))',plan) or re.search(r'派(?:港币|港元)([\d.]+)元',plan)
        if not match or per is None or any(x in plan for x in ('送','配股','分拆','认股','认购','实物')):
            unresolved.append(dict(date=day,reason='现金币种、每股单位或非现金权益未核定',raw=row));continue
        events.append(dict(date=day,cash_hkd=float(match.group(1))/per,announced_on=row['NOTICE_DATE'][:10],
                           updated_on=row['UPDATE_DATE'][:10],description=plan,report_type=row['REPORT_TYPE'],
                           fiscal_year=row['YEAR'],source_url=payload['source_url']))
    # Provider sometimes contains successive revisions of a distribution.
    latest={}
    for r in events:
        key=(r['date'],r['report_type'],r['fiscal_year'])
        if key not in latest or r['updated_on']>latest[key]['updated_on']:latest[key]=r
    return sorted(latest.values(),key=lambda r:r['date']),unresolved


def total_return(prices,events,capital_events=(),unresolved=()):
    if unresolved:raise ValueError('存在未核定分红；不得标为完整总回报')
    if prices.get('adjustment')!='NONE':raise ValueError('含息计算从未复权价格开始')
    bars=prices['rows'];cash={};splits={}
    for event in events:cash[event['date']]=cash.get(event['date'],0)+event['cash_hkd']
    for event in capital_events:
        if event.get('kind')!='split' or not event.get('verified'):
            raise ValueError('有未核定的拆合股、供股或非现金权益')
        splits[event['date']]=event['new_shares_per_old']
    dates={r['date'] for r in bars}
    missing=[d for d in set(cash)|set(splits) if bars[0]['date']<d<=bars[-1]['date'] and d not in dates]
    if missing:raise ValueError('除权除息日缺少成交价格，暂停该证券含息序列')
    level=100;rows=[dict(bars[0],close=level)]
    for previous,bar in zip(bars,bars[1:]):
        factor=splits.get(bar['date'],1)
        # Dividend per new share. Explicit input convention avoids split/day ambiguity.
        level*=factor*(bar['close']+cash.get(bar['date'],0))/previous['close']
        rows.append(dict(bar,close=level))
    return dict(prices,rows=rows,adjustment='TOTAL_RETURN_GROSS',source='未复权收盘价＋每股港币税前现金分红，除净日再投资',
                capital_events=list(capital_events),dividends=list(events),price_source_url=prices['source_url'])
