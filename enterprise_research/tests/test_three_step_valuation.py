"""Economic failure cases plus the real research persistence boundary."""
import sys
import tempfile
import unittest
from copy import deepcopy
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app import Store
import research_workspace as research


class ThreeStepTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.store = Store(self.tmp.name)
        self.cid = self.store.add_company(dict(name='三步合成测试', currency='CNY'))
        self.project = dict(title='三步测试', question='合成经济口径', as_of='2026-11-01', entries=[])
        self.pid = research.save(self.store, self.cid, self.project)['id']
        self.common = dict(company_id=self.cid, as_of='2026-11-01', currency='CNY', unit='currency',
                           scope_note='合成的同范围集团经营及普通股；无其他资源义务', shares=10)
        self.epv = dict(self.common, method='epv', earnings=dict(revenue=1000, margin=.2,
                        da_addback=30, working_capital_addition=0, lease=dict(mode='financing')),
                        maintenance=dict(mode='direct', value=40), tax=dict(mode='direct', value=50),
                        capital_cost=dict(mode='direct', currency='CNY', wacc=.1),
                        equity_adjustments=[dict(id='cash',kind='excess_cash',value=100),
                                            dict(id='debt',kind='financing_debt',value=200),
                                            dict(id='nci',kind='nci',value=50)])

    def tearDown(self):
        self.tmp.cleanup()

    def run_calc(self, inputs, save=True):
        return research.compute(self.store, self.cid, self.pid, dict(project_revision=1,
                title=inputs['method'],change_note='合成经济案例，非公司研究',inputs=inputs), save)

    def growth(self, epv):
        return dict(self.common, method='growth', epv_calculation_id=epv['id'],
                    growth_route=dict(action='evaluate',reason='合成受保护市场'),
                    price=dict(mode='per_share',value=125,currency='CNY',date='2026-10-30'),
                    distribution=dict(mode='direct',value=100),
                    organic=dict(earnings_growth=.02,investment=dict(mode='direct',value=20)),
                    active=dict(mode='direct',factor=1),franchise=dict(status='supported'),
                    decay=dict(mode='deduct',rate=.02,residual_fraction=.5))

    def test_epv_operating_to_common_bridge_is_independent_of_asset_value(self):
        r = self.run_calc(self.epv)['result']
        self.assertEqual(r['earnings_power'],140)
        self.assertEqual(r['core_epv'],1400)
        self.assertEqual(r['equity_value'],1250)
        self.assertEqual(r['per_share'],125)
        self.assertEqual(r['wacc'],.1)
        self.assertNotIn('price_date',self.run_calc(self.epv)['inputs'])

    def test_unmeasured_liability_is_partial_not_zero_or_floor(self):
        asset=dict(self.common,method='asset',items=[dict(id='plant',kind='asset',value=2000,operating=True),
                dict(id='liability',kind='liability',value=None,reason='义务未计量')])
        r=self.run_calc(asset)['result']
        self.assertEqual(r['equity_value'],2000)
        self.assertEqual(r['status'],'partial_assets')
        self.assertTrue(r['warnings'])
        missing=deepcopy(self.epv);missing['equity_adjustments'][1]['value']=None
        e=self.run_calc(missing)
        self.assertEqual(e['result']['status'],'partial_equity_bridge')
        r=self.run_calc(self.growth(e))['result']
        self.assertEqual(r['status'],'upstream_incomplete')
        self.assertIsNone(r['meets_explicit_return_requirement'])

    def test_no_default_rate_or_missing_maintenance_becomes_price(self):
        for field in ('maintenance','capital_cost'):
            i=deepcopy(self.epv);i[field]=dict(currency='CNY') if field=='capital_cost' else {}
            r=self.run_calc(i)['result']
            self.assertIsNone(r['equity_value'])
            self.assertEqual(r['status'],'incomplete')

    def test_finance_principal_and_retained_asset_income_are_not_double_counted(self):
        i=deepcopy(self.epv)
        for row in i['equity_adjustments'][:2]:row['reflected_in_earnings']=True
        r=self.run_calc(i)['result']
        # Asset with retained income excluded, financing debt still deducted.
        self.assertEqual(r['equity_value'],1150)

    def test_growth_binds_epv_and_uses_value_factor_once(self):
        e=self.run_calc(self.epv);g=self.run_calc(self.growth(e))
        r=g['result']
        self.assertEqual(r['core_purchase_cost'],1400)
        self.assertEqual(r['active_investment'],20)
        self.assertEqual(r['active_net_value_created'],0)
        self.assertAlmostEqual(r['baseline_return'],100/1400+.02+20/1400)
        self.assertAlmostEqual(r['net_return'],r['baseline_return']-.01)
        self.assertEqual(g['inputs']['basis']['earnings_power'],140)
        self.assertEqual(g['inputs']['epv_basis']['calculation_id'],e['id'])
        self.assertEqual(research.calculation(self.store,self.cid,self.pid,g['id']),g)

    def test_negative_funding_balance_does_not_become_growth_approval(self):
        g=self.growth(self.run_calc(self.epv));g['distribution']['value']=130
        r=self.run_calc(g)['result']
        self.assertEqual(r['active_investment'],-10)
        self.assertEqual(r['funding_gap'],10)
        self.assertIsNone(r['net_return'])
        self.assertEqual(r['status'],'unfunded_growth')

    def test_unknown_profit_or_tax_adjustment_limits_all_growth_paths(self):
        for block in ('earnings','tax'):
            i=deepcopy(self.epv)
            key='ebit_adjustments' if block=='earnings' else 'adjustments'
            i[block][key]=[dict(id='unknown_recurring_cost',value=None)]
            e=self.run_calc(i)
            self.assertEqual(e['result']['status'],'partial_earnings')
            g=self.growth(e)
            g['policy']=dict(additional_margin=0)
            g['price']['value']=20
            g['scenarios']=[dict(name='低价比较',price=dict(g['price']))]
            g['price_grid']=[dict(g['price'])]
            r=self.run_calc(g)['result']
            for case in [r,r['scenarios'][0]['calculation'],r['price_grid'][0]['calculation']]:
                self.assertEqual(case['status'],'upstream_incomplete')
                self.assertIsNone(case['meets_explicit_return_requirement'])

    def test_skill_date_is_preserved_and_not_silently_rolled_forward(self):
        i=deepcopy(self.epv);del i['as_of'];i['valuation_date']='2026-06-30'
        e=self.run_calc(i)
        self.assertEqual(e['inputs']['as_of'],'2026-06-30')
        i['as_of']='2026-11-01'
        with self.assertRaisesRegex(ValueError,'时点不一致'):self.run_calc(i)

    def test_skip_or_defer_needs_reason_but_not_price_or_epv(self):
        for action,status in [('skip','not_applicable'),('defer','awaiting_evidence')]:
            g=dict(self.common,method='growth',growth_route=dict(action=action,reason='公开证据不足以支持本轮增长估计'))
            r=self.run_calc(g)['result']
            self.assertEqual(r['status'],status)
            self.assertFalse(r['calculation_performed'])
            self.assertIsNone(r['baseline_return'])
            g['growth_route']['reason']=''
            with self.assertRaises(ValueError):self.run_calc(g)

    def test_wrong_epv_date_currency_or_silent_override_is_rejected(self):
        e=self.run_calc(self.epv);g=self.growth(e)
        changes=[dict(basis=dict(earnings_power=999)),dict(currency='HKD'),dict(as_of='2026-11-02'),
                 dict(scenarios=[dict(name='错误替换',basis=dict(earnings_power=999))]),
                 dict(price=dict(mode='per_share',value=100,date='2026-11-02'))]
        for change in changes:
            with self.subTest(change=change),self.assertRaises(ValueError):self.run_calc(dict(g,**change))
        research.save(self.store,self.cid,dict(self.project,base_revision=1),self.pid)
        with self.assertRaisesRegex(ValueError,'当前版本'):
            research.compute(self.store,self.cid,self.pid,dict(project_revision=2,title='g',change_note='x',inputs=g))

    def test_handoff_and_publication_retain_all_adopted_methods(self):
        e=self.run_calc(self.epv);g=self.run_calc(self.growth(e));ids=[e['id'],g['id']]
        h=research.handoff(self.store,self.cid,self.pid,dict(project_revision=1,calculation_ids=ids,note='独立采用EPV与增长'))
        b=dict(project_id=self.pid,research_revision=1,calculation_ids=ids,handoff_id=h['id'])
        research.validate_publication(self.store,self.cid,b)
        with self.assertRaisesRegex(ValueError,'不一致'):
            research.validate_publication(self.store,self.cid,dict(b,calculation_ids=[e['id']]))
        self.assertEqual(research.read(self.store,self.cid,self.pid)['handoffs'][0]['calculation_ids'],ids)


if __name__=='__main__':unittest.main()
