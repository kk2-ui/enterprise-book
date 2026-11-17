"""Observed market context, with a prior-window factor model and visible peers."""
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime, timedelta, timezone
import json
import math
from pathlib import Path
import re
import sqlite3
from statistics import mean, median, pstdev
from threading import Lock

from market_data import (
    BENCHMARKS, QuoteCache, brent_completed_date, canonical, completed_date,
    now_iso, read_json, write_json,
)


PROFILE_FILE = Path(__file__).with_name('market_peers.json')
METHOD_VERSION = 'market-context-v2.2-sector'
WINDOWS = (5, 20, 60)
TRAIN_DAYS = 120
MIN_TRAIN = 80


def percentage(value):
    return round(math.expm1(value) * 100, 2)


def correlation(left, right):
    if len(left) < 2 or not pstdev(left) or not pstdev(right):
        return None
    left_mean, right_mean = mean(left), mean(right)
    return sum((a-left_mean)*(b-right_mean) for a, b in zip(left, right)) / (len(left)*pstdev(left)*pstdev(right))


def solve(matrix, values):
    """Pivoted elimination for the small, standardised factor system."""
    size = len(values)
    work = [list(row) + [value] for row, value in zip(matrix, values)]
    for column in range(size):
        pivot = max(range(column, size), key=lambda row: abs(work[row][column]))
        if abs(work[pivot][column]) < 1e-9:
            raise ValueError('参照序列过于同步，无法分别估计')
        work[column], work[pivot] = work[pivot], work[column]
        divisor = work[column][column]
        work[column] = [v/divisor for v in work[column]]
        for row in range(size):
            if row == column:
                continue
            factor = work[row][column]
            work[row] = [a-factor*b for a, b in zip(work[row], work[column])]
    return [row[-1] for row in work]


def fit_model(samples, names):
    ys = [row['stock'] for row in samples]
    columns = [[row[key] for row in samples] for key in names]
    centers = [mean(col) for col in columns]
    scales = [pstdev(col) for col in columns]
    if any(scale < 1e-7 for scale in scales) or pstdev(ys) < 1e-7:
        raise ValueError('有效价格变化不足，无法估计敏感度')
    standard = [[(value-center)/scale for value in col]
                for col, center, scale in zip(columns, centers, scales)]
    cov = [[mean([a*b for a, b in zip(x, y)]) for y in standard] for x in standard]
    target = [mean([a*(y-mean(ys)) for a, y in zip(x, ys)]) for x in standard]
    weights = solve(cov, target)
    beta = [weight/scale for weight, scale in zip(weights, scales)]
    alpha = mean(ys) - sum(b*c for b, c in zip(beta, centers))
    residuals = [row['stock'] - alpha - sum(b*row[key] for b, key in zip(beta, names)) for row in samples]
    variance = sum((y-mean(ys))**2 for y in ys)
    r2 = 1-sum(r*r for r in residuals)/variance
    vifs = [solve(cov, [float(i == j) for i in range(len(names))])[j] for j in range(len(names))]
    return {'alpha': alpha, 'beta': dict(zip(names, beta)), 'r2': r2,
            'vif': max(vifs), 'residuals': residuals}


def aggregate_noise(residuals, horizon):
    """Horizon noise scale with up to five autocovariance lags. Not a probability."""
    center = mean(residuals)
    residuals = [value-center for value in residuals]
    variance = mean([v*v for v in residuals])
    total = horizon*variance
    for lag in range(1, min(5, horizon-1)+1):
        covariance = mean([a*b for a, b in zip(residuals[lag:], residuals[:-lag])])
        total += 2*(horizon-lag)*(1-lag/6)*covariance
    return math.sqrt(max(total, variance*horizon*.1, 1e-12))


def return_over(prices, calendar, days):
    if len(calendar) <= days:
        return None
    first, last = calendar[-days-1], calendar[-1]
    if first not in prices or last not in prices:
        return None
    return round((prices[last]/prices[first]-1)*100, 2)


def peer_daily(prices, codes, previous, today, aggregate=mean, coverage=1):
    values = [prices[c][today]/prices[c][previous]-1 for c in codes
              if previous in prices[c] and today in prices[c]]
    required = max(5 if coverage < 1 else 2, math.ceil(len(codes)*coverage))
    return (aggregate(values) if len(values) >= required else None), len(values)


def stock_metrics(data, calendar):
    prices = {row['date']: row['close'] for row in data['rows']}
    active = {row['date']: row.get('volume') for row in data['rows']}
    recent = calendar[-20:]
    baseline = calendar[-80:-20]
    volumes = [active[day] for day in recent if day in active and active[day] is not None]
    old_volumes = [active[day] for day in baseline if day in active and active[day] is not None]
    volume_ratio = None
    if len(volumes) >= 16 and len(old_volumes) >= 40 and median(old_volumes) > 0:
        volume_ratio = round(median(volumes)/median(old_volumes), 2)
    values = [prices[d] for d in calendar[-60:] if d in prices]
    last = prices.get(calendar[-1])
    ma20 = mean(values[-20:]) if len(values) >= 20 else None
    ma60 = mean(values) if len(values) == 60 else None
    trend = '数据不足'
    if ma20 and ma60 and last:
        trend = '上行' if last > ma20 > ma60 else '下行' if last < ma20 < ma60 else '震荡 / 过渡'
    current60 = calendar[-60:]
    zero_volume = sum(active.get(day, 0) == 0 for day in current60)
    flat = sum(prices.get(a) == prices.get(b) for a, b in zip(current60[:-1], current60[1:]) if a in prices and b in prices)
    peak = 0
    drawdown = 0
    for value in values:
        peak = max(peak, value)
        drawdown = min(drawdown, value/peak-1)
    return {'returns': {str(h): return_over(prices, calendar, h) for h in (*WINDOWS, 252)},
            'trend': trend, 'ma20_gap': round((last/ma20-1)*100, 2) if last and ma20 else None,
            'ma60_gap': round((last/ma60-1)*100, 2) if last and ma60 else None,
            'volume_ratio': volume_ratio, 'no_trade_days': zero_volume,
            'flat_days': flat, 'drawdown60': round(drawdown*100, 2),
            'thin': zero_volume > 12 or flat > 30}


def prior_window_analysis(samples, names, horizon, peer_count, thin):
    if len(samples) < horizon + MIN_TRAIN:
        return {'status': 'insufficient', 'reason': '同日可比数据不足，需至少80个训练日及完整观察窗口'}
    evaluation = samples[-horizon:]
    training = samples[max(0, len(samples)-horizon-TRAIN_DAYS):-horizon]
    try:
        model = fit_model(training, names)
        short = fit_model(training[-60:], names)
    except ValueError as error:
        return {'status': 'insufficient', 'reason': str(error)}
    parts = {key: model['beta'][key]*sum(row[key] for row in evaluation) for key in names}
    drift = model['alpha']*horizon
    common = sum(parts.values())
    observed = sum(row['stock'] for row in evaluation)
    unexplained = observed - common - drift
    noise = aggregate_noise(model['residuals'], horizon)
    scale = unexplained/noise
    effects = sorted(parts, key=lambda key: abs(parts[key]), reverse=True)
    first = effects[0]
    second = abs(parts[effects[1]]) if len(effects) > 1 else 0
    stable = model['beta'][first]*short['beta'][first] > 0
    reasons = []
    if model['vif'] > 10:
        reasons.append('因素高度同步，分别归因不稳定')
    if model['r2'] < .2:
        reasons.append('历史共同因素解释力较低')
    if not stable:
        reasons.append('60日和120日估计方向不一致')
    if thin:
        reasons.append('本股成交稀疏，价格敏感度可能失真')
    if 'industry' not in names:
        reasons.append('合格同行不足，行业影响尚未纳入')
    if peer_count and peer_count < 3:
        reasons.append('同行样本仅两家，结论依赖个别公司')
    reliable = model['vif'] <= 10 and model['r2'] >= .2 and not thin and stable
    dominant = first if reliable and abs(parts[first]) >= 2*second and abs(parts[first]) >= .005 else 'mixed'
    labels = {'market': '大盘影响更突出', 'size': '市值风格影响更突出', 'industry': '行业参照影响更突出', 'mixed': '共同影响，主次不清'}
    noise_floor = max(.005, noise*.25)
    wind = '顺风' if common > noise_floor else '逆风' if common < -noise_floor else '影响较小'
    if thin or model['r2'] < .2:
        wind = '证据较弱'
    deviation = '额外走强' if scale >= 2 else '额外走弱' if scale <= -2 else '偏离处于常见波动内'
    if thin:
        deviation = '成交稀疏，偏离待核'
    return {'status': 'ok', 'wind': wind, 'dominant': dominant, 'dominant_label': labels[dominant],
            'deviation': deviation, 'deviation_scale': round(scale, 2),
            'common_effect_pct': percentage(common), 'model_return_pct': percentage(common+drift),
            'actual_return_pct': percentage(observed), 'residual_log_pp': round(unexplained*100, 2),
            'parts_log_pp': {key: round(value*100, 2) for key, value in parts.items()},
            'alpha_log_pp': round(drift*100, 2), 'observed_log_pp': round(observed*100, 2),
            'betas': {key: round(value, 3) for key, value in model['beta'].items()},
            'r2': round(model['r2'], 3), 'max_vif': round(model['vif'], 2),
            'training_start': training[0]['date'], 'training_end': training[-1]['date'],
            'training_days': len(training), 'evaluation_start': evaluation[0]['date'],
            'evaluation_end': evaluation[-1]['date'], 'limitations': reasons,
            'comparison_beta60': round(short['beta'][first], 3)}


def build_context(code, profile, series, errors, cutoff, profile_version, sector_definition=None):
    peer_aggregate = median if profile.get('aggregation') == 'daily_median' else mean
    peer_coverage = .8 if profile.get('aggregation') == 'daily_median' else 1
    market = 'HK' if code.endswith('.HK') else 'CN'
    benchmark_spec = BENCHMARKS[market]
    broad, small, large = [item[0] for item in benchmark_spec]
    base = {'code': code, 'method_version': METHOD_VERSION, 'profile_version': profile_version,
            'profile': profile, 'captured_at': now_iso(), 'requested_through': cutoff, 'errors': errors}
    if code not in series or broad not in series:
        return dict(base, status='unavailable', reason='个股或市场基准暂未取得完整日线', sources=[])
    market_dates = [row['date'] for row in series[broad]['rows']]
    as_of = market_dates[-1]
    own = series[code]
    if own['rows'][-1]['date'] != as_of:
        return dict(base, status='unavailable', reason='个股与市场的最新日期不一致，可能停牌或行情延迟',
                    as_of=own['rows'][-1]['date'], market_as_of=as_of, sources=[])
    prices = {key: {row['date']: row['close'] for row in item['rows']} for key, item in series.items()}
    peers = []
    eligible = []
    for spec in profile['peers']:
        peer = dict(spec, included=False)
        data = series.get(spec['code'])
        if not data:
            peer['exclusion'] = '行情缺失'
        elif data['rows'][-1]['date'] != as_of:
            peer['exclusion'] = '最新日期未对齐'
        elif sum(day in prices[spec['code']] for day in market_dates[-180:]) < min(180, len(market_dates))*.95:
            peer['exclusion'] = '近180日覆盖不足95%'
        else:
            peer['metrics'] = stock_metrics(data, market_dates)
            if peer['metrics']['thin']:
                peer['exclusion'] = '近60日成交或价格变化稀疏'
            else:
                peer['included'] = True
                eligible.append(spec['code'])
            cap, own_cap = data.get('float_cap'), own.get('float_cap')
            peer['float_cap'] = cap
            peer['size_ratio'] = round(cap/own_cap, 2) if cap and own_cap else None
            peer['similar_size'] = bool(cap and own_cap and 1/3 <= cap/own_cap <= 3)
        peers.append(peer)
    names = ['market']
    if all(key in prices and as_of in prices[key] for key in (small, large)):
        names.append('size')
    if len(eligible) >= 2:
        names.append('industry')
    samples = []
    for previous, today in zip(market_dates[:-1], market_dates[1:]):
        keys = [code, broad] + ([small, large] if 'size' in names else [])
        if not all(previous in prices[key] and today in prices[key] for key in keys):
            continue
        ret = {key: math.log(prices[key][today]/prices[key][previous]) for key in keys}
        row = {'date': today, 'stock': ret[code], 'market': ret[broad]}
        if 'size' in names:
            row['size'] = ret[small]-ret[large]
        if 'industry' in names:
            daily, count = peer_daily(prices, eligible, previous, today, peer_aggregate, peer_coverage)
            if daily is None:
                continue
            row['peer'] = math.log1p(daily)
            row['peer_count'] = count
            row['industry'] = row['peer']-ret[broad]
        samples.append(row)
    own_metrics = stock_metrics(own, market_dates)
    peer_correlations = []
    for index, left in enumerate(eligible):
        for right in eligible[index+1:]:
            pairs = [(a,b) for a,b in zip(market_dates[-61:-1],market_dates[-60:])
                     if all(day in prices[key] for day in (a,b) for key in (left,right))]
            if len(pairs) >= 40:
                value = correlation([math.log(prices[left][b]/prices[left][a]) for a,b in pairs],
                                    [math.log(prices[right][b]/prices[right][a]) for a,b in pairs])
                if value is not None:
                    peer_correlations.append(value)
    cohesion = round(median(peer_correlations), 2) if peer_correlations else None
    windows = {}
    for horizon in WINDOWS:
        recent_calendar = market_dates[-horizon:]
        if [row['date'] for row in samples[-horizon:]] != recent_calendar:
            result = {'status': 'insufficient', 'reason': '观察窗口缺交易日，暂缓敏感度分析'}
        else:
            result = prior_window_analysis(samples, names, horizon, len(eligible), own_metrics['thin'])
        valid = [peer for peer in peers if peer.get('metrics', {}).get('returns', {}).get(str(horizon)) is not None and peer['included']]
        returns = [peer['metrics']['returns'][str(horizon)] for peer in valid]
        own_return = own_metrics['returns'][str(horizon)]
        result['breadth'] = {'positive': sum(value > 0 for value in returns), 'total': len(returns),
                             'median_return': round(median(returns), 2) if returns else None}
        result['peer_excess_pp'] = round(own_return-median(returns), 2) if own_return is not None and returns else None
        if result['status'] == 'ok' and cohesion is not None and cohesion < .15:
            result['limitations'].append('同行近60日价格联动较弱，行业参照的代表性有限')
            if result['dominant'] == 'industry':
                result['dominant'] = 'mixed'
                result['dominant_label'] = '同行表现分化，主次待定'
        result['since'] = market_dates[-horizon-1] if len(market_dates) > horizon else None
        windows[str(horizon)] = result
    chart = []
    # Display prices on the complete market calendar. A missing bar remains a gap.
    chart_days = market_dates[-253:]
    calendar_previous = dict(zip(market_dates[1:], market_dates[:-1]))
    for day in chart_days:
        row = {'date': day, 'stock': prices[code].get(day), 'market': prices[broad].get(day),
               'small': prices.get(small, {}).get(day)}
        previous = calendar_previous.get(day)
        daily, count = peer_daily(prices, eligible, previous, day, peer_aggregate, peer_coverage)
        row['peer_available'] = daily is not None
        row['peer_return'], row['peer_count'] = daily, count
        chart.append(row)
    benchmarks = [{'code': key, 'name': name, 'metrics': stock_metrics(series[key], market_dates)}
                  for key, name, _ in benchmark_spec if key in series]
    sources = [{key: data.get(key) for key in ('code','name','source','source_url','adjustment','captured_at')}
               | {'last_date': data['rows'][-1]['date']} for data in series.values()]
    from bear_monitor import build_monitor
    monitor = build_monitor(code, series, market_dates, eligible, samples, names, own_metrics['thin'], cohesion,
                            aggregate=peer_aggregate, coverage=peer_coverage)
    history = None
    if profile.get('sector_history') == 'property':
        from sector_history import build_history
        history = build_history(code, series, sector_definition)
    return dict(base, status='ready', name=own['name'], as_of=as_of, currency=own['currency'], monitor=monitor,
                float_cap=own.get('float_cap'), cap_as_of=own.get('cap_as_of'), metrics=own_metrics,
                windows=windows, benchmarks=benchmarks, peers=peers, peer_correlation60=cohesion,
                chart=chart, sources=sources, sector_history=history,
                lag_days=(date.fromisoformat(cutoff)-date.fromisoformat(as_of)).days,
                labels={'market': benchmark_spec[0][1], 'small': benchmark_spec[1][1],
                        'industry': profile['label'], 'stock': own['name']})

PETROCHINA_CODES = {'601857.SH', '00857.HK'}
PILOT_METHOD_VERSION = 'petrochina-market-pilot-v2'
FIGURE_TAG_RE = re.compile(r'\[\[?figure:([\w-]+)\|([^\]\n]*)\]?\]')
BRENT_INSTRUMENT = {
    'code': 'BRENT',
    'name': '布伦特原油期货连续',
    'secid': '112.B00Y',
    'source': '东方财富期货连续日线',
    'adjustment': 'CONTINUOUS_FUTURES',
    'currency': 'USD',
    'unit': '美元/桶',
}
PETROCHINA_ANNOUNCEMENTS = (
    {
        'id': 'storage2025',
        'published_on': '2025-12-04',
        'short_label': '储气库公告',
        'title': '中国石油储气库关联交易补充公告',
        'url': ('ht' + 'tps://www1.hkexnews.hk/listedco/listconews/sehk/2025/1204/2025120402102.pdf'),
    },
    {
        'id': 'related2027',
        'published_on': '2026-03-29',
        'short_label': '关联交易续签',
        'title': '中国石油2027-2029年续签关联交易及新金融服务协议',
        'url': ('ht' + 'tps://www1.hkexnews.hk/listedco/listconews/sehk/2026/0329/2026032900155.pdf'),
    },
    {
        'id': 'annual2025',
        'published_on': '2026-04-23',
        'short_label': '2025年报',
        'title': '中国石油2025年度报告',
        'url': ('ht' + 'tps://www.hkexnews.hk/listedco/listconews/sehk/2026/0423/2026042301797.pdf'),
    },
    {
        'id': 'results2026h1',
        'published_on': '2026-08-30',
        'short_label': '中期业绩公告',
        'title': '中国石油2026年中期业绩公告（披露单位操作成本）',
        'url': ('ht' + 'tps://www1.hkexnews.hk/listedco/listconews/sehk/2026/0830/2026083000018_c.pdf#page=14'),
    },
    {
        'id': 'div2026',
        'published_on': '2026-08-30',
        'short_label': '中期股息安排',
        'title': '中国石油2026年中期股息及税务安排公告',
        'url': ('ht' + 'tps://www1.hkexnews.hk/listedco/listconews/sehk/2026/0830/2026083000031.pdf'),
    },
    {
        'id': 'h12026',
        'published_on': '2026-09-18',
        'short_label': '2026中报',
        'title': '中国石油2026年中期报告（第25页披露单位操作成本）',
        'url': ('ht' + 'tps://www1.hkexnews.hk/listedco/listconews/sehk/2026/0918/2026091800441.pdf#page=25'),
    },
    {
        'id': 'q32026',
        'published_on': '2026-10-28',
        'short_label': '2026三季报',
        'title': '中国石油2026年第三季度报告',
        'url': ('ht' + 'tps://www.petrochina.com.cn/petrochina/jdbg/202610/ed4e45a0d81149dab4549bd4cc570db4/files/e054e03d628b46588536bf47673d167f.pdf'),
    },
)
PETROCHINA_COST_SPEC = {
    'metric': '单位油气操作成本',
    'unit': '美元/桶',
    'prior_period': '2025年上半年',
    'current_period': '2026年上半年',
    'prior_value': 10.14,
    'current_value': 10.68,
    'yoy_pct': 5.3,
    'delta_value': 0.54,
    'first_disclosed_on': '2026-08-30',
    'interim_report_published_on': '2026-09-18',
    'source_title': '中国石油2026年中期报告（PDF第25页）',
    'source_url': ('ht' + 'tps://www1.hkexnews.hk/listedco/listconews/sehk/2026/0918/2026091800441.pdf#page=25'),
    'first_disclosure_title': '中国石油2026年中期业绩公告（港交所中文版第14页）',
    'first_disclosure_url': ('ht' + 'tps://www1.hkexnews.hk/listedco/listconews/sehk/2026/0830/2026083000018_c.pdf#page=14'),
    'first_disclosure_en_title': 'PetroChina 2026 Interim Results Announcement（英文版第17页）',
    'first_disclosure_en_url': ('ht' + 'tps://www.petrochina.com.cn/ptr/gsgg/202608/34203ea324a34ce8bb932236307b8825/files/f3731ec60e2540eea6170ff1cfef5e85.pdf#page=17'),
    'local_doc_id': 'h12026',
    'local_doc_page': 25,
    'scope_note': '仅在同一半年度口径间对比，不拿全年数据与半年数据横比（半年度不含年末集中结算项）。单位油气操作成本仅反映油气生产现场操作付现支出，不含折旧折耗及摊销、勘探费用、税费、财务费用与维持性资本开支，不能当作完整盈亏线。',
}
PETROCHINA_VALUATION_SPEC = {
    'snapshot_date': '2026-11-13',
    'return_rate_pct': 10,
    'tax_basis': '投资者个人税前',
    'base_normal_cash_yi': 1150,
    'h_implied_cash_yi': 1618,
    'h_implied_cash_exact_yi': 1618.43,
    'a_implied_cash_yi': 2268,
    'a_implied_cash_exact_yi': 2267.63,
    'base_epv_cny': 6.28,
    'base_epv_hkd': 7.34,
    'a_close_cny': 12.39,
    'h_close_hkd': 10.33,
    'hkd_cny': 0.85604,
    'formal_edition_title': '中国石油企业书 · 修订版 v1',
    'formal_figure_title': '中国石油A/H价格的年度现金要求',
    'local_source_version': 'petrochina-sources-20261115-v1',
    'formal_model_name': 'Codex',
    'formal_model_version': 'gpt-6.1-sol',
}


def validate_cutoff_date(as_of):
    if as_of is None or str(as_of).strip() == '':
        return None
    value = str(as_of).strip()
    if not re.fullmatch(r'\d{4}-\d{2}-\d{2}', value):
        raise ValueError('观察截止日须使用 YYYY-MM-DD 格式')
    date.fromisoformat(value)
    return value


def _weekday_calendar(start_iso, end_iso, observed_dates):
    cur = date.fromisoformat(start_iso)
    end = date.fromisoformat(end_iso)
    days = []
    while cur <= end:
        iso = cur.isoformat()
        is_jan1_closed = (cur.month == 1 and cur.day == 1 and iso not in observed_dates)
        if iso in observed_dates or (cur.weekday() < 5 and not is_jan1_closed):
            days.append(iso)
        cur += timedelta(days=1)
    return days


def build_petrochina_cost(cutoff, company=None):
    visible = cutoff >= PETROCHINA_COST_SPEC['first_disclosed_on']
    interim_report_visible = cutoff >= PETROCHINA_COST_SPEC['interim_report_published_on']
    editions = (company or {}).get('book_editions') or []
    has_local_pkg = any(
        e.get('source_version') == PETROCHINA_VALUATION_SPEC['local_source_version']
        for e in editions
    )
    local_doc_visible = interim_report_visible and has_local_pkg
    cost_sources = []
    if interim_report_visible:
        cost_sources.append({
            'id': 'h12026',
            'published_on': PETROCHINA_COST_SPEC['interim_report_published_on'],
            'title': f"中报原文：{PETROCHINA_COST_SPEC['source_title']}（{PETROCHINA_COST_SPEC['interim_report_published_on']}刊发）",
            'url': PETROCHINA_COST_SPEC['source_url'],
        })
    if visible:
        cost_sources.append({
            'id': 'results2026h1_zh',
            'published_on': PETROCHINA_COST_SPEC['first_disclosed_on'],
            'title': f"首次公开：{PETROCHINA_COST_SPEC['first_disclosure_title']}（{PETROCHINA_COST_SPEC['first_disclosed_on']}）",
            'url': PETROCHINA_COST_SPEC['first_disclosure_url'],
        })
        cost_sources.append({
            'id': 'results2026h1_en',
            'published_on': PETROCHINA_COST_SPEC['first_disclosed_on'],
            'title': f"{PETROCHINA_COST_SPEC['first_disclosure_en_title']}（{PETROCHINA_COST_SPEC['first_disclosed_on']}）",
            'url': PETROCHINA_COST_SPEC['first_disclosure_en_url'],
        })
    return {
        'metric': PETROCHINA_COST_SPEC['metric'],
        'unit': PETROCHINA_COST_SPEC['unit'],
        'prior_period': PETROCHINA_COST_SPEC['prior_period'],
        'current_period': PETROCHINA_COST_SPEC['current_period'],
        'first_disclosed_on': PETROCHINA_COST_SPEC['first_disclosed_on'],
        'interim_report_published_on': PETROCHINA_COST_SPEC['interim_report_published_on'] if interim_report_visible else None,
        'requested_through': cutoff,
        'visible': visible,
        'prior_value': PETROCHINA_COST_SPEC['prior_value'] if visible else None,
        'current_value': PETROCHINA_COST_SPEC['current_value'] if visible else None,
        'yoy_pct': PETROCHINA_COST_SPEC['yoy_pct'] if visible else None,
        'delta_value': PETROCHINA_COST_SPEC['delta_value'] if visible else None,
        'blank_reason': None if visible else (
            f"历史截止日（{cutoff}）早于该数据首次公开日期（{PETROCHINA_COST_SPEC['first_disclosed_on']}），"
            "此处按当时公开信息边界留空。"
        ),
        'source_title': PETROCHINA_COST_SPEC['source_title'] if interim_report_visible else None,
        'source_url': PETROCHINA_COST_SPEC['source_url'] if interim_report_visible else None,
        'first_disclosure_title': PETROCHINA_COST_SPEC['first_disclosure_title'] if visible else None,
        'first_disclosure_url': PETROCHINA_COST_SPEC['first_disclosure_url'] if visible else None,
        'first_disclosure_en_url': PETROCHINA_COST_SPEC['first_disclosure_en_url'] if visible else None,
        'local_source_version': PETROCHINA_VALUATION_SPEC['local_source_version'] if local_doc_visible else None,
        'local_doc_id': PETROCHINA_COST_SPEC['local_doc_id'] if local_doc_visible else None,
        'local_doc_page': PETROCHINA_COST_SPEC['local_doc_page'] if local_doc_visible else None,
        'sources': cost_sources,
        'scope_note': PETROCHINA_COST_SPEC['scope_note'],
    }


def _is_petrochina_formal_edition(edition):
    if not isinstance(edition, dict):
        return False
    if edition.get('format') == 'legacy_snapshot':
        return False
    if (
        edition.get('title') != PETROCHINA_VALUATION_SPEC['formal_edition_title']
        or edition.get('information_cutoff') != PETROCHINA_VALUATION_SPEC['snapshot_date']
        or edition.get('source_version') != PETROCHINA_VALUATION_SPEC['local_source_version']
    ):
        return False
    model = edition.get('model')
    if isinstance(model, dict):
        m_name = str(model.get('name') or '').strip()
        m_ver = str(model.get('version') or '').strip()
        if m_name and m_name != PETROCHINA_VALUATION_SPEC['formal_model_name']:
            return False
        if m_ver and m_ver != PETROCHINA_VALUATION_SPEC['formal_model_version']:
            return False
    return True


def _extract_formal_threshold_figure(company, target, edition_loader=None):
    if not target:
        return None
    parts = target.get('parts')
    if not isinstance(parts, dict) and callable(edition_loader):
        loaded = edition_loader((company or {}).get('id'), target.get('id'))
        if isinstance(loaded, dict):
            if not _is_petrochina_formal_edition(loaded | {'id': target.get('id')}):
                return None
            parts = loaded.get('parts')
    if not isinstance(parts, dict):
        return None
    sources_by_id = {
        s['id']: s
        for s in ((company or {}).get('sources') or [])
        if isinstance(s, dict) and s.get('id') and s.get('available', True)
    }
    if not sources_by_id:
        return None
    ordered_slots = ['valuation', 'chapter-7'] + [
        key for key in parts.keys() if key not in ('valuation', 'chapter-7')
    ]
    expected_title = PETROCHINA_VALUATION_SPEC['formal_figure_title']
    for slot in ordered_slots:
        part = parts.get(slot)
        body = part.get('body', '') if isinstance(part, dict) else ''
        for sid, caption in FIGURE_TAG_RE.findall(body or ''):
            src = sources_by_id.get(sid)
            if not src:
                continue
            if (
                src.get('title') == expected_title
                or expected_title in caption
                or '年度现金要求' in caption
                or '年度现金门槛' in caption
            ):
                return src
    return None


def build_petrochina_valuation(company, cutoff, edition_loader=None):
    cid = (company or {}).get('id')
    editions = (company or {}).get('book_editions') or []
    matches = [e for e in editions if _is_petrochina_formal_edition(e)]
    target = next(
        (e for e in matches
         if isinstance(e.get('model'), dict)
         and e['model'].get('name') == PETROCHINA_VALUATION_SPEC['formal_model_name']),
        matches[0] if matches else None,
    )
    fig_source = _extract_formal_threshold_figure(company, target, edition_loader=edition_loader)
    edition_id = target['id'] if target else None
    return {
        'snapshot_date': PETROCHINA_VALUATION_SPEC['snapshot_date'],
        'return_rate_pct': PETROCHINA_VALUATION_SPEC['return_rate_pct'],
        'tax_basis': PETROCHINA_VALUATION_SPEC['tax_basis'],
        'base_normal_cash_yi': PETROCHINA_VALUATION_SPEC['base_normal_cash_yi'],
        'h_implied_cash_yi': PETROCHINA_VALUATION_SPEC['h_implied_cash_yi'],
        'h_implied_cash_exact_yi': PETROCHINA_VALUATION_SPEC['h_implied_cash_exact_yi'],
        'a_implied_cash_yi': PETROCHINA_VALUATION_SPEC['a_implied_cash_yi'],
        'a_implied_cash_exact_yi': PETROCHINA_VALUATION_SPEC['a_implied_cash_exact_yi'],
        'base_epv_cny': PETROCHINA_VALUATION_SPEC['base_epv_cny'],
        'base_epv_hkd': PETROCHINA_VALUATION_SPEC['base_epv_hkd'],
        'a_close_cny': PETROCHINA_VALUATION_SPEC['a_close_cny'],
        'h_close_hkd': PETROCHINA_VALUATION_SPEC['h_close_hkd'],
        'hkd_cny': PETROCHINA_VALUATION_SPEC['hkd_cny'],
        'edition_id': edition_id,
        'edition_title': target.get('title') if target else PETROCHINA_VALUATION_SPEC['formal_edition_title'],
        'edition_valuation_url': f"#/company/{cid}/editions?edition={edition_id}&view=valuation" if cid and edition_id else None,
        'edition_overview_url': f"#/company/{cid}/editions?edition={edition_id}&view=overview" if cid and edition_id else None,
        'figure_title': PETROCHINA_VALUATION_SPEC['formal_figure_title'],
        'figure_url': f"/api/sources/{fig_source['id']}/file" if fig_source else None,
        'cutoff_precedes_snapshot': cutoff < PETROCHINA_VALUATION_SPEC['snapshot_date'],
        'note': '沿用 2026-11-13 正式版企业书研究快照（按 10% 股权回报反算，投资者个人税前），不重新建模，亦不倒铺至历史股价。',
    }


def build_petrochina_pilot(code, series, errors, cutoff, company=None, brent_cutoff=None, edition_loader=None):
    effective_brent_cutoff = min(cutoff, brent_cutoff) if brent_cutoff else cutoff
    filtered = {}
    for key in ('601857.SH', '00857.HK', 'BRENT'):
        item = series.get(key)
        if item:
            key_cutoff = effective_brent_cutoff if key == 'BRENT' else cutoff
            rows = [row for row in item.get('rows', []) if row['date'] <= key_cutoff]
            if rows:
                filtered[key] = dict(item, rows=rows)
    prices_a = {r['date']: r['close'] for r in filtered.get('601857.SH', {}).get('rows', [])}
    prices_h = {r['date']: r['close'] for r in filtered.get('00857.HK', {}).get('rows', [])}
    prices_brent = {r['date']: r['close'] for r in filtered.get('BRENT', {}).get('rows', [])}
    observed = sorted(set(prices_a) | set(prices_h) | set(prices_brent))
    visible_anns = [dict(a) for a in PETROCHINA_ANNOUNCEMENTS if a['published_on'] <= cutoff]

    listings_meta = {
        '601857.SH': {
            'code': '601857.SH',
            'field': 'a_stock',
            'name': '中国石油 A股 (601857.SH)',
            'unit': '元/股',
            'adjustment': '前复权收盘',
            'last_date': filtered['601857.SH']['rows'][-1]['date'] if '601857.SH' in filtered else None,
        },
        '00857.HK': {
            'code': '00857.HK',
            'field': 'h_stock',
            'name': '中国石油股份 H股 (00857.HK)',
            'unit': '港元/股',
            'adjustment': '前复权收盘',
            'last_date': filtered['00857.HK']['rows'][-1]['date'] if '00857.HK' in filtered else None,
        },
    }
    brent_meta = {
        'code': 'BRENT',
        'field': 'brent',
        'name': '布伦特原油期货连续',
        'unit': '美元/桶',
        'adjustment': '连续合约收盘',
        'session_cutoff_note': 'ICE伦敦23:00收盘后收录',
        'requested_through': effective_brent_cutoff,
        'last_date': filtered['BRENT']['rows'][-1]['date'] if 'BRENT' in filtered else None,
    }
    default_listing = code if code in listings_meta and filtered.get(code) else (
        '601857.SH' if '601857.SH' in filtered else ('00857.HK' if '00857.HK' in filtered else code)
    )
    sources = [
        {k: data.get(k) for k in ('code', 'name', 'source', 'source_url', 'adjustment', 'captured_at')}
        | {'last_date': data['rows'][-1]['date']}
        for data in filtered.values()
    ]
    base = {
        'pilot': 'petrochina_market_v1',
        'code': code,
        'method_version': PILOT_METHOD_VERSION,
        'captured_at': now_iso(),
        'requested_through': cutoff,
        'brent_through': effective_brent_cutoff,
        'errors': errors,
        'sources': sources,
        'cost': build_petrochina_cost(cutoff, company),
        'valuation': build_petrochina_valuation(company, cutoff, edition_loader=edition_loader),
    }
    if not observed:
        return dict(
            base,
            status='unavailable',
            reason='截至所选观察日期暂未取得中国石油股价或布伦特油价日线',
            as_of=None,
            trend={
                'status': 'unavailable',
                'reason': '暂未取得股价或布伦特油价日线',
                'default_listing': default_listing,
                'listings': listings_meta,
                'brent': brent_meta,
                'ah_premium_included': False,
                'chart': [],
                'announcements': visible_anns,
            },
        )
    window_observed = observed[-260:]
    calendar = _weekday_calendar(window_observed[0], window_observed[-1], set(window_observed))
    chart = [
        {
            'date': day,
            'a_stock': prices_a.get(day),
            'h_stock': prices_h.get(day),
            'brent': prices_brent.get(day),
        }
        for day in calendar
    ]
    for ann in visible_anns:
        ann['plot_date'] = next(
            (d for d in calendar if d >= ann['published_on']),
            None,
        ) if ann['published_on'] >= calendar[0] and ann['published_on'] <= calendar[-1] else None
    as_of = window_observed[-1]
    return dict(
        base,
        status='ready',
        as_of=as_of,
        lag_days=(date.fromisoformat(cutoff) - date.fromisoformat(as_of)).days,
        trend={
            'status': 'ready',
            'default_listing': default_listing,
            'listings': listings_meta,
            'brent': brent_meta,
            'ah_premium_included': False,
            'chart': chart,
            'announcements': visible_anns,
        },
    )


class MarketService:
    def __init__(self, directory):
        self.root_directory = Path(directory)
        self.db_path = self.root_directory / 'research.db'
        self.directory = self.root_directory / 'market_context'
        self.quotes = QuoteCache(self.directory)
        self.executor = ThreadPoolExecutor(max_workers=2, thread_name_prefix='market-context')
        self.lock = Lock()
        self.jobs = {}
        self.failures = {}

    def _load_edition_data(self, cid, edition_id):
        if not cid or not edition_id or not self.db_path.is_file():
            return None
        try:
            with sqlite3.connect(self.db_path) as conn:
                row = conn.execute(
                    'SELECT data FROM book_editions WHERE company_id=? AND id=?',
                    (cid, edition_id),
                ).fetchone()
            return json.loads(row[0]) if row else None
        except (sqlite3.Error, ValueError, TypeError):
            return None

    def profile(self, code):
        registry = json.loads(PROFILE_FILE.read_text(encoding='utf-8'))
        fallback = {'label': '同行待选择', 'scope': '业务可比名单尚未建立，先展示市场与市值风格。',
                    'peers': [], 'excluded': []}
        return registry['profiles'].get(code, fallback), registry['version']

    def refresh(self, company):
        code = canonical(company['code'])
        cutoff = completed_date()
        if code in PETROCHINA_CODES:
            brent_cutoff = min(cutoff, brent_completed_date())
            instruments = [
                {'code': '601857.SH', 'cutoff': cutoff},
                {'code': '00857.HK', 'cutoff': cutoff},
                dict(BRENT_INSTRUMENT, cutoff=brent_cutoff),
            ]
            series, errors = self.quotes.collect(instruments, cutoff)
            result = build_petrochina_pilot(
                code, series, errors, cutoff, company=company,
                brent_cutoff=brent_cutoff, edition_loader=self._load_edition_data,
            )
            write_json(self.directory / 'panels' / (code+'.json'), result)
            return result
        profile, version = self.profile(code)
        market = 'HK' if code.endswith('.HK') else 'CN'
        instruments = [{'code': code}] + [{'code': peer['code']} for peer in profile['peers']]
        instruments += [{'code': key, 'name': name, 'secid': secid} for key, name, secid in BENCHMARKS[market]]
        if profile.get('sector_history') == 'property':
            from sector_history import registry
            instruments += [{'code':m['code']} for m in registry()['members']]
        series, errors = self.quotes.collect(instruments, cutoff)
        result = build_context(code, profile, series, errors, cutoff, version)
        write_json(self.directory / 'panels' / (code+'.json'), result)
        return result

    def _run(self, company):
        code = canonical(company['code'])
        try:
            self.refresh(company)
            with self.lock:
                self.failures.pop(code, None)
        except Exception as error:
            with self.lock:
                self.failures[code] = {'message': str(error), 'at': now_iso()}

    def response(self, company, force=False, as_of=None):
        requested_as_of = validate_cutoff_date(as_of)
        try:
            code = canonical(company['code'])
        except ValueError as error:
            return {'status': 'unsupported', 'reason': str(error), 'refreshing': False}
        result = read_json(self.directory / 'panels' / (code+'.json'))
        if code in PETROCHINA_CODES:
            live_cutoff = completed_date()
            live_brent_cutoff = min(live_cutoff, brent_completed_date())
            outdated = bool(
                result and (
                    result.get('method_version') != PILOT_METHOD_VERSION
                    or result.get('requested_through') != live_cutoff
                    or result.get('brent_through') != live_brent_cutoff
                )
            )
            valid_cached = result if (result and not outdated) else None
            elapsed = (datetime.now(timezone.utc)-datetime.fromisoformat(valid_cached['captured_at'])).total_seconds() if valid_cached else math.inf
            with self.lock:
                job = self.jobs.get(code)
                failure = self.failures.get(code)
                recently_failed = failure and (datetime.now(timezone.utc)-datetime.fromisoformat(failure['at'])).total_seconds() < 300
                if (force or not recently_failed and (elapsed > 3600 or not valid_cached)) and (job is None or job.done()):
                    job = self.executor.submit(self._run, dict(company))
                    self.jobs[code] = job
                refreshing = bool(job and not job.done())
            cutoff = min(requested_as_of, live_cutoff) if requested_as_of else live_cutoff
            brent_cutoff = min(cutoff, live_brent_cutoff)
            if requested_as_of or not valid_cached:
                cached_series = {}
                for key in ('601857.SH', '00857.HK', 'BRENT'):
                    key_cutoff = brent_cutoff if key == 'BRENT' else cutoff
                    sliced = self.quotes.cached_through(key, key_cutoff)
                    if sliced:
                        cached_series[key] = sliced
                if cached_series or requested_as_of:
                    response = build_petrochina_pilot(
                        code, cached_series, (valid_cached or {}).get('errors', []), cutoff,
                        company=company, brent_cutoff=brent_cutoff, edition_loader=self._load_edition_data,
                    )
                else:
                    response = {
                        'pilot': 'petrochina_market_v1',
                        'status': 'pending',
                        'code': code,
                        'requested_through': cutoff,
                        'brent_through': brent_cutoff,
                        'errors': [],
                        'sources': [],
                        'cost': build_petrochina_cost(cutoff, company),
                        'valuation': build_petrochina_valuation(company, cutoff, edition_loader=self._load_edition_data),
                        'trend': {
                            'status': 'pending',
                            'default_listing': code,
                            'listings': {},
                            'brent': {
                                'code': 'BRENT',
                                'name': '布伦特原油期货连续',
                                'unit': '美元/桶',
                                'requested_through': brent_cutoff,
                            },
                            'ah_premium_included': False,
                            'chart': [],
                            'announcements': [dict(a) for a in PETROCHINA_ANNOUNCEMENTS if a['published_on'] <= cutoff],
                        },
                    }
            else:
                response = dict(valid_cached)
                response['cost'] = build_petrochina_cost(cutoff, company)
                response['valuation'] = build_petrochina_valuation(company, cutoff, edition_loader=self._load_edition_data)
            response['custom_cutoff'] = bool(requested_as_of)
            response['refreshing'] = refreshing
            response['refresh_error'] = failure['message'] if failure else None
            response['cache_age_hours'] = round(elapsed/3600, 1) if valid_cached else None
            return response
        _, profile_version = self.profile(code)
        outdated = result and (result.get('method_version') != METHOD_VERSION or result.get('profile_version') != profile_version)
        elapsed = (datetime.now(timezone.utc)-datetime.fromisoformat(result['captured_at'])).total_seconds() if result else math.inf
        with self.lock:
            job = self.jobs.get(code)
            failure = self.failures.get(code)
            recently_failed = failure and (datetime.now(timezone.utc)-datetime.fromisoformat(failure['at'])).total_seconds() < 300
            if (force or not recently_failed and (elapsed > 3600 or not result or outdated)) and (job is None or job.done()):
                job = self.executor.submit(self._run, dict(company))
                self.jobs[code] = job
            refreshing = bool(job and not job.done())
        response = dict(result or {'status': 'pending', 'code': code})
        response['refreshing'] = refreshing
        response['refresh_error'] = failure['message'] if failure else None
        response['cache_age_hours'] = round(elapsed/3600, 1) if result else None
        return response

    def close(self):
        self.executor.shutdown(wait=False, cancel_futures=True)
