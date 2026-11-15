"""One frozen input set drives the overview, sector table and offline report."""
from copy import deepcopy
from datetime import date,timedelta
from .calculation import VERSION,PROPERTY_PROFILE,valuation,aggregate,percentile,ttm,candidates,choose,latest
from .ingestion import subject_id
from . import fx,economic,events


def financial_signature(facts,day):
    result={}
    for metric in ('parent_profit','parent_equity','operating_cash_flow','capital_expenditure','cash','trade_receivables','goodwill'):
        rows=candidates(facts,metric,day)
        for period in sorted({f['period_end'] for f in rows}):
            same=[f for f in rows if f['period_end']==period]
            for kind,subset in [('selected',same),('vendor',[f for f in same if f['vintage']=='unknown'])]:
                f=choose(subset)
                if f:result[f'{kind}:{metric}:{period}']=[f.get(k) for k in ('period_start','value','currency','scope')]
    return result


def current_observation(rows, cutoff, information_cutoff):
    valid=[r for r in rows if r['as_of']<=cutoff and r.get('available_on',r['as_of'])<=information_cutoff]
    return max(valid,key=lambda r:(r['as_of'],r.get('available_on',''),r.get('id',''))) if valid else None


def load_inputs(repo, member):
    sid=subject_id(member['code']);series=repo.observations(sid,'raw_price_series')
    facts=repo.facts(sid);checks=repo.observations(sid,'financial_comparability')
    for f in facts:
        f['ttm_scope_checks']=[x for x in checks if x.get('current_document_id')==f.get('source',{}).get('document_id')]
    distributions=repo.observations(sid,'cash_distributions')
    capital_coverage=repo.observations(sid,'capital_coverage')
    return dict(facts=facts,series=series[-1] if series else None,
                shares=repo.observations(sid,'shares'),distributions=distributions[-1] if distributions else None,
                capital_gaps=capital_coverage[-1].get('unresolved',[]) if capital_coverage else [])


def reported(repo, member, cutoff, information_cutoff, fx_rows, historical=False, inputs=None):
    sid=subject_id(member['code']);inputs=inputs or load_inputs(repo,member);facts=inputs['facts'];issues=[]
    series=inputs['series']
    price_rows=[r for r in (series or {}).get('rows',[]) if r['date']<=cutoff]
    price=price_rows[-1] if price_rows else None
    visible_gaps=[g for g in inputs.get('capital_gaps',[]) if g['available_on']<=information_cutoff]
    invalid_documents={'hkex-'+g['document_id'] for g in visible_gaps}
    shares=current_observation([s for s in inputs['shares'] if s.get('document_id') not in invalid_documents],cutoff,information_cutoff)
    unresolved=[g for g in visible_gaps if not shares or g['available_on']>=shares.get('available_on',shares['as_of'])]
    if unresolved:
        shares=None
        issues.append('最后已核股本之后存在未识别的股份公告；暂停市值，直到后续完整股本原件明确结存：'+','.join(g['document_id'] for g in unresolved))
    rate=fx.at(fx_rows,cutoff,information_cutoff)
    # Suspension and exit remain visible; stale prices never become live market caps.
    active=price and price['date']==cutoff and member.get('joined','1900-01-01')<=cutoff
    if member.get('left') and cutoff>=member['left']:active=False
    if not price:issues.append('缺少未复权行情')
    elif not active:issues.append('无当日成交收盘价；停牌/退出的末次价格单列，不进入当前估值统计')
    if not shares:issues.append('缺少截至当时已公开、扣除库存股的总普通股股数')
    if not rate:issues.append('缺少对应日期的可得汇率')
    value={}
    if price and shares and rate and active:
        value=valuation(facts,dict(as_of=price['date'],close=price['close'],currency='HKD',adjustment='NONE',
                                  observation_id=series['id']),shares,cutoff,rate['rates'],historical,information_cutoff)
        value['fx_observation']=rate
    else:
        equity=latest(facts,'parent_equity',information_cutoff,historical)
        earnings=ttm(facts,'parent_profit',information_cutoff,historical)
        value=dict(market_cap=None,pe_ttm=dict(value=None,status='missing'),pb=dict(value=None,status='missing'),
                   cash_proxy_multiple=dict(value=None,status='missing'),earnings=None,equity=None,cash_proxy=None,
                   financial_period=(equity or {}).get('period_end'),shares_date=(shares or {}).get('as_of'),
                   basis=dict(earnings=earnings,equity_fact_id=(equity or {}).get('id'),
                              ocf=ttm(facts,'operating_cash_flow',information_cutoff,historical),
                              capex=ttm(facts,'capital_expenditure',information_cutoff,historical)))
    basis=value.get('basis',{});ids=set()
    for component in ('earnings','ocf','capex'):
        ids.update(basis.get(component,{}).get('fact_ids',[]))
    if basis.get('equity_fact_id'):ids.add(basis['equity_fact_id'])
    facts_used=[f for f in facts if f['id'] in ids]
    if any(f['vintage']=='unknown' for f in facts_used):issues.append('当前报表指标含供应商数据；历史时点计算排除此类未核原版数据')
    if value['pe_ttm']['value'] is None:issues.append('PE不可用：亏损或缺少同口径完整TTM，不能解释为极低估值')
    if value['pb']['value'] is None:issues.append('PB不可用：非正净资产或缺少归母权益')
    if value['cash_proxy_multiple']['value'] is None:issues.append('现金筛查比率不可用：非正现金或资本开支覆盖未完成')
    # Dividend yield is the trailing realised gross cash distribution per H
    # share, including special distributions; it is not sustainable owner cash.
    div=inputs.get('distributions') if not historical else None;dividend_yield=None;dividend_basis=[]
    if div and not div.get('unresolved') and active:
        start=(date.fromisoformat(cutoff)-timedelta(days=365)).isoformat()
        dividend_basis=[e for e in div['events'] if start<e['date']<=cutoff]
        dividend_yield=sum(e['cash_hkd'] for e in dividend_basis)/price['close']
    return dict(value,subject_id=sid,code=member['code'],name=member['name'],group=member['group'],
                listing_status=member['status'],active=bool(active),issues=issues,
                classification=member.get('classification',{}),classification_reason=member.get('reason'),
                membership=member.get('membership',{}),
                last_price=price,source_fact_ids=sorted(ids),source_facts=facts_used,facts_count=len(facts),
                dividend_yield=dividend_yield,dividend_basis=dividend_basis,
                dividend_source_id=(div or {}).get('source_id'))


def monthly_history(repo,member,cutoff,fx_rows,inputs=None):
    inputs=inputs or load_inputs(repo,member);series=inputs['series']
    if not series:return []
    last={}
    for row in series['rows']:
        if '2020-12-01'<=row['date']<=cutoff:last[row['date'][:7]]=row['date']
    # Month ends come from the market calendar, supplied by acquisition. Missing
    # security bars do not redefine a suspended stock's month end.
    calendar=repo.observations('HSCI','trading_calendar')
    if calendar:
        last={}
        for day in calendar[-1]['dates']:
            if '2020-12-01'<=day<=cutoff:last[day[:7]]=day
    rows=[]
    for month,day in sorted(last.items()):
        if month==cutoff[:7] and day==cutoff:continue  # unfinished calendar month
        r=reported(repo,member,day,day,fx_rows,historical=True,inputs=inputs)
        rows.append(dict(date=day,price=(r.get('last_price') or {}).get('close') if r['active'] else None,
                         pe=r['pe_ttm']['value'],pb=r['pb']['value'],
                         earnings=r.get('earnings'),equity=r.get('equity'),
                         market_cap=r.get('market_cap'),basis=r.get('basis'),fx_observation=r.get('fx_observation'),
                         source_fact_ids=r['source_fact_ids'],issues=r['issues']))
    return rows


def checked_market(market):
    """Pause cross-basis claims while preserving a readable old snapshot."""
    result=deepcopy(market or {})
    bases={s.get('adjustment') for s in result.get('sources',[])}
    matched=bool(bases) and bases<=set(('TOTAL_RETURN_GROSS',))
    result['return_basis']=dict(matched=matched,bases=sorted(x for x in bases if x),
        status='matched' if matched else 'unmatched',
        reason='' if matched else '个股前复权与恒生价格指数尚无已核对的一致含息序列；暂停跨口径主导与跑赢跑输结论。单项走势仍可阅读。')
    if matched:return result
    for window in result.get('windows',{}).values():
        window.update(status='insufficient',reason=result['return_basis']['reason'],dominant='unknown',dominant_label='无法识别')
    monitor=result.get('monitor')
    if monitor:
        monitor['research_priority']='价格处境可观察，跨口径压力归因暂停'
        monitor['research_reason']=result['return_basis']['reason']
        for window in monitor.get('windows',{}).values():
            window.update(status='insufficient',driver_label='无法识别（回报口径待匹配）',reason=result['return_basis']['reason'],
                          contributions_log_pp=None,r2=None)
            window.setdefault('relative_returns',{})['industry_market']=None
            window.setdefault('industry_laggards',{})['below_market']=None
    history=result.get('sector_history')
    if history:
        history['cross_basis_warning']=result['return_basis']['reason']
        for group in history.get('main',{}).get('groups',{}).values():group['below_market']=None
    return result


def build(repo,universe,cutoff,information_cutoff,market=None,include_history=True):
    rates=repo.observations('FX','daily_rates');fx_rows=[r for o in rates for r in o.get('rows',[])]
    # Latest acquisition wins only for duplicate reference-date quotes.
    fx_rows=sorted({r['as_of']:r for r in fx_rows}.values(),key=lambda r:r['as_of'])
    companies=[]
    for member in universe['members']:
        inputs=load_inputs(repo,member)
        row=reported(repo,member,cutoff,information_cutoff,fx_rows,inputs=inputs)
        row['financial_signature']=financial_signature(inputs['facts'],information_cutoff)
        sid=row['subject_id'];adjustments=repo.adjustments(sid)
        row['company_events']=events.visible(repo.observations(sid,'company_event'),information_cutoff)
        row['research'],row['economic']=economic.read(repo,sid,information_cutoff,row.get('market_cap'),row.get('basis',{}).get('fx',{}))
        row['adjustments']=economic.adopted_adjustments(adjustments,row['research'],information_cutoff)
        row['history']=monthly_history(repo,member,cutoff,fx_rows,inputs) if include_history else []
        used=set(row['source_fact_ids'])
        for observation in row['history']:used.update(observation['source_fact_ids'])
        row['evidence_facts']=[f for f in inputs['facts'] if f['id'] in used]
        source_ids={f.get('source',{}).get('source_id') for f in row['evidence_facts']}
        source_ids.update((row['research'] or {}).get('source_ids',[]))
        source_ids.update(x.get('source_id') for x in row['company_events'])
        source_ids.add(row.get('basis',{}).get('shares',{}).get('source_id'))
        source_ids.add(row.get('dividend_source_id'))
        import json
        with repo.connect() as c:
            row['sources']=[dict(id=r['id'],**{k:json.loads(r['data']).get(k) for k in ('title','url','published_on')})
                            for r in c.execute('SELECT id,data FROM sources WHERE company_id=?',(sid,)) if r['id'] in source_ids]
        row['historical_percentiles']={key:dict(percentile(row[field]['value'],[h[key] for h in row['history']]),
                                                  start=row['history'][0]['date'] if row['history'] else None,
                                                  end=row['history'][-1]['date'] if row['history'] else None)
                                      for key,field in [('pe','pe_ttm'),('pb','pb')]}
        companies.append(row)
    groups={}
    for group in ('basic','commercial','mixed'):
        rows=[r for r in companies if r['group']==group]
        groups[group]=dict(selected=len(rows),active=sum(r['active'] for r in rows),
                          pe=aggregate(rows,'pe_ttm','earnings'),pb=aggregate(rows,'pb','equity'),
                          cash_proxy=aggregate(rows,'cash_proxy_multiple','cash_proxy'))
        dates=sorted({h['date'] for r in rows for h in r['history']})
        histories={r['code']:{h['date']:h for h in r['history']} for r in rows}
        group_history=[]
        for day in dates:
            observations=[]
            for r in rows:
                h=histories[r['code']].get(day,{})
                observations.append(dict(code=r['code'],market_cap=h.get('market_cap'),earnings=h.get('earnings'),
                                         equity=h.get('equity'),pe_ttm={'value':h.get('pe')},pb={'value':h.get('pb')}))
            group_history.append(dict(date=day,pe=aggregate(observations,'pe_ttm','earnings'),pb=aggregate(observations,'pb','equity')))
        groups[group]['history']=group_history
        groups[group]['historical_percentiles']={key:dict(percentile(groups[group][key]['overall']['value'],[h[key]['overall']['value'] for h in group_history]),
                    start=dates[0] if dates else None,end=dates[-1] if dates else None) for key in ('pe','pb')}
    poly=next(r for r in companies if r['code']=='06049.HK')
    peers=[r for r in companies if r['group']=='basic' and r['code']!=poly['code']]
    relative={}
    for key,field,denom in [('pe','pe_ttm','earnings'),('pb','pb','equity')]:
        vals=[r[field]['value'] for r in peers if r[field]['value'] is not None]
        value=poly[field]['value']
        relative[key]=dict(aggregate(peers,field,denom),own=value,
                           lower_count=sum(v<value for v in vals) if value is not None else None,
                           reference='基础物业同行，排除保利；行业整体包含保利')
    return dict(method_version=VERSION,universe_version=universe['version'],profile=PROPERTY_PROFILE,
                universe_scope=universe['scope'],classification_report=universe.get('classification_report',''),
                information_cutoff=information_cutoff,price_date=cutoff,companies=companies,groups=groups,
                poly_peer_position=relative,market=checked_market(market),
                index_valuations=[dict(r,index=code) for code in ('HSCI','HSLI','HSSI') for r in repo.observations(code,'official_valuation')[-1:]],
                coverage=dict(subjects=len(companies),basic=sum(r['group']=='basic' for r in companies),
                              current_pe=sum(r['pe_ttm']['value'] is not None for r in companies),
                              economic_research=sum(r['research'] is not None for r in companies)),
                boundary='逆向研究辅助；便宜、下跌、统计残差都不自动代表错杀或买卖信号')
