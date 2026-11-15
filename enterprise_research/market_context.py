"""Observed market context, with a prior-window factor model and visible peers."""
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime, timezone
import json
import math
from pathlib import Path
from statistics import mean, median, pstdev
from threading import Lock

from market_data import BENCHMARKS, QuoteCache, canonical, completed_date, now_iso, read_json, write_json


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


class MarketService:
    def __init__(self, directory):
        self.directory = Path(directory) / 'market_context'
        self.quotes = QuoteCache(self.directory)
        self.executor = ThreadPoolExecutor(max_workers=2, thread_name_prefix='market-context')
        self.lock = Lock()
        self.jobs = {}
        self.failures = {}

    def profile(self, code):
        registry = json.loads(PROFILE_FILE.read_text(encoding='utf-8'))
        fallback = {'label': '同行待选择', 'scope': '业务可比名单尚未建立，先展示市场与市值风格。',
                    'peers': [], 'excluded': []}
        return registry['profiles'].get(code, fallback), registry['version']

    def refresh(self, company):
        code = canonical(company['code'])
        profile, version = self.profile(code)
        market = 'HK' if code.endswith('.HK') else 'CN'
        instruments = [{'code': code}] + [{'code': peer['code']} for peer in profile['peers']]
        instruments += [{'code': key, 'name': name, 'secid': secid} for key, name, secid in BENCHMARKS[market]]
        if profile.get('sector_history') == 'property':
            from sector_history import registry
            instruments += [{'code':m['code']} for m in registry()['members']]
        cutoff = completed_date()
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

    def response(self, company, force=False):
        try:
            code = canonical(company['code'])
        except ValueError as error:
            return {'status': 'unsupported', 'reason': str(error), 'refreshing': False}
        result = read_json(self.directory / 'panels' / (code+'.json'))
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
