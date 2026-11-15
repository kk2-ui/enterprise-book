"""Bind the Greenwald arithmetic to actual, revisioned research inputs.

The underlying methods remain independent. No combined price or default rate.
Money is in the basic unit of the stated currency, shares in shares.
"""
from copy import deepcopy
from valuation_methods import valuation, epv, growth

METHODS = ('asset', 'epv', 'growth')


def epv_completeness(result):
    missing_bridge = any(r['included'] and r['value'] is None for r in result['equity_bridge'])
    missing_earnings = any(r['included'] and r['value'] is None
                           for key in ('ebit_adjustments', 'tax_adjustments') for r in result[key])
    if missing_bridge or missing_earnings:
        result['status'] = 'partial_earnings' if missing_earnings else 'partial_equity_bridge'
        result['warnings'].append('盈利、经营税或普通股权益桥仍有未计量调整；所列数值只是已计量部分的条件合计。')
    for scenario in result.get('scenarios', []):
        epv_completeness(scenario['calculation'])


def incomplete_growth_basis(result):
    result['status'] = 'upstream_incomplete'
    result['meets_explicit_return_requirement'] = None
    result.setdefault('warnings', []).append('采用的EPV尚未形成完整正盈利及权益桥，增长数值仅作诊断。')
    for key in ('scenarios', 'price_grid'):
        for scenario in result.get(key, []):
            if scenario.get('calculation'):
                incomplete_growth_basis(scenario['calculation'])


def bind_growth(inputs, source):
    """Use the stored EPV, never a client-supplied replacement earnings basis."""
    if source['inputs'].get('method') != 'epv':
        raise ValueError('增长基础必须是已保存的EPV计算，不能把条件现金改名为EPV')
    origin, result = source['inputs'], source['result']
    if inputs['as_of'] != origin['as_of']:
        raise ValueError('增长与EPV时点须一致；新时点请先核对并另存EPV')
    if inputs.get('currency') != origin['currency']:
        raise ValueError('增长与EPV须采用相同计价币种')
    basis = dict(currency=result['currency'], unit='currency', scope='enterprise',
                 revenue=result['revenue'], earnings_power=result['earnings_power'],
                 equity_adjustment=result['equity_adjustment'], capital_cost=result['wacc'],
                 capital_cost_basis='wacc', shares=result['shares'], valuation_date=origin['as_of'])
    if inputs.get('basis') not in (None, basis):
        raise ValueError('增长不能覆盖已采用的EPV基础；改变盈利、权益桥或资本成本请先另存EPV')
    for scenario in inputs.get('scenarios', []):
        if scenario.get('basis'):
            raise ValueError('增长情景不能另换EPV基础；请先保存相应EPV并建立增长计算')
    inputs['basis'] = basis
    inputs['epv_basis'] = dict(calculation_id=source['id'], project_revision=source['project_revision'],
                               as_of=origin['as_of'], warnings=deepcopy(result.get('warnings', [])),
                               status=result.get('status'), limitations=origin.get('limitations', ''))


def calculate(inputs):
    method = inputs['method']
    if not inputs.get('currency'):
        raise ValueError('请指定计价币种')
    if inputs.get('unit', 'currency') != 'currency':
        raise ValueError('三步计算金额须使用所选币种的基本单位，股数为股')
    if not str(inputs.get('scope_note', '')).strip():
        raise ValueError('请说明业务范围、权益归属和重要未计量项目')
    if method == 'asset':
        result = valuation.calculate(inputs)
        missing = [r for r in result['items'] if r['included'] and r['value'] is None]
        result['status'] = 'partial_assets' if missing or not result['items'] else 'conditional_estimate'
    elif method == 'epv':
        result = epv.calculate(inputs)
        epv_completeness(result)
    else:
        route = inputs.get('growth_route', {})
        action = route.get('action')
        if action not in ('evaluate', 'skip', 'defer') or not str(route.get('reason', '')).strip():
            raise ValueError('请明确评价增长、不适用或暂缓及其具体理由；定向核查记录在研究过程')
        if action == 'evaluate' and not inputs.get('epv_basis'):
            raise ValueError('评价增长须先选择实际保存的EPV')
        result = growth.calculate(inputs)
        source = inputs.get('epv_basis', {})
        result.setdefault('warnings', []).extend(source.get('warnings', []))
        if source and source.get('status') != 'conditional_estimate' and action == 'evaluate':
            incomplete_growth_basis(result)
    result['kind'] = method
    result['method'] = method
    result.setdefault('warnings', [])
    return result
