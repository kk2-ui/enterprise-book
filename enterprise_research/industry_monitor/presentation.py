"""Standalone snapshot reader: same numbers online and offline, no CDN."""
from html import escape
import json
import re


def e(value):return escape(str(value if value is not None else '—'),quote=True)
def n(value,digits=2):return '—' if value is None else f'{value:,.{digits}f}'
def pct(value):return '—' if value is None else f'{value*100:.1f}%'


def research_text(text,sources):
    def marker(m):
        sid,page,label=m.groups();s=sources.get(sid,{})
        return f'<a href="{e(s.get("url") or "#sources-"+sid)}{("#page="+page) if page and s.get("url") else ""}">{e(label or s.get("title") or sid)}</a>'
    text=re.sub(r'\*\*([^*]+)\*\*',r'<b>\1</b>',e(text))
    return re.sub(r'\[\[source:([\w-]+)(?:@(\d+))?(?:\|([^\]]+))?\]\]',marker,text)


def research_blocks(text,sources):
    """Render authored paragraphs/tables without turning source text into HTML."""
    out=[];table=False
    for line in text.splitlines():
        if line.strip().startswith('|'):
            if not table:out.append('<div class="table-scroll"><table>');table=True
            if re.fullmatch(r'[\s|:\-]+',line):continue
            out.append('<tr>'+''.join('<td>'+research_text(c.strip(),sources)+'</td>' for c in line.strip().strip('|').split('|'))+'</tr>')
            continue
        if table:out.append('</table></div>');table=False
        if line.strip():out.append('<p>'+research_text(line,sources)+'</p>')
    if table:out.append('</table></div>')
    return ''.join(out)


def cash_bridge(x):
    cash=x.get('owner_cash') or x.get('observed_cash_bridge')
    if not cash or 'adjustments' not in cash:return ''
    observed=cash.get('basis_type')=='observed'
    label='已发生期间现金桥' if observed else '正常年度普通股现金桥'
    rows=''.join(f'<tr><td>{e(a["name"])}</td><td>{n(a.get("value")/1e6 if a.get("value") is not None else None,3)}</td><td>{e(a["basis"])}</td></tr>' for a in cash['adjustments'])
    return f'''<h4>{label}</h4><p>{e(cash['basis'])}。金额为百万元 {e(cash['currency'])}。</p>
    <table><tr><th>项目</th><th>金额</th><th>依据</th></tr><tr><td>现金起点</td><td>{n(cash['starting_cash']/1e6,3)}</td><td>按所列期间与合并范围</td></tr>{rows}</table>
    <p>已列项目后的现金：{n(cash['known_cash']/1e6,3)}百万元。{'这是期间收支的部分衔接，不是账上现金余额或未来正常现金。' if observed else '此数仍受列明正常经营条件约束。'}
    {'尚未计量：'+e('；'.join(cash['unknown']))+'；未将未知按零计入，普通股可持续现金收益率不生成。' if cash['unknown'] else ''}</p>'''


def economics(row):
    x=row.get('economic')
    if not x:return ''
    epv=x.get('epv',{});asset=x.get('asset_reference',{});tables=[]
    for title,rows in [('正常经营收益桥',epv.get('earnings_bridge',[])),('经营价值到普通股权益',epv.get('equity_bridge',[]))]:
        if rows:tables.append('<h4>'+title+'</h4><table><tr><th>项目</th><th>金额或比率</th><th>依据</th></tr>'+''.join(f'<tr><td>{e(r.get("name",r.get("id")))}</td><td>{n(r.get("value"))}</td><td>{e(r.get("reason",""))}</td></tr>' for r in rows)+'</table>')
    return f'''<section><h3>经济调整与已采用计算</h3><p>{e(x['boundary'])}。研究日 {e(x['research_date'])}，采用日 {e(x['adopted_on'])}。</p>
      <p>价格 / 条件EPV：{n(epv.get('price_to_value'))}；资本成本 {pct(epv.get('capital_cost'))}。已计量资产参照的价格比：{n(asset.get('price_to_value'))}，状态 {e(asset.get('status'))}。</p>
      <p>{e(x.get('operating_earnings_label','正常经营收益'))}：{pct(x.get('operating_earnings_yield'))}。普通股可持续现金收益率：{pct(x.get('owner_cash_yield'))}。{e(x.get('owner_cash_reason'))}</p>
      {('<p>下表原币种为 '+e(epv.get('currency'))+'，金额使用基本货币单位；比率按原计算保留。</p>') if tables else ''}{''.join(tables)}{cash_bridge(x)}
      <details><summary>完整资产、EPV及增长计算（含输入、情景和未计量项目）</summary><pre>{e(json.dumps(x['calculations'],ensure_ascii=False,indent=2))}</pre></details></section>'''


def market_detail(market):
    rows=[]
    for days,w in market.get('monitor',{}).get('windows',{}).items():
        effects=w.get('contributions_log_pp') or {}
        rows.append(f'<tr><th>{e(days)}个交易日</th><td>{e(w.get("driver_label","无法识别"))}</td><td>{n(w.get("r2"))}</td><td>{e("；".join(str(k)+" "+n(v)+" 对数百分点" for k,v in effects.items()))}</td><td>{e(w.get("reason",w.get("warnings",[])))}</td></tr>')
    return '<section><h2>顺逆风与统计主导力量</h2><p>'+e(market.get('return_convention','回报口径尚未匹配'))+'</p><table><tr><th>窗口</th><th>统计判断</th><th>拟合R²</th><th>区间分解</th><th>边界</th></tr>'+''.join(rows)+'</table><p>回归分解不是因果比例；残差不能证明公司自身出问题。低估、逆风与错杀分别判断。</p><details><summary>量价、长期比较与完整模型输入/覆盖</summary><pre>'+e(json.dumps(market,ensure_ascii=False,indent=2))+'</pre></details></section>'


def current_reading(snapshot):
    poly=next(r for r in snapshot['companies'] if r['code']=='06049.HK')
    g=snapshot['groups']['basic'];peer=snapshot['poly_peer_position']['pe'];h=poly['historical_percentiles']['pe']
    monitor=snapshot['market'].get('monitor',{});w=monitor.get('windows',{}).get('60',{})
    context=[]
    for key,label in [('market','恒生综合'),('industry','基础物业有效参照'),('stock','保利')]:
        x=monitor.get(key,{})
        context.append(f'<tr><th>{label}</th><td>{e(x.get("state"))}</td>'+''.join(f'<td>{n(x.get("returns",{}).get(str(d)))}%</td>' for d in (20,60,252))+'</tr>')
    long=snapshot['market'].get('sector_history',{}).get('main',{});lg=long.get('groups',{}).get('basic',{})
    return f'''<section><h2>先读当前判断</h2><h3>便宜程度：历史位置与同行位置分开</h3>
    <p>保利PE {n(poly['pe_ttm']['value'])}倍、PB {n(poly['pb']['value'])}倍。PE在自身{h['count']}个有效月末值中为第{n(h.get('value'),1)}百分位；排除保利后的正PE中位数{n(peer['median'])}倍，{peer['positive_multiple_count']}家正PE中有{peer['lower_count']}家低于保利。这里是报表倍数比较，尚不能据此断言内在低估。</p>
    <p>基础物业整体PE {n(g['pe']['overall']['value'])}倍，正PE中位数{n(g['pe']['median'])}倍；整体比率保留{g['pe']['nonpositive']}家非正利润，在{g['pe']['valid']}/{g['selected']}家同分子分母覆盖内成立。整体PB {n(g['pb']['overall']['value'])}倍、中位数{n(g['pb']['median'])}倍。亏损与信用损失会拉大整体PE与中位数的差距；低PB也须先查应收和无形资产。</p>
    <h3>顺逆风：同一含息口径</h3><table><tr><th>层次</th><th>价格处境</th><th>20日</th><th>60日</th><th>252日</th></tr>{''.join(context)}</table>
    <p>当前含息模型实际纳入{monitor.get('industry',{}).get('breadth',{}).get('valid','—')}家同行，保利不进入自己的行业参照；停牌、稀疏成交、日期或资本事件口径不齐者仍留在39家明细中，不能把模型有效参照称为全部行业。</p>
    <h3>主导力量：按观察窗口判断</h3><p>最近60日：{e(w.get('driver_label','无法识别'))}。解释力R² {n(w.get('r2'))}，保利相对行业变化{n(w.get('relative_returns',{}).get('stock_industry'))}%。统计共同变化支持市场/行业环境判断，残差只说明模型之外的变化，不能认定为公司基本面恶化或错杀。</p>
    <p>长期另用统一不含股息的价格口径，从{e(long.get('start'))}到{e(long.get('end'))}：恒生综合{n(long.get('market_pct'))}%，保利{n(lg.get('own_pct'))}%；起点基础物业同行（排除保利）{lg.get('selected','—')}家中，有{lg.get('valid','—')}家同行取得可比终点，中位数{n(lg.get('median_pct'))}%，{lg.get('unknown','—')}家未知。{e(snapshot.get('universe_scope'))}未取得退出价的公司不当零回报，也不冒充幸存者已覆盖。</p></section>'''


def sector_valuation_history(snapshot):
    out=[]
    for group,label in [('basic','基础物业'),('commercial','商管'),('mixed','混合')]:
        g=snapshot['groups'][group];history=g.get('history',[])
        if not history:continue
        rows=[dict(date=h['date'],pe=h['pe']['overall']['value'],pb=h['pb']['overall']['value']) for h in history]
        stats=g.get('historical_percentiles',{})
        table=''.join(f'<tr><td>{e(h["date"])}</td><td>{n(h["pe"]["overall"]["value"])}</td><td>{h["pe"]["valid"]}/{h["pe"]["selected"]}</td><td>{h["pe"]["nonpositive"]}</td><td>{n(h["pb"]["overall"]["value"])}</td><td>{h["pb"]["valid"]}/{h["pb"]["selected"]}</td></tr>' for h in history)
        out.append(f'<details><summary>{label}历史估值与覆盖</summary><p>整体PE第{n(stats.get("pe",{}).get("value"),1)}百分位，{stats.get("pe",{}).get("count",0)}个有效月末值；整体PB第{n(stats.get("pb",{}).get("value"),1)}百分位。名单及业务分组按当前回顾，每月仅用当时可得财务、股本和行情，样本覆盖变化亦会改变比率。</p><h4>整体PE（倍）</h4>{history_chart(rows,"pe",label+"整体PE")}<h4>整体PB（倍）</h4>{history_chart(rows,"pb",label+"整体PB")}<table><tr><th>月末</th><th>整体PE</th><th>PE有效/选定</th><th>非正利润</th><th>整体PB</th><th>PB有效/选定</th></tr>{table}</table></details>')
    return '<section><h2>行业报表估值的历史位置</h2><p>不足36个月不显示长期分位；不同月份有效覆盖变化可影响排名，历史便宜位置不替代经济价值。</p>'+''.join(out)+'</section>'


def history_chart(rows,key,title):
    valid=[(i,r[key]) for i,r in enumerate(rows) if r.get(key) is not None]
    if not valid:return '<p class="unknown">严格历史时点有效观察为0；未核公开版本的供应商历史值没有补入。</p>'
    low=min(0,min(v for _,v in valid));high=max(v for _,v in valid) or 1;paths=[];last=-2
    for i,v in valid:
        x=45+i*700/max(1,len(rows)-1);y=180-(v-low)*145/(high-low)
        paths.append(('L' if i==last+1 else 'M')+f'{x:.1f},{y:.1f}');last=i
    return f'<svg viewBox="0 0 780 220" role="img" aria-label="{e(title)}"><title>{e(title)}；缺失处断线</title><path d="{" ".join(paths)}" fill="none" stroke="#287166" stroke-width="2"/><text x="5" y="35">{n(high)}</text><text x="5" y="180">{n(low)}</text><text x="45" y="210">{e(rows[0]["date"])}</text><text x="650" y="210">{e(rows[-1]["date"])}</text></svg>'


def company_detail(row):
    r=row.get('research');entries='';sources={s['id']:s for s in row.get('sources',[])}
    if r:
        entries='<p>'+e(r.get('current_view',''))+'</p>'
        entries+=''.join('<section><h4>'+e(x['title'])+'</h4><div class="prose">'+research_blocks(x['body'].removeprefix(x['title']).lstrip(),sources)+'</div></section>' for x in r['entries'])
        entries+='<p><b>反方：</b>'+e(r.get('rival'))+'</p><p><b>改判与接续：</b>'+e(r.get('next_step'))+'</p>'
    else:entries='<p class="unknown">本批已核业务分类，商管及混合组单列作报表参照；本批未对这7家作经济重估。</p>'
    adjustments=''.join(f'<tr><td>{e(a["key"])}</td><td>{e(a["status"])}</td><td>{e(a["basis"])}</td><td>{e(a["reason"])}</td><td>{e(a.get("range"))}</td><td>{e(a["rival"])}</td></tr>' for a in row.get('adjustments',[]))
    history=''.join(f'<tr><td>{e(h["date"])}</td><td>{n(h["price"])}</td><td>{n(h["pe"])}</td><td>{n(h["pb"])}</td><td>{e("；".join(h["issues"]))}</td></tr>' for h in row.get('history',[]))
    facts=''.join(f'<tr><td>{e(f["metric"])}</td><td>{e(f["period_end"])}</td><td>{n(f["value"])} {e(f["currency"])}</td><td>{e(f["available_on"])}</td><td>{e(f["scope"])}</td><td>{e(f.get("source",{}).get("pdf_page"))}<br>{e(f.get("source",{}).get("excerpt",f.get("source",{}).get("formula","")))}</td><td>{e(f["id"])}</td></tr>' for f in row.get('evidence_facts',row.get('source_facts',[])))
    source_links=''.join(f'<p id="sources-{e(s["id"])}"><a href="{e(s.get("url") or "#")}">{e(s.get("title"))}</a> · {e(s["id"])}</p>' for s in sources.values())
    event_rows=''.join(f'<tr><td>{e(x["published_at"])}</td><td><a href="{e(x["source_url"])}">{e(x["title"])}</a></td><td>{"原件已取得" if x["evidence_status"]=="original_acquired" else "仅公告索引，正文待取得"}</td></tr>' for x in row.get('company_events',[]))
    event_block=('<details><summary>公司事件与市场判断的其他解释</summary><p>最近一年公告提示，保留停复牌、收购、关联交易等公司因素。标题不证明事件已完成或是涨跌原因；已研究的经济含义见下文。</p><table><tr><th>公开时点</th><th>公告原件</th><th>取得状态</th></tr>'+event_rows+'</table></details>') if event_rows else ''
    return f'''<article id="{e(row['subject_id'])}" class="company"><h2>{e(row['name'])} <small>{e(row['code'])}</small></h2>
      <p>分组依据：{e(row.get('classification_reason'))}。<a href="{e(row.get('classification',{}).get('source_url','#'))}">分类原件</a>，公开日 {e(row.get('classification',{}).get('known_at'))}。当前分组不倒填为历史业务事实。</p><p>回顾有效期 {e(row.get('membership',{}).get('valid_from'))}至{e(row.get('membership',{}).get('valid_to') or '仍在样本')}；{e(row.get('membership',{}).get('date_basis'))}。</p><p>财报期 {e(row.get('financial_period'))} · 股本 {e(row.get('shares_date'))} · 研究日 {e((r or {}).get('as_of'))}</p>
      <div class="stats"><div>PE TTM<strong>{n(row['pe_ttm']['value'])}</strong></div><div>PB<strong>{n(row['pb']['value'])}</strong></div><div>经营现金减资本开支<strong>{n(row['cash_proxy_multiple']['value'])}</strong></div></div>
      <p>市值 {n(row.get('market_cap')/1e8 if row.get('market_cap') is not None else None)} 亿港元。所有倍数按对应分母匹配普通股权利；现金筛查值尚非普通股可分配现金。</p>
      {event_block}
      <details><summary>原表计算、输入版本与缺口</summary><ul>{''.join('<li>'+e(x)+'</li>' for x in row['issues'])}</ul><pre>{e(json.dumps(row.get('basis',{}),ensure_ascii=False,indent=2))}</pre></details>
      <details><summary>原件事实与来源（当前及历史，均为冻结输入）</summary><table><tr><th>指标</th><th>期间</th><th>原币金额</th><th>可用收盘日</th><th>归属</th><th>PDF页/原文</th><th>事实编号</th></tr>{facts}</table>{source_links}</details>
      {economics(row)}
      {entries}
      {('<details><summary>经济调整桥</summary><table><thead><tr><th>项目</th><th>状态</th><th>原数/依据</th><th>理由</th><th>范围</th><th>反方</th></tr></thead><tbody>'+adjustments+'</tbody></table></details>') if adjustments else ''}
      <details><summary>2021年以来当时可知的报表估值</summary><h4>未复权价格（港元）</h4>{history_chart(row.get('history',[]),'price','未复权价格')}<h4>PE TTM（倍）</h4>{history_chart(row.get('history',[]),'pe','PE TTM 历史')}<h4>PB（倍）</h4>{history_chart(row.get('history',[]),'pb','PB 历史')}<h4>当时可知TTM归母利润（港元换算）</h4>{history_chart(row.get('history',[]),'earnings','TTM归母利润')}<table><thead><tr><th>日期</th><th>未复权价格</th><th>PE</th><th>PB</th><th>覆盖说明</th></tr></thead><tbody>{history}</tbody></table><details><summary>每个月末的原始输入、汇率与事实编号</summary><pre>{e(json.dumps(row.get('history',[]),ensure_ascii=False,indent=2))}</pre></details></details><a href="#top">回到行业表 ↑</a></article>'''


def offline(snapshot):
    if snapshot.get('status')=='pending':return '<!doctype html><meta charset="utf-8"><p>首批数据与研究尚未发布。</p>'
    groups=[]
    for key,label in [('basic','基础物业'),('commercial','商管'),('mixed','混合业务')]:
        group=snapshot['groups'][key];rows=[r for r in snapshot['companies'] if r['group']==key]
        stats=group['pe'];coverage=pct(stats['market_cap_coverage'])
        groups.append(f'<section><h2>{label} · {len(rows)}家</h2><p>整体PE {n(stats["overall"]["value"])} · 正倍数中位数 {n(stats["median"])} · 同口径有效 {stats["valid"]}/{stats["selected"]}家 · 可得市值覆盖 {coverage} · 非正利润 {stats["nonpositive"]}家</p><p class="muted">整体比率保留亏损分母；中位数仅计算有意义的正倍数。未取得市值的公司不在市值覆盖分母内，家数缺口另列。基础物业行业整体包含保利，保利同行位置排除自身。</p><table><thead><tr><th>主体</th><th>状态</th><th>财报期</th><th>PE TTM</th><th>PB</th><th>现金筛查</th><th>研究</th></tr></thead><tbody>'+''.join(
            f'<tr><th><a href="#{e(r["subject_id"])}">{e(r["name"])}</a><small>{e(r["code"])}</small></th><td>{"当日可得" if r["active"] else "停牌/退出/无当日价"}</td><td>{e(r.get("financial_period"))}</td><td>{n(r["pe_ttm"]["value"])}</td><td>{n(r["pb"]["value"])}</td><td>{n(r["cash_proxy_multiple"]["value"])}</td><td>{"有研究记录" if r["research"] else "已核分类；未作经济重估"}</td></tr>' for r in rows)+'</tbody></table></section>')
    market=snapshot.get('market',{});wind=market.get('metrics',{}).get('trend','无法判定')
    return f'''<!doctype html><html lang="zh-CN"><meta charset="utf-8"><title>物业行业估值与市场环境 · {e(snapshot['as_of'])}</title>
    <style>body{{font:16px/1.75 system-ui,sans-serif;color:#243b38;background:#f6f7f3;max-width:1180px;margin:36px auto;padding:0 24px}}h1{{font-size:30px}}h2{{font-size:24px}}h3,h4{{margin-bottom:6px}}a{{color:#17665d}}small,.muted{{color:#60726e}}small{{display:block;font-size:12px}}section,.company{{background:white;padding:26px;margin:24px 0;border:1px solid #d6dfd9;border-radius:7px}}table{{width:100%;border-collapse:collapse;font-size:14px}}td,th{{text-align:left;border-bottom:1px solid #e3e9e4;padding:10px;vertical-align:top}}.stats{{display:flex;gap:40px;margin:20px 0}}strong{{display:block;font-size:25px}}.unknown{{background:#fbf2db;padding:14px}}details{{margin:18px 0}}summary{{cursor:pointer;color:#21665b}}.prose p{{max-width:85ch}}.prose b{{font-weight:650}}.table-scroll{{overflow-x:auto}}td{{overflow-wrap:anywhere}}pre{{white-space:pre-wrap;overflow-wrap:anywhere;font-size:12px;background:#f5f7f5;padding:12px}}svg{{max-width:900px;width:100%;font:12px system-ui}}@media print{{body{{margin:0}}details{{display:block}}}}</style>
    <body id="top"><h1>物业行业估值与市场环境</h1><p>行情日 {e(snapshot['as_of'])} · 信息截止 {e(snapshot['information_cutoff'])} · 快照 {e(snapshot['run_id'])} · 方法 {e(snapshot['method_version'])}</p>
    <p class="unknown">{'当前快照覆盖尚不完整，以下结论仅适用于明确列出的有效输入。' if snapshot['status']=='partial' else '已发布研究快照。'} {e(snapshot['boundary'])}</p>
    <p>保利价格趋势：{e(wind)}。{e(market.get('return_basis',{}).get('reason',''))}</p>
    <p>32家基础物业是本批研究样本，含历史退出成员；另列3家商管与4家混合业务。并非香港全部物业公司的穷尽清单。重估只用于研究日之后，不倒填历史。</p>
    {current_reading(snapshot)}{market_detail(market)}<details><summary>商管、混合业务的分类核验全文</summary>{research_blocks(snapshot.get('classification_report',''),{})}</details>
    <details><summary>大盘估值的官方观测及日期</summary><pre>{e(json.dumps(snapshot.get('index_valuations',[]),ensure_ascii=False,indent=2))}</pre><p>官方指数估值保留原定义；与本批行业归母口径或日期不同时不直接作高低排序。未披露的PB等指标不填零。</p></details>
    {sector_valuation_history(snapshot)}{''.join(groups)}{''.join(company_detail(r) for r in snapshot['companies'])}</body></html>'''
