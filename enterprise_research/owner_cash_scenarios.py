"""Conditional common-equity arithmetic; economic assumptions belong to research.

This deliberately does not attest source-bound Owner Cash readiness or produce
trade instructions. Amounts are CNY, shares are individual ordinary shares.
"""
from copy import deepcopy
import math


def number(value, name, *, positive=False, nonnegative=False):
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise ValueError(f'{name}: explicit finite number required')
    if positive and value <= 0 or nonnegative and value < 0:
        raise ValueError(f'{name}: invalid sign')
    return value


def calculate(inputs):
    if inputs['currency'] != 'CNY' or inputs['amount_unit'] != 'yuan' or inputs['share_unit'] != 'share':
        raise ValueError('use CNY yuan and individual shares; convert before calculation')
    if inputs['claim_scope'] != 'ordinary_common_equity_after_tax_interest_and_minority':
        raise ValueError('this calculation accepts direct common-equity earnings only')
    shares = number(inputs['shares'], 'shares', positive=True)
    price = number(inputs['reference_price'], 'reference_price', positive=True)
    rates = [number(r, 'capitalization_rate', positive=True) for r in inputs['rates']]
    if not rates or any(r >= 1 for r in rates):
        raise ValueError('capitalization rates must be decimal fractions between zero and one')
    rows = []
    for scenario in inputs['scenarios']:
        profit = number(scenario['normal_parent_profit'], 'normal_parent_profit')
        update = number(scenario['maintenance_net_adjustment'], 'maintenance_net_adjustment')
        reserve = number(scenario['working_capital_reserve'], 'working_capital_reserve', nonnegative=True)
        if not scenario['basis']:
            raise ValueError('scenario requires its research basis')
        cash = profit + update - reserve
        if cash <= 0:
            raise ValueError('nonpositive cash requires separate funding/loss research, not perpetuity pricing')
        rows.append({**deepcopy(scenario), 'owner_cash': cash,
                     'values_per_share': {str(r): cash / r / shares for r in rates}})
    names = [r['name'] for r in rows]
    if not rows or len(set(names)) != len(names):
        raise ValueError('distinct scenarios are required')
    base = next(r for r in rows if r['name'] == inputs['base_scenario'])
    stress = inputs['stress']
    rate = number(stress['capitalization_rate'], 'stress rate', positive=True)
    realization = number(stress['realization_fraction'], 'realization fraction', positive=True)
    decline = number(stress['annual_decline'], 'annual decline', nonnegative=True)
    lower_cash = number(stress['structural_cash'], 'structural cash', positive=True)
    if realization > 1 or decline >= 1 or rate >= 1:
        raise ValueError('stress fractions are out of range')
    return {
        'kind': 'conditional_owner_cash_scenarios',
        'company_id': inputs['company_id'], 'as_of': inputs['as_of'],
        'currency': 'CNY', 'amount_unit': 'yuan', 'shares': shares,
        'reference_price': price, 'price_date': inputs['price_date'],
        'scenarios': rows,
        'required_cash_at_reference_price': price * shares * rate,
        'base_cash_yield_at_reference_price': base['owner_cash'] / (price * shares),
        'stress': {
            'capitalization_rate': rate,
            'realization_fraction': realization,
            'realization_value_per_share': base['owner_cash'] * realization / rate / shares,
            'annual_decline': decline,
            # Cash is the first future year's amount, so no extra (1-g) term.
            'declining_value_per_share': base['owner_cash'] / (rate + decline) / shares,
            'structural_cash': lower_cash,
            'structural_value_per_share': lower_cash / rate / shares,
            'value_change_per_1bn_annual_cash': 1e9 / rate / shares,
        },
        'formulas': {
            'cash': 'normal_parent_profit + maintenance_net_adjustment - working_capital_reserve',
            'value': 'first_future_year_cash / capitalization_rate / shares',
            'decline': 'first_future_year_cash / (capitalization_rate + annual_decline) / shares',
        },
        'assumption_status': 'RESEARCH_CONDITIONS_NOT_VALIDATED_NORMAL_CASH',
        'inputs': deepcopy(inputs),
    }


def render_markdown(result):
    inp = result['inputs']
    lines = ['# 格力条件现金与估值演算', '',
             f"研究时点：{result['as_of']}。参考价：{result['reference_price']}元，日期为{result['price_date']}，未刷新行情。",
             '', '所有金额输入均为人民币元、股份为股。以下是研究条件的演算，未将维护投入、周转或正常盈利升级为已核定事实。', '',
             '| 情景 | 正常归母收益（亿元） | 净更新修正 | 周转预留 | 股东现金 | ' + ' | '.join(f'{r:.0%}每股价值' for r in inp['rates']) + ' |',
             '| --- | ---: | ---: | ---: | ---: | ' + ' | '.join('---:' for _ in inp['rates']) + ' |']
    for row in result['scenarios']:
        values = [row[k] / 1e8 for k in ['normal_parent_profit','maintenance_net_adjustment','working_capital_reserve','owner_cash']]
        lines.append('| ' + row['name'] + ' | ' + ' | '.join(f'{x:g}' for x in values) + ' | ' + ' | '.join(f'{row["values_per_share"][str(r)]:.2f}' for r in inp['rates']) + ' |')
    lines += ['', '净更新修正以带正负号的金额加到利润上，周转预留按支出扣除。税、利息与少数股东已在归母起点处理；未另加现金、另减债务或预计未来注销。', '',
              f"按{result['stress']['capitalization_rate']:.0%}反推，参考价格需要每年{result['required_cash_at_reference_price']/1e8:.2f}亿元股东现金。"]
    s = result['stress']
    lines += [f"股东取得基准现值的{s['realization_fraction']:.0%}时，每股{s['realization_value_per_share']:.2f}元；第一年为基准现金、以后每年下降{s['annual_decline']:.0%}时，每股{s['declining_value_per_share']:.2f}元；现金稳定在{s['structural_cash']/1e8:g}亿元时，每股{s['structural_value_per_share']:.2f}元。三项分别演算，没有叠加。", '']
    for row in result['scenarios']:
        lines += [f"**{row['name']}的研究依据：**{row['basis']}", '']
    lines += ['完整输入、公式和未四舍五入结果见同目录valuation_result.json。经济判断与原件入口见研究记录.md。']
    return '\n'.join(lines) + '\n'
