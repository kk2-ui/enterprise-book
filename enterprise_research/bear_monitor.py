"""Three-level bear monitoring. Descriptive observations, no trading decisions."""
import math
from datetime import date
from statistics import mean, median, pstdev

from market_context import fit_model, aggregate_noise, solve, peer_daily
from market_data import BENCHMARKS

HORIZONS = (20, 60, 252)


def regime(rows, calendar):
    prices = {r['date']: r['close'] for r in rows}
    dates = [d for d in calendar if d in prices]
    if not dates or dates[-1] != calendar[-1]:
        return {'status': 'unavailable', 'reason': '最新交易日未对齐'}
    values = [prices[d] for d in dates]
    # Preserve the observable long-cycle peak, instead of silently dropping
    # an old bear-market high when a rolling five-year window advances.
    peak_index = max(range(len(values)), key=values.__getitem__)
    peak_date = dates[peak_index]
    drawdown = values[-1]/values[peak_index]-1
    last252 = values[-252:]
    ma200 = mean(values[-200:]) if len(values) >= 200 else None
    old_ma200 = mean(values[-220:-20]) if len(values) >= 220 else None
    slope = ma200/old_ma200-1 if ma200 and old_ma200 else None
    gap = values[-1]/ma200-1 if ma200 else None
    duration = (date.fromisoformat(dates[-1])-date.fromisoformat(peak_date)).days
    deep = drawdown <= -.20 and duration >= 60
    if gap is None or slope is None:
        trend, state = '未知', '历史不足'
    elif gap < 0 and slope < 0:
        trend, state = '下行', '熊市下行' if deep else '下行调整'
    elif gap > 0 and slope > 0:
        trend, state = '上行', '深回撤后的修复' if deep else '上行'
    else:
        trend, state = '震荡', '深回撤中震荡' if deep else '震荡 / 过渡'
    returns = {}
    for h in HORIZONS:
        start = calendar[-h-1] if len(calendar) > h else None
        returns[str(h)] = round((prices[calendar[-1]]/prices[start]-1)*100, 2) if start in prices else None
    return {'status': 'ok', 'state': state, 'trend': trend, 'deep_drawdown': deep,
            'drawdown_pct': round(drawdown*100, 2),
            'drawdown252_pct': round((values[-1]/max(last252)-1)*100, 2),
            'peak_date': peak_date, 'days_since_peak': duration,
            'history_days': len(values), 'history_start': dates[0],
            'full_five_years': len(values) >= 1260,
            'ma200_gap_pct': round(gap*100, 2) if gap is not None else None,
            'ma200_change20_pct': round(slope*100, 2) if slope is not None else None,
            'returns': returns}


def volume_state(rows, calendar):
    by_date = {r['date']: r for r in rows}
    recent, past = calendar[-20:], calendar[-80:-20]
    if len(past) < 40 or not all(d in by_date and by_date[d].get('volume') is not None for d in recent+past):
        return {'status': 'unavailable', 'label': '量价数据不足'}
    baseline = median(by_date[d]['volume'] for d in past)
    total = sum(by_date[d]['volume'] for d in recent)
    if baseline <= 0 or total <= 0 or len(calendar) < 21:
        return {'status': 'unavailable', 'label': '成交过于稀疏'}
    pairs = list(zip(calendar[-21:-1], recent))
    if not all(a in by_date for a, _ in pairs):
        return {'status': 'unavailable', 'label': '量价日期不完整'}
    signed = sum((1 if by_date[b]['close'] > by_date[a]['close'] else -1 if by_date[b]['close'] < by_date[a]['close'] else 0)*by_date[b]['volume'] for a,b in pairs)/total
    ratio = median(by_date[d]['volume'] for d in recent)/baseline
    ret = by_date[recent[-1]]['close']/by_date[calendar[-21]]['close']-1
    activity = '放量' if ratio >= 1.5 else '缩量' if ratio <= .67 else '成交接近平常'
    direction = '上涨' if ret > .005 else '下跌' if ret < -.005 else '横盘'
    return {'status': 'ok', 'label': direction+' · '+activity,
            'activity_ratio': round(ratio, 2), 'signed_volume_balance': round(signed, 3),
            'note': '按涨跌日归类成交量，不是净资金流'}


def peer_portfolio(series, codes, calendar, aggregate=mean, coverage=1):
    if len(codes) < 2:
        return []
    prices = {c:{r['date']:r['close'] for r in series[c]['rows']} for c in codes}
    # Keep the continuous common history ending today. Do not bridge missing bars.
    pairs = []
    for a,b in reversed(list(zip(calendar[:-1],calendar[1:]))):
        daily, count = peer_daily(prices,codes,a,b,aggregate,coverage)
        if daily is None:
            break
        pairs.append((a,b,daily,count))
    pairs.reverse()
    if not pairs:
        return []
    level = 100.0
    rows = [{'date': pairs[0][0], 'close': level}]
    for a,b,daily,count in pairs:
        level *= 1+daily
        rows.append({'date': b, 'close': level,'peer_count':count})
    return rows


def attribution(samples, names, horizon, calendar, thin=False):
    if len(samples) < horizon+126 or [r['date'] for r in samples[-horizon:]] != calendar[-horizon:]:
        return {'status': 'unavailable', 'reason': '需完整观察期及之前至少126个同日训练样本'}
    training, evaluation = samples[-horizon-252:-horizon], samples[-horizon:]
    try:
        fit = fit_model(training, names)
        short = fit_model(training[-126:], names)
    except ValueError as e:
        return {'status': 'unavailable', 'reason': str(e)}
    effects = {key: fit['beta'][key]*sum(r[key] for r in evaluation) for key in names}
    effects['drift'] = fit['alpha']*horizon
    observed = sum(r['stock'] for r in evaluation)
    effects['specific'] = observed-sum(effects.values())
    # Include coefficient-estimation uncertainty. An unusually large market
    # crash amplifies beta uncertainty and must not become a false stock alarm.
    columns = [[r[k] for r in training] for k in names]
    centers, scales = [mean(c) for c in columns], [pstdev(c) for c in columns]
    standard = [[(v-c)/s for v in col] for col,c,s in zip(columns,centers,scales)]
    covariance = [[mean([x*y for x,y in zip(a,b)]) for b in standard] for a in standard]
    displacement = [(sum(r[k] for r in evaluation)-horizon*c)/s for k,c,s in zip(names,centers,scales)]
    solved = solve(covariance,displacement)
    coefficient_variance = sum(r*r for r in fit['residuals'])/(len(training)-len(names)-1)
    coefficient_variance *= (horizon*horizon+sum(a*b for a,b in zip(displacement,solved)))/len(training)
    noise = math.sqrt(aggregate_noise(fit['residuals'], horizon)**2+coefficient_variance)
    z = effects['specific']/noise
    stable = {key:fit['beta'][key]*short['beta'][key]>0 for key in names}
    negatives = sorted([(k,-v) for k,v in effects.items() if v < 0 and k != 'drift'], key=lambda x:x[1], reverse=True)
    driver = 'none'
    if negatives:
        first, strength = negatives[0]
        second = negatives[1][1] if len(negatives)>1 else 0
        if strength < .005:
            driver = 'none'
        elif strength >= 2*second:
            driver = first
        else:
            driver = 'mixed'
    warnings = []
    if effects['drift'] < -max(.005, negatives[0][1] if negatives else 0):
        driver = 'unknown'
        warnings.append('历史平均弱势延续占比较大，不能据此判断其来源')
    if thin:
        warnings.append('成交稀疏，暂停主导判定')
        driver = 'unknown'
    elif fit['vif'] > 10 or fit['r2'] < .2:
        warnings.append('历史拟合不足以稳定区分来源')
        driver = 'unknown'
    elif driver in names and not stable[driver]:
        warnings.append('长短训练期敏感度不同号')
        driver = 'unknown'
    elif driver == 'specific' and z > -2:
        driver = 'unknown'
        warnings.append('未解释偏离尚未明显超出历史波动，不能判定个股因素主导，也不据此推定多种负向压力')
    return {'status':'ok','horizon':horizon,'driver':driver,
            'contributions_log_pp':{k:round(v*100,2) for k,v in effects.items()},
            'observed_log_pp':round(observed*100,2),'specific_z':round(z,2),
            'specific_alert':z <= -2 and effects['specific'] <= -.005 and observed < 0 and not thin and fit['r2'] >= .2 and fit['vif'] <= 10,
            'r2':round(fit['r2'],3),'max_vif':round(fit['vif'],2),
            'training_start':training[0]['date'],'training_end':training[-1]['date'],
            'training_days':len(training),'observation_start':evaluation[0]['date'],
            'warnings':warnings}


def build_monitor(code, series, calendar, eligible, samples, names, thin, cohesion, aggregate=mean, coverage=1):
    broad = BENCHMARKS['HK' if code.endswith('.HK') else 'CN'][0][0]
    market = regime(series[broad]['rows'], calendar)
    stock = regime(series[code]['rows'], calendar)
    portfolio = peer_portfolio(series, eligible, calendar, aggregate, coverage)
    industry = regime(portfolio, calendar) if portfolio else {'status':'unavailable','reason':'同行不足或没有连续可比历史'}
    peer_states = [(c,regime(series[c]['rows'],calendar)) for c in eligible]
    known = [(c,s) for c,s in peer_states if s['status']=='ok' and s['ma200_gap_pct'] is not None]
    industry['breadth'] = {'below_ma200':sum(s['ma200_gap_pct']<0 for _,s in known),'valid':len(known),'selected':len(eligible)}
    industry['cohesion60'] = cohesion
    stock['volume'] = volume_state(series[code]['rows'],calendar)
    volumes = [volume_state(series[c]['rows'],calendar) for c in eligible]
    known_v = [v for v in volumes if v['status']=='ok']
    industry['volume'] = {'valid':len(known_v),'median_activity':round(median(v['activity_ratio'] for v in known_v),2) if known_v else None,
                          'median_signed_balance':round(median(v['signed_volume_balance'] for v in known_v),3) if known_v else None}
    windows={}
    labels={'market':'大盘压力更突出','industry':'行业参照压力更突出','size':'规模风格压力更突出',
            'specific':'个股额外下跌更突出','mixed':'多种压力共同作用','none':'当前未见明显下行压力','unknown':'压力来源暂不能稳定识别'}
    for horizon in HORIZONS:
        result = attribution(samples,names,horizon,calendar,thin)
        if result['status']=='ok':
            limited_reference = len(eligible)<3 or cohesion is None or cohesion<.15
            result['limited_reference'] = limited_reference
            if result['driver'] in ('industry','specific') and limited_reference:
                result['driver']='unknown'
                result['warnings'].append('行业样本少或联动弱，行业与个股原因暂难区分')
            result['driver_label']=labels[result['driver']]
        relative={}
        for key,a,b in [('industry_market',industry,market),('stock_industry',stock,industry),('stock_market',stock,market)]:
            x,y=a.get('returns',{}).get(str(horizon)),b.get('returns',{}).get(str(horizon))
            relative[key]=round(((1+x/100)/(1+y/100)-1)*100,2) if x is not None and y is not None and y>-100 else None
        result['relative_returns']=relative
        valid = [s['returns'][str(horizon)] for _,s in peer_states if s.get('returns',{}).get(str(horizon)) is not None]
        benchmark = market.get('returns',{}).get(str(horizon))
        result['industry_laggards']={'below_market':sum(v<benchmark for v in valid) if benchmark is not None else None,'valid':len(valid)}
        windows[str(horizon)]=result
    a20,a60=windows['20'],windows['60']
    if any(a.get('specific_alert') for a in (a20,a60)):
        limited = any(a.get('specific_alert') and a.get('limited_reference') for a in (a20,a60))
        priority='个股异常待确认' if limited else '个股异常优先核查'
        explanation=('存在模型外的额外下跌，但行业参照不足，不能确定为公司特有原因。' if limited else
                     '本股存在超出共同因素的额外下跌；先核查公司事件、交易异常与模型遗漏。')
    elif (stock.get('deep_drawdown') or (stock.get('trend')=='下行' and (stock.get('returns',{}).get('60') or 0)<0)) and any(x.get('deep_drawdown') for x in (market,industry)):
        priority='共同深回撤背景'
        explanation='本股与市场或行业参照均有长期回撤；'+('本股正在修复，不代表当前仍同步下跌。' if stock.get('trend')=='上行' else '近期压力来源另见20/60日分解。')
    elif stock.get('deep_drawdown'):
        priority='本股深回撤，谨慎核查'
        explanation='本股仍处深回撤，但共同熊市依据不足；不可只按跌幅视为逆向机会。'
    else:
        priority='继续观察'
        explanation='当前未形成明确的共同深回撤候选。'
    warnings=['行业为当前已核实参照名单，不是完整行业总体；全市场个股广度尚未接入。',
              '参数为首版监测口径，未验证为买点；自身偏离不等于已确定的公司原因。']
    if len(eligible)<3:
        warnings.append('行业有效参照少于3家，行业来源判断受限。')
    return {'version':'bear-monitor-v1.1','as_of':calendar[-1],'market':market,'industry':industry,'stock':stock,
            'windows':windows,'research_priority':priority,'research_reason':explanation,'warnings':warnings,
            'market_breadth':None}
