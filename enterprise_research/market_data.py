"""Public daily quotes for the company environment panel. Standard library only."""
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
import json
import math
import sys
from ipaddress import IPv4Address
from subprocess import SubprocessError, run
from pathlib import Path
import re
import tempfile
from threading import Lock
from urllib.parse import urlencode
from urllib.request import Request, urlopen
from zoneinfo import ZoneInfo


HONG_KONG = ZoneInfo('Asia/Hong_Kong')
LONDON = ZoneInfo('Europe/London')
B00Y_HOST = 'push2his.eastmoney.com'
B00Y_SITE = 'https://quote.eastmoney.com/globalfuture/B00Y.html'
B00Y_DNS = ('https://dns.alidns.com/resolve', 'https://dns.google/resolve')
HISTORY_LIMIT = 1500
BENCHMARKS = {
    'HK': [('HSCI', '恒生综合指数', '124.HSCI'),
           ('HSSI', '恒生综合小型股', '124.HSSI'),
           ('HSLI', '恒生综合大型股', '124.HSLI')],
    'CN': [('CSI300', '沪深300', '1.000300'),
           ('CSI500', '中证500', '1.000905'),
           ('SSE50', '上证50', '1.000016')],
}


def now_iso():
    return datetime.now(timezone.utc).isoformat(timespec='seconds')


def completed_date(now=None):
    """Exclude an unfinished session, including HK closing auction."""
    current = (now or datetime.now(timezone.utc)).astimezone(HONG_KONG)
    day = current.date()
    if current.hour < 17:
        day -= timedelta(days=1)
    while day.weekday() >= 5:
        day -= timedelta(days=1)
    return day.isoformat()

def brent_completed_date(now=None):
    """Exclude an unfinished ICE Brent session (01:00-23:00 Europe/London, plus 15m close buffer)."""
    current = (now or datetime.now(timezone.utc)).astimezone(LONDON)
    day = current.date()
    if (current.hour, current.minute) < (23, 15):
        day -= timedelta(days=1)
    while day.weekday() >= 5:
        day -= timedelta(days=1)
    return day.isoformat()



def symbol(code):
    match = re.fullmatch(r'(\d{1,6})\.(HK|SH|SZ)', str(code).upper())
    if not match:
        raise ValueError('目前支持带 .HK、.SH 或 .SZ 后缀的股票代码')
    digits, market = match.groups()
    if market == 'HK' and len(digits) <= 5:
        return 'hk' + digits.zfill(5)
    if market in ('SH', 'SZ') and len(digits) == 6:
        return market.lower() + digits
    raise ValueError('股票代码长度与市场不符')


def canonical(code):
    value = symbol(code)
    return value[2:] + '.' + value[:2].upper()


def write_json(path, data):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile('w', encoding='utf-8', dir=path.parent, delete=False) as handle:
        json.dump(data, handle, ensure_ascii=False, allow_nan=False)
        temporary = Path(handle.name)
    temporary.replace(path)


def read_json(path):
    try:
        return json.loads(Path(path).read_text(encoding='utf-8'))
    except FileNotFoundError:
        return None


def get_json(url):
    request = Request(url, headers={'User-Agent': 'Mozilla/5.0'})
    with urlopen(request, timeout=18) as response:
        return json.load(response)


def b00y_over_physical_route(url):
    table = run(['/usr/sbin/netstat', '-rn', '-f', 'inet'], capture_output=True,
                text=True, check=True, timeout=4).stdout
    interface = next((route[3] for route in map(str.split, table.splitlines())
                      if len(route) >= 4 and route[0] == 'default' and route[3].startswith('en')), None)
    if not interface:
        raise OSError('未找到 macOS 以太网或 Wi-Fi 的默认路由')
    # A proxy TUN can replace system DNS with a synthetic address and catch raw-IP requests.
    # Resolve the same official host over HTTPS, then bind only this transfer to the physical interface.
    error = '公开 DNS 未返回东财源站地址'
    tried = set()
    for resolver in B00Y_DNS:
        try:
            answer = get_json(resolver + '?' + urlencode({'name': B00Y_HOST, 'type': 'A'}))
            addresses = [IPv4Address(row['data']) for row in answer.get('Answer', [])
                         if row['type'] == 1]
        except (OSError, ValueError, KeyError) as cause:
            error = str(cause)
            continue
        for address in addresses:
            if not address.is_global or address in tried:
                continue
            tried.add(address)
            response = run(['/usr/bin/curl', '--interface', f'if!{interface}', '--noproxy', '*',
                            '--resolve', f'{B00Y_HOST}:443:{address}', '-fsS', '--connect-timeout', '5',
                            '--max-time', '8', '-A', 'Mozilla/5.0', '-e', B00Y_SITE, url],
                           capture_output=True, text=True, timeout=10)
            if response.returncode == 0:
                return json.loads(response.stdout)
            error = response.stderr.strip()
    raise OSError(error)


def get_b00y_json(url):
    """Return B00Y JSON and its successful route, including macOS TUN recovery."""
    try:
        return get_json(url), 'system'
    except OSError as original:
        if sys.platform != 'darwin':
            raise
        try:
            return b00y_over_physical_route(url), 'macos-physical-interface'
        except (OSError, ValueError, SubprocessError) as alternate:
            raise OSError(f'东财常规路由失败（{original}），物理网卡也未取得日线（{alternate}）') from alternate


def checked_rows(rows):
    if not rows:
        raise ValueError('行情源未返回日线')
    dates = [row['date'] for row in rows]
    if dates != sorted(set(dates)):
        raise ValueError('行情日期重复或未排序')
    for row in rows:
        datetime.strptime(row['date'], '%Y-%m-%d')
        if not math.isfinite(row['close']) or row['close'] <= 0:
            raise ValueError('行情收盘价缺失或无效')
        if row.get('volume') is not None and (not math.isfinite(row['volume']) or row['volume'] < 0):
            raise ValueError('行情成交量无效')
    return rows


def parse_stock(payload, code, url, cutoff):
    key = symbol(code)
    body = payload.get('data')
    if not isinstance(body, dict):
        raise ValueError('行情源未返回有效证券日线对象')
    data = body.get(key) or {}
    raw = data.get('qfqday')
    # A raw fallback can misclassify cash dividends as a sell-off.
    if not raw:
        raise ValueError('前复权序列缺失，等待可比行情')
    rows = checked_rows([
        {'date': row[0], 'close': float(row[2]), 'volume': float(row[5])}
        for row in raw if row[0] <= cutoff
    ])
    quote = data.get('qt', {}).get(key, [])
    name = quote[1] if len(quote) > 2 else code
    if len(quote) > 2 and str(quote[2]).zfill(len(key)-2) != key[2:]:
        raise ValueError('行情返回的证券代码不匹配')
    cap = None
    if len(quote) > 46 and quote[45]:
        try:
            cap = float(quote[45]) * 1e8
        except (TypeError, ValueError):
            pass
    return {'code': code, 'name': name, 'source': '腾讯前复权日线', 'source_url': url,
            'adjustment': 'QFQ', 'currency': 'HKD' if key.startswith('hk') else 'CNY',
            'float_cap': cap, 'cap_as_of': str(quote[30]) if len(quote) > 30 else None,
            'rows': rows, 'captured_at': now_iso()}


def parse_index(payload, code, name, secid, url, cutoff, source='东方财富指数日线',
                adjustment='PRICE_INDEX', currency=None, unit=None):
    data = payload.get('data') or {}
    if str(data.get('code') or '').upper() != secid.split('.')[1].upper():
        raise ValueError('指数代码与请求不符')
    rows = []
    for raw in data.get('klines', []):
        fields = raw.split(',')
        if fields[0] <= cutoff:
            rows.append({'date': fields[0], 'close': float(fields[2]), 'volume': None})
    result = {'code': code, 'name': name, 'provider_name': data.get('name'),
            'source': source, 'source_url': url, 'adjustment': adjustment,
            'rows': checked_rows(rows), 'captured_at': now_iso()}
    if currency:
        result['currency'] = currency
    if unit:
        result['unit'] = unit
    return result


def parse_a_stock(payload, code, secid, url, cutoff):
    """Eastmoney adjusted equity bars; also the explicit HK fallback."""
    data = payload.get('data') or {}
    if str(data.get('code') or '').upper() != secid.split('.')[1].upper():
        raise ValueError('股票代码与请求不符')
    rows = []
    for raw in data.get('klines', []):
        fields = raw.split(',')
        if fields[0] <= cutoff:
            rows.append({'date': fields[0], 'close': float(fields[2]),
                         'volume': float(fields[5]), 'amount': float(fields[6])})
    return {'code': code, 'name': data.get('name') or code,
            'source': '东方财富前复权日线', 'source_url': url, 'adjustment': 'QFQ',
            'currency': 'HKD' if code.endswith('.HK') else 'CNY', 'float_cap': None, 'cap_as_of': None,
            'rows': checked_rows(rows), 'captured_at': now_iso()}


class QuoteCache:
    def __init__(self, directory):
        self.directory = Path(directory) / 'quotes'
        self._lock = Lock()
        self._locks = {}

    def fetch(self, instrument, cutoff):
        cutoff = instrument.get('cutoff') or cutoff
        code = instrument['code']
        with self._lock:
            lock = self._locks.setdefault(code, Lock())
        with lock:
            path = self.directory / (code + '.json')
            cached = read_json(path)
            current = datetime.now(timezone.utc)
            # Short TTL deduplicates shared benchmarks across company requests.
            a_stock = code.endswith(('.SH', '.SZ'))
            current_provider = not a_stock or cached and cached.get('source') == '东方财富前复权日线'
            if cached and current_provider and cached.get('requested_bars', 0) >= HISTORY_LIMIT and cached.get('rows') and  cached['rows'][-1]['date'] == cutoff:
                age = current - datetime.fromisoformat(cached['captured_at'])
                if age.total_seconds() < 3600:
                    return cached, None
            try:
                if 'secid' in instrument or a_stock:
                    secid = instrument.get('secid') or ('1.' if code.endswith('.SH') else '0.')+code.split('.')[0]
                    query = urlencode({'secid': secid, 'klt': 101, 'fqt': 1 if a_stock else 0,
                                       'lmt': HISTORY_LIMIT, 'end': cutoff.replace('-', ''),
                                       'fields1': 'f1,f2,f3,f4,f5,f6',
                                       'fields2': 'f51,f52,f53,f54,f55,f56,f57'})
                    url = 'https://push2his.eastmoney.com/api/qt/stock/kline/get?' + query
                    payload = get_b00y_json(url)[0] if secid == '112.B00Y' else get_json(url)
                    result = (parse_a_stock(payload, code, secid, url, cutoff) if a_stock else
                              parse_index(payload, code, instrument['name'], secid, url, cutoff,
                                          source=instrument.get('source', '东方财富指数日线'),
                                          adjustment=instrument.get('adjustment', 'PRICE_INDEX'),
                                          currency=instrument.get('currency'),
                                          unit=instrument.get('unit')))
                else:
                    key = symbol(code)
                    endpoint = 'hkfqkline' if key.startswith('hk') else 'fqkline'
                    query = urlencode({'param': f'{key},day,,{cutoff},{HISTORY_LIMIT},qfq'})
                    url = f'https://web.ifzq.gtimg.cn/appstock/app/{endpoint}/get?' + query
                    try:
                        result = parse_stock(get_json(url), code, url, cutoff)
                    except (OSError, ValueError, TypeError, KeyError, IndexError):
                        # Some HK securities supply only unadjusted bars here.
                        # Request explicit fqt=1 elsewhere instead of relabelling them.
                        secid = '116.' + code.split('.')[0]
                        query = urlencode({'secid': secid, 'klt': 101, 'fqt': 1,
                                           'lmt': HISTORY_LIMIT, 'end': cutoff.replace('-', ''),
                                           'fields1': 'f1,f2,f3,f4,f5,f6',
                                           'fields2': 'f51,f52,f53,f54,f55,f56,f57'})
                        url = 'https://push2his.eastmoney.com/api/qt/stock/kline/get?' + query
                        result = parse_a_stock(get_json(url), code, secid, url, cutoff)
                result['requested_bars'] = HISTORY_LIMIT
                write_json(path, result)
                return result, None
            except (OSError, ValueError, TypeError, KeyError, IndexError) as error:
                if not cached:
                    return None, str(error)
                rows = [row for row in cached.get('rows', []) if row['date'] <= cutoff]
                return (dict(cached, rows=rows) if rows else None), str(error)

    def cached_through(self, code, cutoff):
        cached = read_json(self.directory / (code + '.json'))
        if not cached:
            return None
        rows = [row for row in cached.get('rows', []) if row['date'] <= cutoff]
        return dict(cached, rows=rows) if rows else None

    def collect(self, instruments, cutoff):
        unique = {item['code']: item for item in instruments}
        def fetch(item):
            data, error = self.fetch(item, item.get('cutoff') or cutoff)
            return item['code'], data, error
        with ThreadPoolExecutor(max_workers=4) as executor:
            results = list(executor.map(fetch, unique.values()))
        return ({code: data for code, data, _ in results if data},
                [{'code': code, 'error': error} for code, _, error in results if error])
