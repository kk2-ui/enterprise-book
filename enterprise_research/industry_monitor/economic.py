"""Read adopted research/calculations from the existing workspace, never revalue silently."""
import json
from .calculation import convert


def adopted_adjustments(rows,research,cutoff):
    if not research:return []
    latest={}
    for row in rows:
        ref=row.get('research_reference',{})
        if row['as_of']<=cutoff and ref.get('project_id')==research['id'] and ref.get('research_revision')==research['revision']:
            latest[row['key']]=row
    return list(latest.values())


def adopt(repo,sid,basis,adopted_on,review_reference):
    from research_workspace import validate_publication
    from .snapshot import financial_signature
    from .events import visible
    if not review_reference:raise ValueError('须记录实际经济审阅依据')
    validate_publication(repo,sid,basis)
    return repo.observe(sid,'research_basis',adopted_on,'research-adoption',
                        dict(basis=basis,review_reference=review_reference,available_on=adopted_on,
                             financial_signature=financial_signature(repo.facts(sid),adopted_on),
                             event_ids=[r['document_id'] for r in visible(repo.observations(sid,'company_event'),adopted_on)]))


def read(repo,sid,information_cutoff,market_cap,fx_rates):
    bases=[r for r in repo.observations(sid,'research_basis') if r['as_of']<=information_cutoff]
    if not bases:return None,None
    selected=bases[-1];b=selected['basis'];pid=b['project_id'];rev=b['research_revision']
    with repo.connect() as c:
        p=c.execute('SELECT data,created_at FROM research_projects WHERE company_id=? AND id=? AND revision=?',(sid,pid,rev)).fetchone()
        if not p:raise ValueError('已采用研究版本不存在')
        research=dict(json.loads(p['data']),id=pid,revision=rev,created_at=p['created_at'],adoption=selected)
        records=[]
        for cid in dict.fromkeys([b.get('calculation_id')]+b.get('calculation_ids',[])):
            if not cid:continue
            r=c.execute('SELECT data,project_revision FROM research_calculations WHERE company_id=? AND project_id=? AND id=?',(sid,pid,cid)).fetchone()
            if not r or r['project_revision']!=rev:raise ValueError('已采用计算与研究版本不匹配')
            records.append(dict(json.loads(r['data']),id=cid,project_revision=rev))
    out=dict(calculations=records,status='conditional',research_date=research['as_of'],adopted_on=selected['as_of'],
             owner_cash_yield=None,owner_cash_reason='所采用模型尚未给出独立的普通股可持续现金金额；不能用合并经营收益替代',
             boundary='沿用列明研究日的条件假设，只以本快照市值重算比较；不是自动刷新内在价值')
    for c in records:
        r=c['result'];kind=r.get('kind',r.get('method'));cur=r.get('currency') or c['inputs'].get('currency')
        def hkd(v):return convert(v,cur,'HKD',fx_rates)
        if kind=='epv':
            equity=hkd(r.get('equity_value'));earnings=hkd(r.get('earnings_power'))
            out['epv']=dict(calculation_id=c['id'],equity_value=r.get('equity_value'),currency=cur,equity_value_hkd=equity,
                            price_to_value=market_cap/equity if market_cap and equity and equity>0 else None,
                            capital_cost=r.get('wacc'),status=r.get('status'),scenarios=r.get('scenarios',[]),
                            equity_bridge=r.get('equity_bridge',[]),earnings_bridge=r.get('earnings_bridge',[]))
            out['operating_earnings_yield']=earnings/market_cap if earnings is not None and market_cap else None
            out['operating_earnings_label']='正常年度合并经营收益/普通股市值（少数股东分配前，非普通股现金收益率）'
        elif kind=='asset_reproduction' or kind=='asset' or 'operating_net_assets' in r:
            equity=hkd(r.get('equity_value'))
            out['asset_reference']=dict(calculation_id=c['id'],equity_value=r.get('equity_value'),currency=cur,
                                       price_to_value=market_cap/equity if market_cap and equity and equity>0 else None,
                                       status=r.get('status'),missing_items=r.get('missing_items',[]),items=r.get('items',[]))
        elif kind=='growth':out['growth']=dict(calculation_id=c['id'],status=r.get('status'),reason=r.get('reason'))
        elif kind=='owner_cash_bridge':
            item=dict(calculation_id=c['id'],**r)
            if r['basis_type']=='normal_condition':
                out['owner_cash']=item
                amount=r['owner_cash']
                out['owner_cash_yield']=hkd(amount)/market_cap if amount is not None and market_cap else None
                out['owner_cash_reason']='普通股现金桥的条件估计；未计量项：'+('、'.join(r['unknown']) or '无空缺，但须满足列明的经营和资本用途条件')
            elif r['basis_type']=='capitalization_equivalent':out.setdefault('capitalization_equivalents',[]).append(item)
            else:out['observed_cash_bridge']=item
        elif kind=='conditional_owner_cash_scenarios':
            rows=r['scenarios'];base=next(v for v in rows if v['name']==c['inputs']['base_scenario'])
            out['owner_cash']=dict(calculation_id=c['id'],amount=base['owner_cash'],currency=cur,
                                  scenarios=rows,status=r['assumption_status'],basis=base['basis'])
            out['owner_cash_yield']=hkd(base['owner_cash'])/market_cap if market_cap else None
            out['owner_cash_reason']='在列明正常利润、更新和留资条件下的普通股年度现金；并非已宣布分红或保证收益。'
        elif kind=='layered_owner_cash':
            amount=r['bridge']['owner_cash']*1e6
            out['owner_cash']=dict(calculation_id=c['id'],amount=amount,currency='CNY',
                                  bridge=r['bridge'],status=r['assumption_status'],basis=c['inputs']['basis'])
            out['owner_cash_yield']=convert(amount,'CNY','HKD',fx_rates)/market_cap if market_cap else None
            out['owner_cash_reason']='由合并现金扣税、租赁、维护、周转及下层权益的条件估计；原计算百万元已转换为元。'
        elif kind=='owner_cash_paths':
            base=next(v for v in r['scenarios'] if v['name']==r['base_scenario'])
            out['cash_path']=dict(calculation_id=c['id'],currency=cur,scenarios=r['scenarios'],status=r['status'],
                                  first_year_cash=base['years'][0]['owner_cash'],terminal_cash=base['terminal_cash'])
            out['owner_cash_reason']='采用恢复/衰减现金路径；首年现金与远期稳定现金分别展示，不折成一个正常年度收益率。'

    return research,out

