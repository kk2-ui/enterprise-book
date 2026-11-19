"""Presentation data for the Gemini-designed market observation charts."""
import json
from pathlib import Path

ANNUAL = 'https://static.cninfo.com.cn/finalpage/2026-03-27/1225038336.PDF#page=225'
COLORS = ['#1B4965', '#237A5B', '#B83A2D', '#9E6314']


def haier_regions():
    # 2025 年报 PDF 第 225 页，“地区信息 / 对外交易收入”，人民币元。
    totals = (302346783918.30, 286015294936.52)
    regions = [('中国大陆', 146554578270.93, 142201323244.53), ('美洲', 79870721756.60, 79528519635.18),
               ('欧洲', 38490745958.28, 32089184505.33)]
    other_current = totals[0] - sum(current for _, current, prior in regions)
    other_prior = totals[1] - sum(prior for _, current, prior in regions)
    regions.append(('其余地区', other_current, other_prior))
    return [dict(region=name, currency=f'{now / 1e8:,.1f} 亿元', sharePct=now / totals[0] * 100,
                 yoyText=f'同比 {(now/before-1)*100:+.1f}%', color=color)
            for (name, now, before), color in zip(regions, COLORS)]


def series(label, native, color, converted=None):
    return dict(label=label, nativeUnit=native, cnyUnit=converted or native, color=color)


def trend(key, data, days):
    haier = key == 'haier'
    codes = ['600690.SH', '06690.HK', '690D.DE'] if haier else ['601857.SH', '00857.HK', 'B00Y']
    fields = ['sh','hk','de'] if haier else ['a','h','brent']
    rows = []
    for item in data['chart']:
        values = item['values']
        row = dict(date=item['date'], **{f: values.get(code) for f, code in zip(fields, codes)})
        if haier:
            volume = values.get('d_volume')
            row.update(deVol=volume / 1000 if volume is not None else None, fxHkdCny=values.get('HKDCNY'),
                       fxEurCny=values.get('EURCNY'), hkCny=values.get('h_cny'), deCny=values.get('d_cny'))
        rows.append(row)
    # 中间价可以在交易所收盘前发布。尾日必须至少有一条真实行情，内部缺日完整保留。
    while rows and all(rows[-1][field] is None for field in fields):
        rows.pop()
    rows = rows[-days:]
    events = []
    for e in data['events']:
        pin_date = e.get('plot_on', e['date'])
        if rows and pin_date < rows[0]['date']:
            continue
        events.append(dict(id=f"e{len(events)+1}", pin=str(len(events)+1), date=pin_date,
                           title=e['label'], firstDisclosed=e['date'], sourceUrl=e['url'],
                           onChart=bool(rows and pin_date <= rows[-1]['date']),
                           impact=f"接受期 {e['start']} 至 {e['end']}" if e.get('start') else ''))
    if haier:
        meta = dict(sh=series('沪 A', 'CNY/股', COLORS[0]), hk=series('港 H', 'HKD/股', COLORS[1], '折人民币/股'),
                    de=series('德 D · Xetra', 'EUR/股', COLORS[2], '折人民币/股'),
                    deVol=dict(label='Xetra 成交量', unit='千股', color='#7D95A6'))
        modes = [('cny', '同日折人民币'), ('native', '三地原币')]
    else:
        meta = dict(a=series('中石油 A 股','元/股',COLORS[0]), h=series('中石油 H 股','港元/股',COLORS[1]),
                    brent=series('布伦特当月连续 · B00Y','美元/桶',COLORS[3]))
        modes = [('a', 'A 股与布伦特'), ('h', 'H 股与布伦特')]
    return dict(timeline=rows, events=events, seriesMeta=meta, defaultMode=modes[0][0],
                modes=[dict(id=k,label=v) for k,v in modes],
                layoutType='haier_tri_market' if haier else 'petrochina_split_brent',
                sectionTitle='三地价格与德国成交量' if haier else '中石油股价与布伦特原油',
                sectionSub=f'最近 {days} 个工作日。三地未复权收盘，以同日 CFETS 中间价折算人民币；德国成交量单列右轴。'
                if haier else f'最近 {days} 个工作日。A/H 前复权收盘与东方财富 112.B00Y 已收盘日线共用日期，各用原单位。')


def operating(key, data):
    haier = key == 'haier'
    cards = data['cards']
    panel = dict(facts=cards, visualItems=[], visualType='haier_fx_revenue' if haier else 'petrochina_upstream_cost',
               sectionTitle='收入来自哪里，市场需求如何变化' if haier else '上游每桶操作成本',
               sectionSub='年报列示收入地区，季度披露补充终端需求与市场份额。' if haier else '两个半年度使用同一口径，可直接比较。')
    if haier and data['cutoff'] >= '2026-03-27':
        panel.update(visualItems=haier_regions(), visualTitle='2025 年对外交易收入', visualUnit='占合计比重',
                   visualNote='按对外交易地区划分。其余地区为列示三地以外的合计。', source=ANNUAL)
    if not haier and cards:
        card = next((c for c in cards if c['title']=='单位油气操作成本'), None)
        if card:
            metrics = card['metrics']
            panel.update(visualTitle='同半年度单位油气操作成本', visualUnit='美元/桶',
                       visualNote='操作成本仅为上游成本的一部分。',
                       visualItems=[dict(label=period,period=period,value=float(val.split()[0]),badge=badge,color=color)
                                    for (period,val),badge,color in zip(metrics[:2],['同期基数',metrics[2][1]],COLORS[::2])])
    return panel


def valuation(key, data):
    snap = data['valuation']
    val = dict(sectionTitle='研究主例与价格隐含的现金要求', available=bool(snap.get('url')), venues=[],
               sectionSub='用相同的 10% 股权回报率，把各市场的价格换算成每年需要的普通股现金。')
    if not val['available']:
        return dict(val, reason=snap['reason'])
    if 'cash_yi' not in snap:
        return dict(val, linkedEdition=True, sectionTitle='本版现金与估值',
                    sectionSub='固定研究日期与适用条件见本版正文。', researchDate=snap['date'],
                    published=snap['published_on'], url=snap['url'], editionTitle=snap['title'])
    val.update(researchDate=snap['date'], published=snap['published_on'], requiredReturnPct=10,
               baseline=snap['cash_yi'], url=snap['url'], figureUrl=snap.get('figure_url'),
               assumptions=[snap['summary'], '各市场价格分别应用于同一公司总股本，按投资者个人税前口径比较。'])
    if key == 'haier':
        prices = data['price_snapshot']
        if prices:
            val['priceDate'] = prices['date']
            val['venues'] = [dict(market=m['label'], cnyPrice=m['price_cny'], cash=m['cash_yi']) for m in prices['metrics']]
            val['assumptions'].append(f"{prices['shares_on']} 已发行 {prices['shares']:,} 股。未复权收盘价 × 同日中间价 × 总股本 × 10%。")
            val['shareUrl'] = prices['share_url']
    else:
        path = Path(__file__).parent / 'research' / 'petrochina_book_20261115' / 'valuation.json'
        fixed = json.loads(path.read_text(encoding='utf-8'))
        prices = fixed['price']
        if prices['date'] != snap['date']:
            raise ValueError('正式版价格快照与估值研究日不一致')
        val['priceDate'] = prices['date']
        val['venues'] = [dict(market=label, cnyPrice=prices[k+'_cny'], cash=prices[k+'_needs_at_10']) for k, label in [('h', 'H 股'), ('a', 'A 股')]]
        val['assumptions'].append(f"正式版研究日 A 股 {prices['a_cny']} 元、H 股 {prices['h_hkd']} 港元，1 港元折 {prices['hkd_cny']} 元。")
    return val


def build(data, days=120):
    """Format the current observation for the two company charts."""
    if days not in (60, 120, 270):
        raise ValueError('市场观察窗口须为 60、120 或 270 个工作日')
    key = data['observation']
    codes = ' · '.join(item['code'] for item in data['coverage']
                       if item['code'] not in ('EURCNY', 'HKDCNY', 'B00Y'))
    chart = trend(key, data, days)
    operations = operating(key, data)
    cash = valuation(key, data)
    rows = reversed(chart['timeline'])
    items = operations['visualItems']
    if key == 'haier':
        headline = '同一股海尔，三个市场各出多少钱？'
        deck = '观察沪、港、德三地收盘，拆开汇率、公司经营与各市场价格隐含的年度现金要求。'
        latest = next((r for r in rows if r.get('sh') and r.get('deCny')), None)
        questions = [
            ('三地定价', f"D 股较 A 股 {(latest['deCny']/latest['sh']-1)*100:+.2f}%" if latest else '待同日报价',
             f"{latest['date']}，按当日欧元中间价折算。" if latest else '需要同日 A/D 收盘和欧元中间价。'),
            ('收入结构', f"中国大陆 {items[0]['sharePct']:.1f}%" if items else '尚无可比披露', '2025 年度对外交易收入占比。'),
        ]
    else:
        headline = '从布伦特收盘，到中石油股价要求的现金'
        deck = '每日油价、每半年披露的操作成本和正式版估值各有自己的日期。沿公告回看当时能知道什么。'
        latest = next((r for r in rows if r.get('brent') is not None), None)
        questions = [
            ('布伦特收盘', f"{latest['brent']:.2f} 美元/桶" if latest else '暂无收盘',
             f"{latest['date']} · 东方财富 112.B00Y" if latest else '等待同标的已收盘日线。'),
            ('单位操作成本', f"{items[-1]['value']:.2f} 美元/桶" if items else '尚无可比披露',
             f"{items[-1]['period']}，同比 {items[-1]['badge']}。" if items else '按原件首次公开日显示。'),
        ]
    venues = cash['venues']
    metric = ' / '.join(f"{v['cash']:,.0f}" for v in venues) + ' 亿元' if venues else '暂无同日比较'
    summary = cash.get('reason', '需要同日价格和汇率。')
    if venues:
        summary = '、'.join(v['market'] for v in venues) + f" 次序 · {cash['priceDate']}"
    questions.append(('价格要求的年度现金', metric, summary))
    return dict(id=key, name=data['company'], codes=codes, cutoff=data['cutoff'], headline=headline, deck=deck,
                threeQuestions=[dict(title=t, highlightMetric=m, summary=s) for t, m, s in questions],
                mainChart=chart, operating=operations, valuation=cash)
