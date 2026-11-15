"""Consolidated cash -> ordinary equity -> quote-currency value.

All operating amounts and shares use millions. Annual distributions split the
owner cash; they are neither debt nor a second deduction from equity value.
"""
from copy import deepcopy
from owner_cash_scenarios import number

METHOD = 'layered_owner_cash'


def calculate(inputs):
    i = deepcopy(inputs)
    if (i['currency'], i['amount_unit'], i['share_unit'], i['quote_currency'], i['fx_convention']) != ('CNY', 'million', 'million_shares', 'HKD', 'CNY_per_HKD'):
        raise ValueError('本方法采用人民币百万元、百万股、人民币/港元汇率，输出港元每股价值。')
    def n(key, **kw):
        return number(i[key], key, **kw)
    for key in ['pre_wc','normal_tax','interest','lease','maintenance','deferred_release','annual_distribution','fee','net_ownership_deduction']:
        n(key, nonnegative=True)
    shares = n('shares', positive=True)
    fx = n('cny_per_hkd', positive=True)
    n('reference_price', positive=True)
    for key in ['ownership', 'deferred_ownership', 'deferred_tax_offset']:
        value = n(key, nonnegative=True)
        if value > 1:
            raise ValueError(f'{key} 必须介于0与1之间')
    rates = [number(r, 'rate', positive=True) for r in i['rates']]
    if not rates or any(r >= 1 for r in rates):
        raise ValueError('资本化率须介于0与1之间')
    rate = n('comparison_rate', positive=True)
    if rate >= 1:
        raise ValueError('比较资本化率须小于1')
    xs = [number(x, 'extra_payment', nonnegative=True) for x in i['extra_payments']]
    if len(xs) != 2 or xs[0] > xs[1]:
        raise ValueError('独立额外付款需给出由小到大的两个端点')
    phis = [number(v, 'retention_realization', nonnegative=True) for v in i['retention_realizations']]
    if not phis or any(v > 1 for v in phis):
        raise ValueError('留存现值兑现比例须介于0与1之间')
    before = i['pre_wc'] - i['normal_tax'] - i['interest'] - i['lease'] - i['maintenance']
    deferred_loss = i['deferred_release'] * i['deferred_ownership'] * (1-i['deferred_tax_offset'])
    owner = before * i['ownership'] - i['net_ownership_deduction'] - deferred_loss
    distribution = i['annual_distribution']
    if owner <= 0 or distribution >= owner:
        raise ValueError('本方法要求正的股东现金，且年度分配小于股东现金；超额分配须另行研究资金来源。')
    def values(cash, k=rate):
        return [(cash/k-x)/shares/fx for x in reversed(xs)]
    def price_row(price, label):
        number(price, 'comparison_price', positive=True)
        required = price*(1+i['fee'])*shares*fx*rate
        return dict(label=label, price=price, required_cash=[required+x*rate for x in xs],
                    required_retention=[(required+x*rate-distribution)/(owner-distribution) for x in xs])
    comparisons = [price_row(p['price'],p['label']) for p in i['comparison_prices']]
    sensitivities=[]
    for s in i['sensitivities']:
        maintenance = number(s.get('maintenance_increase',0), 'maintenance increase', nonnegative=True)
        selling = number(s.get('selling_increase',0), 'selling increase', nonnegative=True)
        tax = number(s.get('selling_tax_offset',0), 'selling tax offset', nonnegative=True)
        if tax > 1:
            raise ValueError('费用抵税比例须介于0与1之间')
        cash = owner-(maintenance+selling*(1-tax))*i['ownership']
        if cash <= 0:
            raise ValueError('压力后现金为负，应转入亏损和供资研究')
        sensitivities.append(dict(**s,owner_cash=cash,values=values(cash),value_loss=(owner-cash)/rate/shares/fx))
    deferred=[]
    for s in i['deferred_cases']:
        own = number(s['ownership'], 'deferred ownership', nonnegative=True)
        tax = number(s['tax_offset'], 'deferred tax offset', nonnegative=True)
        if max(own,tax)>1:
            raise ValueError('递延归属与抵税比例须介于0与1之间')
        release = number(s['release'], 'deferred release', nonnegative=True)
        cash = before*i['ownership']-i['net_ownership_deduction']-release*own*(1-tax)
        deferred.append(dict(**s,owner_cash=cash,values=values(cash)))
    return dict(kind=METHOD,company_id=i['company_id'],as_of=i['as_of'],inputs=i,
        bridge=dict(before_deferred=before,adjusted_group_cash=before-i['deferred_release'],deferred_owner_loss=deferred_loss,
                    owner_cash=owner,annual_distribution=distribution,retained_cash=owner-distribution),
        valuation=[dict(rate=k,values=values(owner,k)) for k in rates],
        retention=[dict(realization=p,effective_cash=distribution+(owner-distribution)*p,
                        values=values(distribution+(owner-distribution)*p)) for p in phis],
        comparisons=comparisons,sensitivities=sensitivities,deferred_cases=deferred,
        reference=price_row(i['reference_price'],f"{i['price_date']}冻结参考价"),
        formulas=dict(owner='(pre_wc-tax-interest-lease-maintenance)*ownership-net_ownership_deduction-deferred_release*deferred_ownership*(1-deferred_tax_offset)',
            value='([annual_distribution+(owner_cash-annual_distribution)*retention_realization]/rate-extra_payment)/shares/cny_per_hkd',
            required_retention='(price*(1+fee)*shares*cny_per_hkd*rate+extra_payment*rate-annual_distribution)/(owner_cash-annual_distribution)'),
        assumption_status='RESEARCH_CONDITIONS_NOT_VALIDATED_NORMAL_CASH')


def render_markdown(r):
    i,b=r['inputs'],r['bridge']
    span=lambda a:'—'.join(f'{x:.3f}' for x in a)
    lines=['# 中国食品：从集团现金到港元每股价值','',f"研究时点：{i['as_of']}。经营输入为人民币百万元，股数为百万股；每股价值为港元。",'',
        '这些计算沿用原企业书的研究条件。正常税、维护、下层权益净调整和留存兑现均需要经营依据，计算正确并不使条件成为已核定事实。','',
        '## 先扣经营责任，再分股东的份额','',
        '| 项目 | 人民币百万元 |','| --- | ---: |']
    for key,label in [('pre_wc','滚动十二个月周转前经营现金'),('deferred_release','扣：以前收取的递延支持释放'),('normal_tax','扣：正常现金税'),('interest','扣：利息'),('lease','扣：租赁本金'),('maintenance','扣：每年正常更新')]:
        lines.append(f'| {label} | {i[key]:.3f} |')
    lines += [f"| 以上集团余额 | {b['adjusted_group_cash']:.3f} |",f"| 普通股现金（按各项权益归属及净调整计算） | {b['owner_cash']:.5f} |",'',
        f"本次核心权益为{i['ownership']:.0%}，递延款也暂按{i['deferred_ownership']:.0%}归属，递延税节约为{i['deferred_tax_offset']:.0%}。下层股东与外围业务的净调整扣除{i['net_ownership_deduction']:g}百万元。",'',
        f"得到约{b['owner_cash']/100:.2f}亿元普通股年度现金，其中年度分配暂取{b['annual_distribution']/100:.2f}亿元，余下{b['retained_cash']/100:.2f}亿元留在企业。年度分配是未来条件，不是分红承诺。留存兑现比例表示这部分钱最终形成多少股东现值。",'',
        '## 正常现金具有完整现值时','', '| 资本化率 | 港元/股：额外付款较高端—零或较低端 |','| --- | ---: |']
    for row in r['valuation']:lines.append(f"| {row['rate']:.0%} | {span(row['values'])} |")
    lines += ['',f"以{i['comparison_rate']:.0%}为例，先用年度现金除以资本化率，得到人民币权益价值，再扣一次额外付款，最后除以{i['shares']:g}百万股及{i['cny_per_hkd']:.10f}人民币/港元。汇率按每港元对应多少人民币表示，所以人民币价值换成港元时要除以这个汇率。",'',
        '额外付款的两个端点只讨论未被正常更新或项目价值覆盖的独立付款。它不是所有风险的上下限；年度分红已经包含在普通股现金内，也不再作为债务扣除。交易费用仅用于价格反推，没有从上表内在价值再扣一次。','',
        '## 分红照取，留存部分分别兑现多少现值','', '| 留存兑现比例 | 港元/股 |','| --- | ---: |']
    for row in r['retention']:lines.append(f"| {row['realization']:.0%} | {span(row['values'])} |")
    lines += ['', '兑现比例同时可能受到投资亏损及等待分配的影响，不是成功概率。这里各列是可比较的条件；没有指定某个比例为公司的确定状态。','',
        '## 旧价格分别要求什么','', '| 历史比较价 | 要求留存兑现比例 |','| --- | ---: |']
    for row in r['comparisons']:lines.append(f"| {row['label']}：{row['price']:g}港元 | {'—'.join(f'{x:.1%}' for x in row['required_retention'])} |")
    lines += ['', '超过100%表示现有现金及完整留存兑现仍不足以支持该价格，需要更高的现金、更低资本化率或另有可回收资产。历史比较价不作现价或买卖指令。','',
        '## 单项条件改变时','', '| 条件 | 普通股年度现金（亿元） | 港元/股 |','| --- | ---: | ---: |']
    for row in r['sensitivities']:lines.append(f"| {row['label']} | {row['owner_cash']/100:.3f} | {span(row['values'])} |")
    lines += ['', '各项分别演算，没有把同一费用、递延款或设备责任重复叠加。费用增加按全年条件处理，未把半年差额乘二。','',
        '## 递延款的归属与税务条件','', '| 条件 | 普通股年度现金（亿元） | 港元/股 |','| --- | ---: | ---: |']
    for row in r['deferred_cases']:lines.append(f"| {row['label']} | {row['owner_cash']/100:.3f} | {span(row['values'])} |")
    lines += ['', '## 采用依据与时间条件','']
    for value in i['basis'].values():lines += [value,'']
    return '\n'.join(lines)
