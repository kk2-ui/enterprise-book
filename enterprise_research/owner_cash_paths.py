"""Discount explicit ordinary-equity cash paths; no invented normalization inputs."""
import math

METHOD = 'owner_cash_paths'


def number(value, name, minimum=None):
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise ValueError(name + '必须是有限数值')
    if minimum is not None and value < minimum:
        raise ValueError(name + '低于允许范围')
    return value


def calculate(inputs):
    if (inputs.get('currency'), inputs.get('amount_unit'), inputs.get('share_unit')) != ('CNY', 'yuan', 'share'):
        raise ValueError('现金路径采用人民币元及股数口径')
    if inputs.get('claim_scope') != 'ordinary_common_equity_after_tax_interest_and_minority':
        raise ValueError('现金路径须已处理税、利息及少数股东')
    shares = number(inputs['shares'], '股数', 1)
    price = number(inputs['reference_price'], '参考价', 0)
    rates = inputs['rates']
    if not rates or any(number(r, '折现率', 0) <= 0 for r in rates):
        raise ValueError('折现率必须大于零')
    results = []
    for scenario in inputs['scenarios']:
        if not scenario.get('name') or not scenario.get('basis'):
            raise ValueError('须填写情景名称与依据')
        flows = []
        for row in scenario['years']:
            # Years are elapsed 12-month periods; end-year discounting is explicit.
            if row['year'] != len(flows) + 1:
                raise ValueError('现金路径须从第1年连续排列')
            cash = number(row['cash_before_transition'], '过渡调整前股东现金')
            wc = number(row['working_capital_use'], '新增周转投入')
            extra = number(row['other_cash_use'], '额外现金用途', 0)
            flows.append(dict(row, owner_cash=cash - wc - extra))
        if not flows:
            raise ValueError('现金路径不能为空')
        terminal = number(scenario['terminal_cash'], '首个稳定年度现金', 0)
        growth = number(scenario['terminal_growth'], '稳定期增长率')
        if growth > 0 or growth <= -1:
            raise ValueError('本方法仅支持无增长或衰减，不隐含新增增长投资')
        values = {}
        for rate in rates:
            annual_pv = sum(row['owner_cash'] / (1 + rate) ** row['year'] for row in flows)
            terminal_pv = terminal / (rate - growth) / (1 + rate) ** len(flows)
            values[str(rate)] = dict(explicit_cash_pv=annual_pv, terminal_pv=terminal_pv,
                                     total_value=annual_pv + terminal_pv,
                                     value_per_share=(annual_pv + terminal_pv) / shares)
        results.append(dict(name=scenario['name'], years=flows, terminal_cash=terminal,
                            terminal_growth=growth, values=values))
    names = [s['name'] for s in results]
    if len(names) != len(set(names)) or inputs['base_scenario'] not in names:
        raise ValueError('情景名须唯一且包含主判断')
    base = next(row for row in results if row['name'] == inputs['base_scenario'])
    hurdle = number(inputs['comparison_rate'], '比较折现率', 0)
    if hurdle not in rates:
        raise ValueError('比较折现率须在折现率列表中')
    # Solve terminal cash required by the price, preserving the explicit early years.
    base_pv = base['values'][str(hurdle)]['explicit_cash_pv']
    required = (price * shares - base_pv) * (1 + hurdle) ** len(base['years']) * (hurdle - base['terminal_growth'])
    releases = []
    for option in inputs.get('asset_release_sensitivities', []):
        amount = number(option['amount'], '额外返还资产', 0)
        year = number(option['year'], '返还时间', 0)
        net_yield = number(option['after_tax_yield_lost'], '税后收益率损失', 0)
        # Baseline retains interest. Remove the same assets' income after release.
        increment = (amount - amount * net_yield / hurdle) / (1 + hurdle) ** year
        releases.append(dict(option, incremental_value=increment, incremental_value_per_share=increment / shares))
    return dict(kind=METHOD, scenarios=results, base_scenario=inputs['base_scenario'],
                comparison_rate=hurdle, required_terminal_cash_at_reference_price=required,
                asset_release_sensitivities=releases,
                status='RESEARCH_ESTIMATES_WITH_EXPLICIT_CONDITIONS')
