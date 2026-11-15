"""Auditable bridge from group cash to ordinary holders, preserving unknowns.

This is arithmetic inside the existing research workspace. Only explicitly
adopted normal-cash research may feed a sustainable cash-yield comparison.
"""
from copy import deepcopy
from owner_cash_scenarios import number

METHOD='owner_cash_bridge'


def calculate(inputs):
    if inputs.get('amount_unit')!='yuan' or inputs.get('currency') not in ('CNY','HKD','USD'):
        raise ValueError('现金桥须指定原币及元口径')
    mode=inputs.get('basis_type')
    if mode not in ('observed','normal_condition','capitalization_equivalent'):
        raise ValueError('须区分实际期间现金和正常年度条件')
    if not inputs.get('basis') or not inputs.get('claim_scope')=='ordinary_common_equity':
        raise ValueError('须说明普通股权益归属及现金起点依据')
    start=number(inputs['starting_cash'],'起点现金')
    rows=[];known=start
    for row in inputs['adjustments']:
        if not row.get('name') or not row.get('basis'):raise ValueError('每项调整须说明依据，零调整也不例外')
        value=row.get('value')
        if value is not None:known+=number(value,row['name'])
        rows.append(deepcopy(row))
    unknown=[r['name'] for r in rows if r.get('value') is None]
    return dict(kind=METHOD,currency=inputs['currency'],starting_cash=start,adjustments=rows,
                known_cash=known,owner_cash=None if unknown or mode=='capitalization_equivalent' else known,equivalent_cash=known if mode=='capitalization_equivalent' else None,unknown=unknown,
                basis_type=mode,status='partial' if unknown else 'illustrative_equivalence' if mode=='capitalization_equivalent' else 'conditional_estimate' if mode=='normal_condition' else 'observed',
                formula='starting_cash + sum(signed adjustments); unknown is never treated as zero',basis=inputs['basis'])
