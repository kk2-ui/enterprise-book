"""Read as-published monthly retail and property statistics from the NBS release archive."""
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime, timedelta, timezone
from html.parser import HTMLParser
import math
import re
from subprocess import SubprocessError
import sys
from threading import Lock
from urllib.parse import urljoin
from urllib.request import Request, urlopen

from market_data import official_text_over_physical_route, read_json, write_json

BASE = 'https://www.stats.gov.cn/sj/zxfb/'
METRICS = {'appliances': '限额以上家用电器和音像器材类零售额', 'housing': '全国住宅竣工面积'}
archive_lock = Lock()


class ReleaseHTML(HTMLParser):
    def __init__(self, html):
        super().__init__()
        self.links = {}
        self.rows = []
        self.row = None
        self.cell = None
        self.title = ''
        self.published = ''
        self.feed(html)

    def handle_starttag(self, tag, attrs):
        attr = dict(attrs)
        if tag == 'a':
            url, title = attr.get('href', ''), attr.get('title', '') or ''
            match = re.fullmatch(r'\./(\d{6})/t(\d{8})_\d+\.html', url)
            if match:
                if '社会消费品零售总额' in title and '解读' not in title:
                    self.links[urljoin(BASE, url)] = 'appliances'
                if '全国房地产市场基本情况' in title:
                    self.links[urljoin(BASE, url)] = 'housing'
        elif tag == 'meta' and (attr.get('name') or '').lower() == 'articletitle':
            self.title = attr.get('content', '')
        elif tag == 'meta' and (attr.get('name') or '').lower() == 'pubdate':
            self.published = attr.get('content', '')[:10].replace('/', '-')
        elif tag == 'tr':
            self.row = []
        elif tag in ('td', 'th') and self.row is not None:
            self.cell = []

    def handle_data(self, text):
        if self.cell is not None:
            self.cell.append(text)

    def handle_endtag(self, tag):
        if tag in ('td', 'th') and self.cell is not None:
            self.row.append(''.join(''.join(self.cell).split()))
            self.cell = None
        elif tag == 'tr' and self.row is not None:
            self.rows.append(self.row)
            self.row = None


def release_point(html, metric, url):
    doc = ReleaseHTML(html)
    published = date.fromisoformat(doc.published)
    year = re.search(r'(20[0-9]{2})年', doc.title)
    month = re.search(r'([0-9]{1,2})月份?', doc.title)
    if not year and not month:
        raise ValueError('统计原文标题缺少报告期')
    # Annual releases use only the reporting year in their title.
    period = date(int(year[1]) if year else published.year, int(month[1]) if month else 12, 1).isoformat()[:7]
    for i, row in enumerate(doc.rows):
        if metric == 'appliances' and row and row[0] == '家用电器和音像器材类':
            # Rightmost pair is YTD amount and YTD YoY (Jan-Feb has only one pair).
            cells = row
        elif metric == 'housing' and row and '房屋竣工面积' in row[0] and i+1 < len(doc.rows):
            cells = doc.rows[i+1]
            if not cells or cells[0] not in ('其中：住宅', '其中:住宅', '住宅'):
                continue
        else:
            continue
        if len(cells) < 3 or not re.fullmatch(r'[+−-]?\d+(?:\.\d+)?', cells[-1]):
            continue
        value = float(cells[-1].replace('−', '-'))
        if math.isfinite(value):
            return dict(metric=metric, period=period, published=published.isoformat(), value=value, url=url)
    raise ValueError('统计局原表未找到指定指标的累计同比列')


def official_html(url):
    try:
        with urlopen(Request(url, headers={'User-Agent': 'Mozilla/5.0'}), timeout=6) as response:
            return response.read().decode('utf-8-sig')
    except OSError:
        if sys.platform != 'darwin':
            raise
        return official_text_over_physical_route(url, 'www.stats.gov.cn', BASE)


def archive(directory):
    path = directory / 'market_observation' / 'economic' / 'nbs.json'
    with archive_lock:
        stored = read_json(path) or {}
        now = datetime.now(timezone.utc)
        if stored.get('retry_after', '') > now.isoformat():
            return stored
        rows = dict(stored.get('rows', {}))
        # On first use collect about two years. Subsequent checks discover new releases
        # on the leading pages and retry individual documents that previously failed.
        missing_pages = stored.get('missing_pages', [])
        recent = stored.get('checked_on', '') >= (now.date() - timedelta(days=28)).isoformat()
        pages = sorted(set([*range(3 if rows and recent else 30), *missing_pages]))
        links = dict(stored.get('pending', {}))
        missing_pages = []
        errors = []

        def read_index(n):
            url = BASE if n == 0 else BASE + f'index_{n}.html'
            try:
                return ReleaseHTML(official_html(url)).links
            except (OSError, ValueError, SubprocessError) as error:
                return str(error)

        def read_release(item):
            url, metric = item
            try:
                return release_point(official_html(url), metric, url)
            except (OSError, ValueError, SubprocessError) as error:
                return str(error)

        with ThreadPoolExecutor(max_workers=5) as pool:
            for n, result in zip(pages, pool.map(read_index, pages)):
                if isinstance(result, str):
                    missing_pages.append(n)
                    errors.append(result)
                else:
                    links.update(result)
            pending = {url: key for url, key in links.items() if url not in rows}
            for url, result in zip(list(pending), pool.map(read_release, list(pending.items()))):
                if isinstance(result, dict):
                    rows[url] = result
                    del pending[url]
                else:
                    errors.append(result)
        status = (f'{len(errors)} 个目录或原表未能读取，将重试。' if errors else '')
        if not rows and not status:
            status = '发布目录暂未找到匹配的统计原表。'
        stored = dict(rows=rows, pending=pending, missing_pages=missing_pages, checked_on=now.date().isoformat(),
                      message=status, retry_after=(now + timedelta(hours=1 if status else 6)).isoformat())
        write_json(path, stored)
        return stored


def series(directory, metric, cutoff):
    data = archive(directory)
    start = (date.fromisoformat(cutoff) - timedelta(days=731)).isoformat()
    points = sorted((p for p in data['rows'].values() if p['metric'] == metric and start <= p['published'] <= cutoff),
                    key=lambda p: (p['published'], p['period']))
    return dict(label=METRICS[metric] + '累计同比', unit='%', points=points, message=data.get('message', ''))
