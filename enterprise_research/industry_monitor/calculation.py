"""Pure arithmetic; economic assumptions must arrive as versioned research."""
import calendar
from datetime import date, timedelta
from statistics import median

VERSION = 'industry-valuation-v1'
PROPERTY_PROFILE = {
    'id':'property-basic', 'version':'20261108-v1',
    'name':'基础物业：持续履约、回款与股东现金',
    'primary':['pe_ttm','normalized_earnings_yield','owner_cash_yield'],
    'secondary':['pb','cash_proxy_multiple','dividend_yield','asset_reference'],
    'excluded':{'peg':'增长质量与供资未确定时不用于主排序'},
    'questions':['应收账龄、关联方和拨备能否支持回收？','账上现金有哪些经营和合同义务？',
                 '维护、租赁及少数权益扣后多少钱归普通股？','商誉和客户关系还能贡献多少收益？',
                 '新增业务用款会不会抵消现有盈利？'],
    'minimum_history_months':36,
    'aggregation':'ratio_of_sums_with_losses_and_matched_coverage',
}


def previous_year(day):
    d = date.fromisoformat(day)
    return d.replace(year=d.year-1,day=min(d.day,calendar.monthrange(d.year-1,d.month)[1])).isoformat()


def candidates(facts, metric, cutoff, historical=False):
    result=[]
    versions={}
    for f in facts:
        if f.get('available_on') and f['available_on']<=cutoff:
            key=(f['source_key'],f['metric'],f['period_end'])
            if key not in versions or f.get('revision',1)>versions[key].get('revision',1):versions[key]=f
    for f in versions.values():
        if f['metric'] != metric or f['period_end'] > cutoff or f.get('value') is None:continue
        if not f.get('available_on') or f['available_on'] > cutoff:continue
        if historical and f.get('vintage') not in ('original','dated_restatement'):continue
        if f.get('quality') == 'conflict':continue
        result.append(f)
    return result


def choose(rows):
    if not rows:return None
    return max(rows,key=lambda f:(f['period_end'], f.get('priority',0), f['available_on'],f.get('revision',1)))


def latest(facts, metric, cutoff, historical=False):
    return choose(candidates(facts,metric,cutoff,historical))


def ttm(facts, metric, cutoff, historical=False):
    rows=candidates(facts,metric,cutoff,historical)
    last=choose(rows)
    if not last:return dict(value=None,status='missing',reason='缺少可用披露',fact_ids=[])
    if not last.get('period_start'):
        return dict(value=None,status='unknown_period',reason='累计流量缺少起始日',fact_ids=[last['id']])
    duration=(date.fromisoformat(last['period_end'])-date.fromisoformat(last['period_start'])).days+1
    if 350<=duration<=380:
        return dict(value=last['value'],currency=last['currency'],scope=last['scope'],status='annual',
                    end=last['period_end'],start=last['period_start'],fact_ids=[last['id']],formula='最近完整年度')
    prior_end=previous_year(last['period_end']); prior_start=previous_year(last['period_start'])
    fy_end=(date.fromisoformat(last['period_start'])-timedelta(days=1)).isoformat()
    compatible=[f for f in rows if (f['currency'],f['scope'],f['unit'])==(last['currency'],last['scope'],last['unit'])]
    prior=choose([f for f in compatible if f['period_end']==prior_end and f.get('period_start')==prior_start])
    annual=choose([f for f in compatible if f['period_end']==fy_end and f.get('period_start')==prior_start])
    if prior is None or annual is None:
        return dict(value=None,status='missing_bridge',reason='缺少同口径前一年度或去年同期，不能以中报乘二',fact_ids=[last['id']])
    earlier=[f for f in compatible if f['period_end']==prior_end and f.get('period_start')==prior_start
             and f['available_on']<prior['available_on'] and f.get('vintage')=='original']
    revised=prior.get('comparative_restated') and any(f['value']!=prior['value'] for f in earlier)
    annual_doc=annual.get('source',{}).get('document_id')
    confirmed=any(v.get('annual_document_id')==annual_doc and v.get('status')=='confirmed'
                  and v.get('available_on','9999')<=cutoff for v in last.get('ttm_scope_checks',[]))
    checks=[v for v in last.get('ttm_scope_checks',[]) if v.get('annual_document_id')==annual_doc
            and v.get('available_on','9999')<=cutoff and metric in v.get('metrics',[])]
    check=max(checks,key=lambda v:(v.get('available_on',''),v.get('revision',0))) if checks else None
    if check and check.get('status')=='unresolved':
        return dict(value=None,status='scope_unresolved',end=last['period_end'],reason=check['reason'],
                    fact_ids=[annual['id'],last['id'],prior['id']],scope_checks=[check])
    if revised and annual['available_on']<prior['available_on'] and not confirmed:
        return dict(value=None,status='scope_unresolved',end=last['period_end'],
                    reason='本期重列了去年同期；尚缺最近全年与新比较列同一并表/会计范围的原件依据，暂停TTM拼接',
                    fact_ids=[annual['id'],last['id'],prior['id']])
    return dict(value=annual['value']+last['value']-prior['value'],currency=last['currency'],scope=last['scope'],
                status='ttm',end=last['period_end'],start=(date.fromisoformat(prior_end)+timedelta(days=1)).isoformat(),
                fact_ids=[annual['id'],last['id'],prior['id']],scope_checks=last.get('ttm_scope_checks',[]),
                formula='前一完整年度＋本期累计－去年同期累计')


def convert(value, currency, target, fx):
    if value is None:return None
    if currency==target:return float(value)
    rate=fx.get(currency+'/'+target)
    if rate is None or rate<=0:return None
    return float(value)*rate


def metric(numerator, denominator):
    if numerator is None or denominator is None:return dict(value=None,status='missing')
    if denominator<=0:return dict(value=None,status='nonpositive_denominator',denominator=denominator)
    return dict(value=numerator/denominator,status='ok',denominator=denominator)


def valuation(facts, price, shares, cutoff, fx, historical=False, information_cutoff=None):
    """Price/share observations must be date- and rights-matched by the caller."""
    if price.get('adjustment')!='NONE':raise ValueError('估值必须使用未复权价格')
    if shares.get('kind')!='total_common_shares':raise ValueError('全公司归母估值必须匹配总普通股股数')
    for item in (price,shares):
        if item.get('as_of','9999')>cutoff:raise ValueError('不能使用未来价格或股本')
    information_cutoff=information_cutoff or cutoff
    if historical and information_cutoff!=cutoff:raise ValueError('历史估值的信息截止日必须等于价格日')
    if shares.get('available_on',cutoff)>information_cutoff:raise ValueError('股本资料尚未公开')
    cap=price['close']*shares['value'] if shares.get('value') is not None else None
    currency=price['currency']
    earnings=ttm(facts,'parent_profit',information_cutoff,historical)
    equity=latest(facts,'parent_equity',information_cutoff,historical)
    ocf=ttm(facts,'operating_cash_flow',information_cutoff,historical)
    capex=ttm(facts,'capital_expenditure',information_cutoff,historical)
    e=convert(earnings.get('value'),earnings.get('currency'),currency,fx)
    b=convert(equity['value'],equity['currency'],currency,fx) if equity else None
    same_period=ocf.get('end') is not None and ocf.get('end')==capex.get('end') and ocf.get('start')==capex.get('start')
    cash=None
    if same_period and ocf.get('value') is not None and capex.get('value') is not None:
        o=convert(ocf['value'],ocf['currency'],currency,fx)
        k=convert(capex['value'],capex['currency'],currency,fx)
        if o is not None and k is not None:cash=o-k
    return dict(market_cap=cap,currency=currency,earnings=e,equity=b,cash_proxy=cash,
                pe_ttm=metric(cap,e),pb=metric(cap,b),cash_proxy_multiple=metric(cap,cash),
                earnings_yield=e/cap if e is not None and cap else None,
                cash_proxy_yield=cash/cap if cash is not None and cap else None,
                financial_period=earnings.get('end'),price_date=price['as_of'],shares_date=shares['as_of'],information_cutoff=information_cutoff,
                basis=dict(price=price,shares=shares,fx=fx,earnings=earnings,equity_fact_id=equity['id'] if equity else None,
                           ocf=ocf,capex=capex),
                cash_label='经营现金减资本开支筛查值，尚非普通股可支配现金')


def aggregate(rows, field, denominator):
    included=[r for r in rows if r.get('market_cap') is not None and r.get(denominator) is not None]
    cap=sum(r['market_cap'] for r in included)
    total=sum(r[denominator] for r in included)
    ratios=[r[field]['value'] for r in included if r.get(field,{}).get('value') is not None]
    all_cap=sum(r['market_cap'] for r in rows if r.get('market_cap') is not None)
    return dict(overall=metric(cap,total) if included else metric(None,None),
                median=median(ratios) if ratios else None,valid=len(included),selected=len(rows),
                positive_multiple_count=len(ratios),nonpositive=sum(r[denominator]<=0 for r in included),
                market_cap=cap,denominator_sum=total,market_cap_coverage=cap/all_cap if all_cap else None,
                codes=[r['code'] for r in included],missing_codes=[r['code'] for r in rows if r not in included])


def percentile(current, history, minimum=36):
    values=[v for v in history if v is not None and v>0]
    if current is None or current<=0 or len(values)<minimum:
        return dict(value=None,count=len(values),status='insufficient_history' if len(values)<minimum else 'not_meaningful')
    rank=(sum(v<current for v in values)+.5*sum(v==current for v in values))/len(values)
    return dict(value=rank*100,count=len(values),status='ok')


def asset_bridge(assets, liabilities=0, other_equity=0):
    """Explicit item costs, including unchanged monetary assets; no blanket CPI."""
    total=0
    for item in assets:
        if item.get('monetary') and item.get('factor',1)!=1:
            raise ValueError('货币资产不能按通胀增加名义金额')
        if item.get('factor',1)!=1 and not item.get('basis'):
            raise ValueError('重置调整须说明对应资产与成本依据')
        total+=item['book_value']*item.get('factor',1)
    return total-liabilities-other_equity
