"""Fixed-date cross-sectional sector history; never fill suspended or exited quotes."""
from pathlib import Path
from statistics import mean, median
from market_data import read_json

REGISTRY = Path(__file__).with_name('property_universe.json')
GROUPS = {'basic':'基础物业', 'commercial':'商管驱动', 'mixed':'混合业务'}


def registry():
    return read_json(REGISTRY)


def value_return(prices, start, end):
    if start not in prices or end not in prices:
        return None
    return (prices[end]/prices[start]-1)*100


def rounded(value):
    return round(value, 2) if value is not None else None


def summarize(records, market, own_code):
    peers = [r for r in records if r['code'] != own_code]
    valid = [r for r in peers if r['return_pct'] is not None]
    values = [r['return_pct'] for r in valid]
    all_valid = [r for r in records if r['return_pct'] is not None]
    own = next((r['return_pct'] for r in records if r['code']==own_code), None)
    below = sum(v < market for v in values) if market is not None else None
    return {'selected':len(peers), 'valid':len(valid), 'unknown':len(peers)-len(valid),
            'median_pct':rounded(median(values)) if values else None,
            'initial_equal_mean_pct':rounded(mean(values)) if values else None,
            'below_market':below,
            'below_market_min_pct':rounded(100*below/len(peers)) if peers and below is not None else None,
            'below_market_max_pct':rounded(100*(below+len(peers)-len(valid))/len(peers)) if peers and below is not None else None,
            'own_pct':rounded(own), 'own_rank':1+sum(r['return_pct']>own for r in all_valid) if own is not None else None,
            'rank_total':len(all_valid), 'records':sorted(records,key=lambda r:r['return_pct'] if r['return_pct'] is not None else -1e9,reverse=True)}


def compare(members, prices, start, end, own_code, cohort=None):
    benchmark = value_return(prices.get('HSCI',{}),start,end)
    rows=[]
    for m in members:
        code=m['code'];p=prices.get(code,{})
        if cohort is not None and code not in cohort:
            continue
        # Later listings never receive a synthetic price at an earlier baseline.
        if cohort is None and start not in p:
            continue
        last = max((d for d in p if d<=end),default=None)
        result=value_return(p,start,end)
        rows.append({'code':code,'name':m['name'],'group':m['group'],
                     'return_pct':result,'last_date':last,'status':m.get('status','active'),
                     'last_observed_pct':rounded(value_return(p,start,last)) if last else None})
    groups={g:summarize([r for r in rows if r['group']==g],benchmark,own_code) for g in GROUPS}
    return {'start':start,'end':end,'market_pct':rounded(benchmark),'groups':groups}


def build_history(own_code, series, definition=None):
    definition=definition or registry()
    members=definition['members'];start=definition['baseline']
    prices={code:{r['date']:r['close'] for r in data['rows']} for code,data in series.items()}
    days=sorted(prices.get('HSCI',{}))
    if not days or start not in prices.get('HSCI',{}):
        return {'status':'unavailable','reason':'市场历史未覆盖2021年共同起点'}
    end=days[-1]
    cohort=[m['code'] for m in members
            if m.get('baseline_member', start in prices.get(m['code'],{}))]
    main=compare(members,prices,start,end,own_code,cohort)
    # Both baseline tests retain the same original cohort, so an IPO cannot
    # change a comparison while it is presented as a start-date sensitivity.
    sensitivity=[compare(members,prices,s,end,own_code,cohort)
                 for s in ('2021-06-30','2024-09-23') if s in prices['HSCI']]
    years=sorted({d[:4] for d in days if start < d < end and d[:4] != end[:4]})
    year_ends=[max(d for d in days if d.startswith(y)) for y in years]
    endpoints=year_ends+[end]
    cumulative=[compare(members,prices,start,d,own_code,cohort) for d in endpoints]
    annual=[];previous=start
    for d in endpoints:
        annual.append(compare(members,prices,previous,d,own_code,cohort));previous=d
    later=[m for m in members if m['code'] not in cohort]
    # New listings have their own first observed day and same-day market return.
    later_rows=[]
    for m in later:
        p=prices.get(m['code'],{});first=min(p,default=None)
        later_rows.append(dict(m,first_date=first,last_date=max(p,default=None),
                               return_pct=rounded(value_return(p,first,end)) if first else None,
                               market_pct=rounded(value_return(prices['HSCI'],first,end)) if first else None))
    # Monthly medians are descriptive cross sections, not a rebalanced portfolio.
    monthly={d[:7]:d for d in days if d>=start}
    chart=[]
    for d in dict.fromkeys([start]+list(monthly.values())):
        c=compare(members,prices,start,d,own_code,cohort);b=c['groups']['basic']
        chart.append({'date':d,'stock':b['own_pct'],'market':c['market_pct'],
                      'industry':b['median_pct'],'valid':b['valid'],'selected':b['selected']})
    for c in [main]+sensitivity+cumulative+annual:
        for g in c['groups'].values():
            for r in g['records']:r['return_pct']=rounded(r['return_pct'])
    return {'status':'ready','version':definition['version'],'as_of':end,'baseline':start,
            'scope':definition['scope'],'group_names':GROUPS,'members':members,
            'main':main,'sensitivity':sensitivity,'cumulative':cumulative,'annual':annual,
            'later_listings':later_rows,'chart':chart,
            'notes':['行业中位数、均值和广度均剔除本股；排名包含本股。固定2021起点名单，停牌、退市保留为缺值，不延用旧收盘价。',
                     '股票为当前前复权价格，恒生综合为价格指数；这是行情表现比较，不是统一含息收益率或可投资组合回测。',
                     '均值为期初等权的个股区间变动均值；中位数代表典型样本，两者都不是每日等权调仓收益。',
                     '年末及月末统计只用当日可观察的原始名单成员，显示实际覆盖，成员缺失会改变横截面构成。']}
