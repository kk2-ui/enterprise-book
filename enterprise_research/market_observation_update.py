"""Refresh issuer observations from completed sessions and published CFETS fixings."""

import argparse
import json
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, date, timedelta, timezone
from pathlib import Path
from threading import Event, Lock, Thread
from urllib.parse import urlencode
from urllib.request import Request, urlopen
from zoneinfo import ZoneInfo

from market_data import (B00Y_HOST, HONG_KONG, checked_rows, completed_date, get_b00y_json,
                         now_iso, read_json, symbol, write_json)

BERLIN = ZoneInfo('Europe/Berlin')
LONDON = ZoneInfo('Europe/London')
TENCENT = 'https://web.ifzq.gtimg.cn/appstock/app/fqkline/get'
XETRA_SITE = 'https://live.deutsche-boerse.com/equity/haier-smart-home-co-ltd/price-history/historical-prices-and-volumes'
YAHOO_XETRA = 'https://query1.finance.yahoo.com/v8/finance/chart/690D.DE'
CFETS_SITE = 'https://www.chinamoney.com.cn/chinese/bkccpr/index.html?tab=2'
CFETS_API = 'https://www.chinamoney.com.cn/ags/ms/cm-u-bk-ccpr/CcprHisNew'
B00Y_SITE = 'https://quote.eastmoney.com/globalfuture/B00Y.html'
B00Y_ID = 'eastmoney:112.B00Y'
B00Y_API = f'https://{B00Y_HOST}/api/qt/stock/kline/get'
STOCKS = {
    '600690.SH': ('海尔 A 股', 'day', '未复权收盘'),
    '06690.HK': ('海尔 H 股', 'day', '未复权收盘'),
    '601857.SH': ('中石油 A 股', 'qfqday', '前复权收盘'),
    '00857.HK': ('中石油 H 股', 'qfqday', '前复权收盘'),
}
CURRENCIES = {'EUR/CNY': 'EURCNY', 'HKD/CNY': 'HKDCNY'}


def fetch(url, referer, *, cfets=False):
    headers = {'User-Agent': 'Mozilla/5.0', 'Referer': referer}
    if cfets:
        headers.update({
            'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36',
            'Accept': 'application/json,text/html,*/*',
        })
    with urlopen(Request(url, headers=headers), timeout=12) as response:
        return json.load(response)


def session_cutoff(now, zone, hour, minute):
    local = now.astimezone(zone)
    day = local.date() - timedelta(days=(local.hour, local.minute) < (hour, minute))
    while day.weekday() >= 5:
        day -= timedelta(days=1)
    return day.isoformat()


def cutoffs(now=None):
    now = now or datetime.now(timezone.utc)
    return {
        'stocks': completed_date(now),
        'xetra': session_cutoff(now, BERLIN, 17, 50),
        'fx': session_cutoff(now, HONG_KONG, 9, 25),
        'B00Y': session_cutoff(now, LONDON, 23, 15),
    }


def start_day(cutoff, days):
    return (date.fromisoformat(cutoff) - timedelta(days=days)).isoformat()


def dataset(label, source, url, rows, **meta):
    return {'label': label, 'source': source, 'url': url, 'rows': checked_rows(rows),
            'checked_at': now_iso(), **meta}


def stock_series(code, cutoff):
    quote = symbol(code)
    label, field, method = STOCKS.get(code, (code, 'day', '未复权收盘'))
    flags = 'qfq' if field == 'qfqday' else ''
    query = urlencode({'param': f'{quote},day,{start_day(cutoff, 400)},{cutoff},640,{flags}'})
    endpoint = TENCENT.replace('/fqkline/', '/hkfqkline/') if code.endswith('.HK') and flags else TENCENT
    url = endpoint + '?' + query
    payload = fetch(url, 'https://gu.qq.com/')
    block = payload.get('data')
    prices = block.get(quote, {}).get(field) if isinstance(block, dict) else None
    if payload.get('code') != 0 or not prices:
        raise ValueError(f'腾讯未返回 {quote} 的 {field} 日线')
    rows = [{'date': row[0], 'close': float(row[2])} for row in prices if row[0] <= cutoff]
    if code in STOCKS and len(rows) < 240:
        raise ValueError('腾讯日线少于一年观察窗口所需的覆盖')
    if not rows:
        raise ValueError('所选截止日没有已收盘日线')
    return dataset(label, f'腾讯证券 · {method}', f'https://gu.qq.com/{quote}/gp', rows)


def xetra_series(cutoff, existing):
    query = urlencode({'range': '1y', 'interval': '1d', 'events': 'splits'})
    try:
        payload = fetch(YAHOO_XETRA + '?' + query, 'https://finance.yahoo.com/')
    except OSError:
        alternate = YAHOO_XETRA.replace('query1.', 'query2.')
        payload = fetch(alternate + '?' + query, 'https://finance.yahoo.com/')
    chart = payload['chart']['result'][0]
    meta = chart['meta']
    if (meta.get('symbol'), meta.get('fullExchangeName'), meta.get('currency')) != ('690D.DE', 'XETRA', 'EUR'):
        raise ValueError('D 股序列未匹配 690D.DE / XETRA / EUR')
    if chart.get('events', {}).get('splits'):
        raise ValueError('窗口内有拆股，需要使用 Xetra 未调整原始收盘')
    data = chart['indicators']['quote'][0]
    rows = []
    for stamp, close, volume in zip(chart['timestamp'], data['close'], data['volume'], strict=True):
        day = datetime.fromtimestamp(stamp, BERLIN).date().isoformat()
        if day <= cutoff and close is not None and volume is not None:
            rows.append({'date': day, 'close': round(close, 4), 'volume': volume})
    checked_rows(rows)
    reference_through = (existing or {}).get('exchange_reference_through')
    if existing:
        if not reference_through and existing['url'] == XETRA_SITE:
            reference_through = existing['rows'][-1]['date']
        # The verified exchange export remains authoritative for its closes and volumes.
        baseline = {row['date']: row for row in existing['rows']}
        overlapping = [r for r in rows if r['date'] in baseline]
        if not overlapping or any(abs(r['close'] - baseline[r['date']]['close']) > .00005 for r in overlapping):
            raise ValueError('Xetra 更新与已核价格缺少重叠或收盘价不一致')
        latest = existing['rows'][-1]['date']
        rows = existing['rows'] + [r for r in rows if r['date'] > latest]
    source = 'Yahoo XETRA · 未复权日线'
    if reference_through:
        source += f'；截至 {reference_through} 保留交易所已核价量'
    return dataset('海尔 D 股（Xetra）', source, 'https://finance.yahoo.com/quote/690D.DE/history/', rows,
                   exchange_url=XETRA_SITE, exchange_reference_through=reference_through)


def fx_series(cutoff, previous):
    start = start_day(cutoff, 30)
    old_ends = [item['rows'][-1]['date'] for item in previous.values() if item]
    if old_ends:
        start = min(start, start_day(min(old_ends), 7))
    if len(old_ends) < len(CURRENCIES):
        start = min(start, start_day(cutoff, 400))
    # CFETS limits this endpoint to the trailing year measured at request time.
    earliest = (datetime.now(HONG_KONG).date() - timedelta(days=364)).isoformat()
    start = max(start, earliest)
    params = {'startDate': start, 'endDate': cutoff, 'currency': ','.join(CURRENCIES),
              'pageNum': 1, 'pageSize': 10}
    rows_by_code = {code: [] for code in CURRENCIES.values()}
    while True:
        query = urlencode(params, safe='/,')
        payload = fetch(CFETS_API + '?' + query, CFETS_SITE, cfets=True)
        info = payload['data']
        if info.get('flagMessage'):
            raise ValueError('CFETS 查询未返回数据：' + info['flagMessage'])
        order = info['searchlist']
        if str(payload['head']['rep_code']) != '200' or set(order) != set(CURRENCIES):
            raise ValueError('中国货币网未返回所选两种中间价')
        for row in payload['records']:
            if not start <= row['date'] <= cutoff:
                continue
            for pair, value in zip(order, row['values'], strict=True):
                if value not in ('', None, '--'):
                    rows_by_code[CURRENCIES[pair]].append({'date': row['date'], 'close': float(value)})
        if params['pageNum'] >= int(info['pageTotal']):
            break
        params['pageNum'] += 1
    result = {}
    for pair, code in CURRENCIES.items():
        received = checked_rows(sorted(rows_by_code[code], key=lambda r: r['date']))
        before = previous.get(code)
        retained = [row for row in before['rows'] if row['date'] < received[0]['date']] if before else []
        result[code] = dataset(pair, '中国外汇交易中心 · 人民币汇率中间价', CFETS_SITE, retained + received)
    return result


def parse_b00y(payload, cutoff, url):
    item = payload.get('data') or {}
    if str(item.get('code')).upper() != 'B00Y' or str(item.get('market')) != '112':
        raise ValueError('东方财富响应未证实标的是 112.B00Y')
    rows = []
    for bar in item.get('klines', []):
        day, _, close, *_ = bar.split(',')
        if day <= cutoff:
            rows.append({'date': day, 'close': float(close)})
    return dataset('布伦特原油当月连续（B00Y）', '东方财富 · 112.B00Y 已收盘日线',
                   B00Y_SITE, rows, series_id=B00Y_ID, fetch_url=url)


def b00y_series(cutoff):
    query = urlencode({'secid': '112.B00Y', 'klt': 101, 'fqt': 0, 'lmt': 350,
                       'end': cutoff.replace('-', ''),
                       'fields1': 'f1,f2,f3,f4,f5,f6', 'fields2': 'f51,f52,f53,f54,f55,f56,f57'})
    url = B00Y_API + '?' + query
    payload, route = get_b00y_json(url)
    return parse_b00y(payload, cutoff, url) | {'network_route': route}


class ObservationUpdater:
    """One refresh at a time, with per-series writes and a persisted result."""

    def __init__(self, directory, schedule=False):
        self.directory = Path(directory) / 'market_observation'
        self.state_file = self.directory / 'refresh.json'
        self.started = Event()
        self.stopped = Event()
        self.lock = Lock()
        self.pool = ThreadPoolExecutor(max_workers=1, thread_name_prefix='market-observation')
        self.job = None
        if schedule:
            Thread(target=self._schedule, name='market-observation-schedule', daemon=True).start()

    def status(self):
        return (read_json(self.state_file) or {}) | {'running': self.started.is_set()}

    def start(self):
        with self.lock:
            if not self.job or self.job.done():
                self.started.set()
                self.job = self.pool.submit(self._run)
            return self.job

    def _schedule(self):
        while not self.stopped.is_set():
            state = self.status()
            retry = (state.get('errors') or state.get('lagging')) and state.get('finished_at') and (
                datetime.now(timezone.utc) - datetime.fromisoformat(state['finished_at'])
            ) >= timedelta(hours=1)
            if not state.get('running') and (state.get('cutoffs') != cutoffs() or retry):
                self.start()
            self.stopped.wait(60)

    def _run(self):
        target = cutoffs()
        assets = (*STOCKS, '690D.DE', *CURRENCIES.values(), 'B00Y')
        try:
            previous = {code: read_json(self.directory / f'{code}.json') for code in assets}
            if previous['B00Y'] and previous['B00Y'].get('series_id') != B00Y_ID:
                previous['B00Y'] = None
            errors, series = {}, {}
            with ThreadPoolExecutor(max_workers=5) as pool:
                tasks = {code: pool.submit(stock_series, code, target['stocks']) for code in STOCKS}
                tasks['690D.DE'] = pool.submit(xetra_series, target['xetra'], previous['690D.DE'])
                tasks['B00Y'] = pool.submit(b00y_series, target['B00Y'])
                tasks['CFETS'] = pool.submit(fx_series, target['fx'], {c: previous[c] for c in CURRENCIES.values()})
                for code, job in tasks.items():
                    try:
                        result = job.result()
                        series.update(result if code == 'CFETS' else {code: result})
                    except (OSError, ValueError, TypeError, KeyError, IndexError) as error:
                        errors[code] = str(error)
            updated, lagging = {}, {}
            for code, new in series.items():
                before = previous[code]
                end = new['rows'][-1]['date']
                if before and end < before['rows'][-1]['date']:
                    errors[code] = '行情源最新交易日早于本机已有数据'
                    continue
                write_json(self.directory / f'{code}.json', new)
                updated[code] = end
                expected = target['stocks' if code in STOCKS else 'xetra' if code == '690D.DE'
                                  else 'fx' if code in CURRENCIES.values() else 'B00Y']
                if end < expected:
                    lagging[code] = {'last': end, 'checked_through': expected}
            state = {'cutoffs': target, 'finished_at': now_iso(), 'updated': updated,
                     'errors': errors, 'lagging': lagging}
            write_json(self.state_file, state)
            return state
        finally:
            self.started.clear()

    def close(self):
        self.stopped.set()
        self.pool.shutdown(wait=False, cancel_futures=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--data-dir', type=Path, default=Path(__file__).parent / 'data')
    args = parser.parse_args()
    updater = ObservationUpdater(args.data_dir)
    try:
        print(json.dumps(updater.start().result(), ensure_ascii=False, indent=2))
    finally:
        updater.close()
