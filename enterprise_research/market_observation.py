"""Shared market observations for issuer-specific inputs and fixed book editions."""

from datetime import date, timedelta
import re

from market_data import completed_date, read_json
from market_context import build_petrochina_cost, build_petrochina_valuation
from model_books import read_edition
from market_observation_update import B00Y_ID

PILOTS = {
    '600690.SH': 'haier',
    '06690.HK': 'haier',
    '690D.DE': 'haier',
    '601857.SH': 'petrochina',
    '00857.HK': 'petrochina',
}

HAIER_Q3 = 'https://smart-home.haier.com/media/21vfayr1/e_32014_ad-2-haier-smart-home-_ess.pdf'
HAIER_TENDER_RESULT = 'https://static.cninfo.com.cn/finalpage/2026-10-02/1225593764.PDF#page=6'
HAIER_RESULTS = 'https://www.eqs-news.com/news/corporate/haier-smart-home-reports-q3-2026-results/94e19f5b-b17c-4490-beab-5714973259ce_en'
HAIER_TENDER = 'https://live.deutsche-boerse.com/news/EQS-News-Haier-Smart-Home-Co-Ltd-Launches-Voluntary-Public-Share-Buy-back-Offer-for-up-to-81044512-D-Shares-at-EUR-187-e228f4a5-a03d-4dbf-b908-2fcd0204876b'
HAIER_SHARES = 'https://cdn.financialreports.eu/financialreports/media/filings/56923/2026/RNS/56923_rns_2026-11-02_92d195b3-71c8-49fc-bead-c65c6d88909f.pdf#page=9'
PETRO_RESULTS = 'https://www1.hkexnews.hk/listedco/listconews/sehk/2026/0830/2026083000017.pdf#page=17'
PETRO_INTERIM = 'https://www1.hkexnews.hk/listedco/listconews/sehk/2026/0918/2026091800441.pdf#page=25'


def event(day, label, url, **details):
    return {'date': day, 'label': label, 'url': url, **details}


def series(key, label, unit, color):
    return {'key': key, 'label': label, 'unit': unit, 'color': color}


def mode(key, label, *lanes, normalize=False):
    return {'key': key, 'label': label, 'lanes': lanes, 'normalize': normalize}


def lane(*items, bars=False):
    return {'items': items, 'bars': bars}


A_HAIER = series('600690.SH', 'A 股', '元/股', 'stock')
H_HAIER = series('06690.HK', 'H 股', '港元/股', 'h')
D_HAIER = series('690D.DE', 'D 股 · Xetra', '欧元/股', 'd')
A_PETRO = series('601857.SH', 'A 股', '元/股', 'stock')
H_PETRO = series('00857.HK', 'H 股', '港元/股', 'h')
BRENT = series('B00Y', '布伦特原油当月连续（B00Y）', '美元/桶', 'oil')

SPECS = {
    'haier': {
        'inputs': ('600690.SH', '06690.HK', '690D.DE', 'EURCNY', 'HKDCNY'),
        'modes': (
            mode('d', 'D 股原币', lane(D_HAIER), lane(series('d_volume', 'Xetra 成交量', '股', 'd'), bars=True)),
            mode('cny', 'A/H/D 折人民币', lane(
                A_HAIER, series('h_cny', 'H 股折人民币', '元/股', 'h'),
                series('d_cny', 'D 股折人民币', '元/股', 'd')),
                lane(series('h_discount', 'H/A 折价', '%', 'h'), series('d_discount', 'D/A 折价', '%', 'd'))),
            mode('fx', 'D 股与汇率分解', lane(series('690D.DE', 'D 股欧元价格', '指数', 'd'),
                 series('d_cny', 'D 股人民币价格', '指数', 'stock'),
                 series('EURCNY', '欧元兑人民币', '指数', 'h')), normalize=True),
            mode('a', 'A 股原币', lane(A_HAIER)),
            mode('h', 'H 股原币', lane(H_HAIER)),
        ),
        'events': (
            event('2026-09-02', 'D 股要约启动公告 · €1.87', HAIER_TENDER,
                  start='2026-09-04', end='2026-09-29', offer=1.87, offer_mode='d'),
            event('2026-10-02', '披露要约购回 79,392,362 股，拟注销', HAIER_TENDER_RESULT),
            event('2026-10-29', '发布三季报', HAIER_Q3),
            event('2026-11-02', '10 月股份月报 · 两批 D 股购回仍待注销', HAIER_SHARES),
        ),
        'cards': (
            {'title': '终端需求', 'period': '2026 年第三季度', 'published': '2026-10-29',
             'metrics': [('国内家电零售额同比', '−10%'), ('北美家电出货量同比', '约 −4%')],
             'note': '国内为奥维云网零售额，北美为 AHAM 出货量，各自对照上年同期。',
             'sources': [('三季报', HAIER_Q3, '2026-10-29')]},
            {'title': '国内份额与集团毛利', 'period': '2026 年前三季度', 'published': '2026-10-29',
             'metrics': [('国内线上零售额份额', '20.6%（+2.9 个百分点）'),
                         ('国内线下零售额份额', '25.0%（+1.7 个百分点）'),
                         ('集团毛利率', '27.2%（同比基本持平）')],
             'note': '份额、毛利率和需求分别观察；利润变化还受售价、成本、区域组合及套保影响。',
             'sources': [('业绩公告', HAIER_RESULTS, '2026-10-29'), ('三季报', HAIER_Q3, '2026-10-29')]},
            {'title': '汇率对集团现金余额的影响', 'period': '2026 年前三季度与上年同期', 'published': '2026-10-29',
             'metrics': [('2025 年前三季度', '+2.38 亿元'), ('2026 年前三季度', '−10.34 亿元')],
             'note': '取合并现金流量表的汇率变动影响。三季报另指出第三季度汇兑损失同比增加，利润表端应单独核对。',
             'sources': [('三季报 · 合并现金流量表', HAIER_Q3, '2026-10-29')]},
        ),
        'edition': {
            'title': '海尔智家 · Codex 企业书 · haier-book-20261110-v2',
            'source_version': 'haier-sources-20261110-v4', 'date': '2026-11-10',
            'cash_yi': 102, 'summary': '主例为需求低位稳定下的普通股正常经济现金。10% 条件部分 EPV 约 10.81 元/股，仍有金融覆盖、GE 和未计损失的边界。',
        },
    },
    'petrochina': {
        'inputs': ('601857.SH', '00857.HK', 'B00Y'),
        'modes': (mode('a', 'A 股与布伦特', lane(A_PETRO), lane(BRENT)),
                  mode('h', 'H 股与布伦特', lane(H_PETRO), lane(BRENT))),
        'events': (
            event('2026-08-30', '披露中期业绩（港股 18:07）', PETRO_RESULTS, plot_on='2026-08-31'),
            event('2026-09-18', '刊发成册中报（港股 16:37）', PETRO_INTERIM, plot_on='2026-09-21'),
            event('2026-10-28', '披露三季报（港股 19:47）',
                  'https://www1.hkexnews.hk/listedco/listconews/sehk/2026/1028/2026102801189.pdf', plot_on='2026-10-29'),
        ),
        'cards': (
            {'title': '单位油气操作成本', 'period': '2026 年上半年与上年同期', 'published': '2026-08-30',
             'metrics': [('2025 年上半年', '10.14 美元/桶'), ('2026 年上半年', '10.68 美元/桶'), ('同比', '+5.3%')],
             'note': '中报列出汇率及基本运行费影响。该指标用于跟踪上游操作成本，完整盈亏还涉及其他费用、税费与资本支出。',
             'sources': [('中期业绩公告 · 第 17 页', PETRO_RESULTS, '2026-08-30'),
                         ('成册中报 · 第 25 页', PETRO_INTERIM, '2026-09-18')]},
        ),
        'edition': {
            'source_version': 'petrochina-sources-20261115-v1', 'date': '2026-11-13',
            'cash_yi': 1150, 'summary': '按 2026-11-13 收盘、10% 股权回报率与个人税前口径，H 股隐含年度普通股现金要求约 1,618 亿元，A 股约 2,268 亿元。',
        },
    },
}


def observation_key(company):
    return PILOTS.get(company['code'].strip().upper())


def observation_cutoff(as_of):
    if not as_of:
        return completed_date()
    if not re.fullmatch(r'\d{4}-\d{2}-\d{2}', as_of):
        raise ValueError('历史截止日须为 YYYY-MM-DD')
    return min(date.fromisoformat(as_of).isoformat(), completed_date())


def official_snapshot(store, company, key, cutoff):
    spec = SPECS[key]['edition']
    formal = {}
    if key == 'petrochina':
        formal = build_petrochina_valuation(company, cutoff,
                    edition_loader=lambda cid, eid: read_edition(store, cid, eid))
        summary = next((item for item in company['book_editions']
                        if item['id'] == formal.get('edition_id')), None)
    else:
        summary = next((item for item in company['book_editions']
                        if item.get('title') == spec['title']
                        and item.get('source_version') == spec['source_version']
                        and item.get('information_cutoff') == spec['date']
                        and item.get('model', {}).get('name') == 'Codex'), None)
    if not summary:
        return {'reason': '尚未定位到该公司已核对的正式版估值。'}
    published = summary.get('completed_at', spec['date'])[:10]
    if cutoff < max(spec['date'], published):
        return {'reason': '所选日期早于正式估值公开，保留当时的信息边界。'}
    result = {
        'date': spec['date'], 'published_on': published, 'cash_yi': spec['cash_yi'], 'cash': f"约 {spec['cash_yi']:,} 亿元/年", 'summary': spec['summary'],
        'url': f"#/company/{company['id']}/editions?edition={summary['id']}&view=valuation",
    }
    if formal.get('figure_url'):
        result['figure_url'] = formal['figure_url']
    return result


def calendar(observed):
    if not observed:
        return
    current = date.fromisoformat(min(observed))
    end = date.fromisoformat(max(observed))
    while current <= end:
        iso = current.isoformat()
        if current.weekday() < 5 or iso in observed:
            yield iso
        current += timedelta(days=1)


def align_inputs(inputs, cutoff):
    by_date = {
        key: {row['date']: row for row in source['rows'] if row['date'] <= cutoff}
        for key, source in inputs.items()
    }
    observed = set().union(*(by_day.keys() for by_day in by_date.values()))
    chart = []
    for day in calendar(observed):
        bars = {key: rows.get(day, {}) for key, rows in by_date.items()}
        values = {key: bar.get('close') for key, bar in bars.items()}
        if '690D.DE' in by_date or '06690.HK' in by_date or '600690.SH' in by_date:
            values['d_volume'] = bars.get('690D.DE', {}).get('volume')
            for label, code, fx_code in (('d', '690D.DE', 'EURCNY'), ('h', '06690.HK', 'HKDCNY')):
                price, fx = values.get(code), values.get(fx_code)
                converted = price * fx if price and fx and bars[code].get('volume') != 0 else None
                values[f'{label}_cny'] = converted
                a = values.get('600690.SH')
                values[f'{label}_discount'] = 100 * (converted / a - 1) if converted and a else None
        chart.append({'date': day, 'values': values})
    return chart


def haier_price_snapshot(chart, cutoff):
    labels = [('A 股', '600690.SH'), ('H 股', 'h_cny'), ('D 股', 'd_cny')]
    row = next((row for row in reversed(chart) if '2026-11-16' <= row['date'] <= cutoff
                and all(row['values'].get(code) is not None for _, code in labels)), None)
    if not row:
        return None
    comparison_day, values = row['date'], row['values']
    share_count = 9_298_538_164
    metrics = [
        {'label': label, 'price_cny': values[code], 'cash_yi': values[code] * share_count * .1 / 1e8}
        for label, code in labels if values.get(code)
    ]
    return {'date': comparison_day, 'shares': share_count, 'shares_on': '2026-10-31',
            'share_url': HAIER_SHARES, 'metrics': metrics} if metrics else None


def response(store, company, as_of=None):
    key = observation_key(company)
    cutoff = observation_cutoff(as_of)
    spec = SPECS[key]
    data_dir = store.directory / 'market_observation'
    inputs = {}
    coverage = []
    for code in spec['inputs']:
        item = read_json(data_dir / f'{code}.json')
        if code == 'B00Y' and item and item.get('series_id') != B00Y_ID:
            item = None
        if item:
            inputs[code] = item
        days = [row['date'] for row in item['rows'] if row['date'] <= cutoff] if item else []
        coverage.append({
            'code': code, 'label': item['label'] if item else code, 'source': item['source'] if item else None,
            'url': item['url'] if item and days else None, 'start': min(days) if days else None,
            'end': max(days) if days else None, 'count': len(days),
        })
    chart = align_inputs(inputs, cutoff)
    cards = [
        dict(card, sources=[source for source in card['sources'] if source[2] <= cutoff])
        for card in spec['cards'] if card['published'] <= cutoff
    ]
    if key == 'petrochina' and cards:
        cost = build_petrochina_cost(cutoff, company)
        cards[0]['sources'] = [(source['title'], source['url']) for source in cost['sources']]
        if cost['local_source_version']:
            cards[0]['sources'].append(('本库固定资料 · 中报第 25 页',
                f"/api/companies/{company['id']}/data/versions/{cost['local_source_version']}/documents/h12026/original#page=25"))
    snapshot = official_snapshot(store, company, key, cutoff)
    return {
        'observation': key, 'company': company['name'], 'cutoff': cutoff, 'chart': chart,
        'modes': spec['modes'], 'coverage': coverage, 'cards': cards, 'valuation': snapshot,
        'events': [item for item in spec['events'] if item['date'] <= cutoff],
        'price_snapshot': haier_price_snapshot(chart, cutoff) if key == 'haier' and snapshot.get('url') else None,
    }
